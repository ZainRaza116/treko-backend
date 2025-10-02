from django.contrib.auth import authenticate
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django_filters import rest_framework as django_filters
from rest_framework import status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import (
    Employee, Admin, Department, Position, Organization
)
from .permissions import IsSuperUser, IsAuthenticatedAndAdmin
from .serializers import (
    # Authentication serializers
    LoginSerializer, TokenSerializer,  # Organization serializers
    OrganizationSerializer, OrganizationCreateUpdateSerializer,
    # Department serializers
    DepartmentSerializer, DepartmentCreateUpdateSerializer,
    # Position serializers
    PositionSerializer, PositionCreateUpdateSerializer,
    # Admin serializers
    AdminSerializer, AdminCreateSerializer, AdminUpdateSerializer,
    # Employee serializers
    EmployeeSerializer, EmployeeUpdateSerializer,
    # Other serializers
    SignupSerializer, ManagerAssignSerializer, TeamMemberSerializer, ChangePasswordSerializer
)


class BaseAPIException(Exception):
    """Custom exception for API errors"""

    def __init__(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class TokenGeneratorMixin:
    """Mixin to handle token generation logic"""

    def generate_tokens(self, user):
        try:
            refresh = RefreshToken.for_user(user)

            # Set user role in token
            if user.is_superuser:
                refresh['role'] = 'SUPERUSER'
                refresh['org_id'] = None
            else:
                refresh['role'] = user.role or 'EMPLOYEE'  # Default to EMPLOYEE if no role
                # Safely handle organization ID
                refresh['org_id'] = str(user.organization.id) if user.organization else None

            # Additional useful claims
            refresh['email'] = user.email
            refresh['is_superuser'] = user.is_superuser
            refresh['is_active'] = user.is_active

            # Generate response data
            data = {
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'user': user,
            }
            return TokenSerializer(data).data

        except Exception as e:

            raise BaseAPIException(
                'Error generating authentication tokens. Please try again.',
                status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ErrorHandlingMixin:
    """Mixin to handle common error scenarios"""

    def handle_exception(self, exc):
        if isinstance(exc, BaseAPIException):
            return Response(
                {'error': exc.message},
                status=exc.status_code
            )
        if isinstance(exc, IntegrityError):
            if 'unique constraint' in str(exc).lower() and 'email' in str(exc).lower():
                return Response(
                    {'error': 'A user with this email already exists'},
                    status=status.HTTP_409_CONFLICT
                )
        if isinstance(exc, ObjectDoesNotExist):
            return Response(
                {'error': str(exc)},
                status=status.HTTP_404_NOT_FOUND
            )
        if isinstance(exc, ValidationError):
            return Response(
                {'error': exc.detail},
                status=status.HTTP_400_BAD_REQUEST
            )
        if isinstance(exc, PermissionDenied):
            return Response(
                {'error': str(exc)},
                status=status.HTTP_403_FORBIDDEN
            )
        return super().handle_exception(exc)


class OrganizationAccessMixin:
    """Mixin to handle organization access checks"""

    def validate_organization_access(self, user, organization_id):
        if user.role == 'ADMIN' and str(user.organization.id) != str(organization_id):
            raise PermissionDenied("You can only access your organization's data")


class UserManagementMixin:
    """Mixin for common user management operations"""

    def validate_manager_assignment(self, manager_id, employee):
        if manager_id:
            try:
                manager = Employee.objects.get(
                    user_id=manager_id,
                    user__organization=employee.user.organization
                )
                # Prevent circular management chain
                current_manager = manager
                while current_manager:
                    if current_manager.id == employee.id:
                        raise BaseAPIException("Circular management chain detected")
                    current_manager = current_manager.manager
                return manager
            except Employee.DoesNotExist:
                raise BaseAPIException("Invalid manager ID")
        return None


class LoginView(TokenGeneratorMixin, ErrorHandlingMixin, APIView):
    serializer_class = LoginSerializer
    permission_classes = []  # Allow unauthenticated access

    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = authenticate(
                email=serializer.validated_data['email'],
                password=serializer.validated_data['password']
            )

            if not user:
                raise BaseAPIException(
                    'Invalid email or password',
                    status.HTTP_401_UNAUTHORIZED
                )

            if not user.is_active:
                raise BaseAPIException(
                    'This account has been deactivated',
                    status.HTTP_403_FORBIDDEN
                )

            tokens = self.generate_tokens(user)
            response_data = {
                **tokens,
                'requires_password_change': user.requires_password_change
            }

            return Response(response_data)

        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except BaseAPIException as e:
            return Response(
                {'error': e.message},
                status=e.status_code
            )
        except Exception as e:
            return Response(
                {'error': 'An unexpected error occurred during login'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class OrganizationViewSet(ErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return OrganizationCreateUpdateSerializer
        return OrganizationSerializer

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Organization.objects.all()
        return Organization.objects.filter(id=self.request.user.organization.id)


class DepartmentViewSet(ErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedAndAdmin]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Department.objects.all()
        return Department.objects.filter(organization=self.request.user.organization)

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return DepartmentCreateUpdateSerializer
        return DepartmentSerializer


class PositionViewSet(ErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticatedAndAdmin]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Position.objects.all()
        return Position.objects.filter(
            department__organization=self.request.user.organization
        )

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return PositionCreateUpdateSerializer
        return PositionSerializer


class EmployeeFilter(django_filters.FilterSet):
    department = django_filters.UUIDFilter(field_name='user__department__id')
    position = django_filters.UUIDFilter(field_name='user__position__id')
    name = django_filters.CharFilter(field_name='user__name', lookup_expr='icontains')

    class Meta:
        model = Employee
        fields = ['department', 'position']


class EmployeeViewSet(ErrorHandlingMixin, viewsets.ModelViewSet):
    # permission_classes = [IsAuthenticatedAndAdmin]
    filter_backends = [django_filters.DjangoFilterBackend, filters.SearchFilter]
    filterset_class = EmployeeFilter
    search_fields = ['user__name', 'user__email']

    def get_permissions(self):
        if self.action == 'team':
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticatedAndAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = Employee.objects.select_related(
            'user',
            'user__department',
            'user__position'
        )

        if not self.request.user.is_superuser:
            queryset = queryset.filter(
                user__organization=self.request.user.organization
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'assign_manager':
            return ManagerAssignSerializer
        elif self.action in ['update', 'partial_update']:
            return EmployeeUpdateSerializer
        elif self.action == 'team':
            return TeamMemberSerializer
        return EmployeeSerializer

    @action(detail=True, methods=['post'])
    def assign_manager(self, request, pk=None):
        employee = self.get_object()
        serializer = self.get_serializer(
            data=request.data,
            context={'employee': employee}
        )
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            # The serializer's validate_manager_id already returns the manager instance
            employee.manager = serializer.validated_data['manager_id']
            employee.save()

        return Response(EmployeeSerializer(employee).data)

    @action(detail=True, methods=['get'])
    def team(self, request, pk=None):
        employee = self.get_object()
        team_members = self.get_queryset().filter(manager=employee)
        serializer = self.get_serializer(team_members, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['delete'])
    def destroy_employee(self, request, pk=None):
        employee = self.get_object()

        if employee.team_members.exists():
            raise ValidationError(
                "Cannot delete employee with direct reports. Reassign team members first."
            )

        with transaction.atomic():
            user = employee.user
            employee.delete()
            user.delete()

        return Response(
            {"message": "Employee deleted successfully", "deleted_id": pk},
            status=status.HTTP_200_OK
        )


class AdminViewSet(ErrorHandlingMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsSuperUser]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return Admin.objects.all().select_related('user', 'user__department', 'user__position')
        return Admin.objects.filter(
            user__organization=self.request.user.organization
        ).select_related('user', 'user__department', 'user__position')

    def get_serializer_class(self):
        if self.action in ['update', 'partial_update']:
            return AdminUpdateSerializer
        elif self.action == 'create':
            return AdminCreateSerializer
        return AdminSerializer

    @action(detail=True, methods=['patch'])
    def update_permissions(self, request, pk=None):
        admin = self.get_object()
        current_permissions = admin.permissions.copy()
        current_permissions.update(request.data)

        serializer = self.get_serializer(
            admin,
            data={'permissions': current_permissions},
            partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(serializer.data)


class SignupView(ErrorHandlingMixin, OrganizationAccessMixin, APIView):
    permission_classes = [IsAuthenticatedAndAdmin]
    serializer_class = SignupSerializer

    def post(self, request):
        serializer = self.serializer_class(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)

        self.validate_organization_access(
            request.user,
            serializer.validated_data['organization_id']
        )

        if serializer.validated_data.get('role') == 'ADMIN':
            raise PermissionDenied("Admin users can only be created by superusers")

        with transaction.atomic():
            serializer.save()
            return Response(
                {
                    'message': 'User account created successfully. Login credentials have been sent to the provided '
                               'email.',
                },
                status=status.HTTP_201_CREATED
            )


class ChangePasswordView(ErrorHandlingMixin, APIView):
    serializer_class = ChangePasswordSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            serializer = self.serializer_class(data=request.data)
            serializer.is_valid(raise_exception=True)

            user = request.user

            # Verify current password
            if not user.check_password(serializer.validated_data['current_password']):
                raise BaseAPIException(
                    'Current password is incorrect',
                    status.HTTP_400_BAD_REQUEST
                )

            # Set new password
            user.set_password(serializer.validated_data['new_password'])
            user.requires_password_change = False
            user.save()

            # Generate new tokens since password changed
            tokens = TokenGeneratorMixin().generate_tokens(user)

            return Response({
                'message': 'Password changed successfully',
                **tokens
            })

        except ValidationError as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except BaseAPIException as e:
            return Response(
                {'error': e.message},
                status=e.status_code
            )
        except Exception as e:
            return Response(
                {'error': 'An unexpected error occurred while changing password'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
