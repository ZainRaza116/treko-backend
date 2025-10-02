from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils.crypto import get_random_string
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from config import settings
from .models import (
    Organization, Admin, Employee, Department, Position
)

User = get_user_model()


class TimestampedSerializer(serializers.ModelSerializer):
    """Base serializer for models with timestamp fields"""
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    class Meta:
        abstract = True


class BaseModelSerializer(TimestampedSerializer):
    """Base serializer with UUID handling"""
    id = serializers.UUIDField(read_only=True)

    class Meta:
        abstract = True


class OrganizationRelatedSerializer(serializers.ModelSerializer):
    """Base serializer for models related to organizations"""

    def validate_organization_id(self, organization_id):
        try:
            return Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            raise serializers.ValidationError("Invalid organization ID")


class DepartmentSerializer(BaseModelSerializer):
    class Meta:
        model = Department
        fields = ('id', 'name', 'description', 'organization', 'is_active',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class DepartmentCreateUpdateSerializer(BaseModelSerializer):
    """Serializer for creating and updating departments"""

    class Meta:
        model = Department
        fields = ('id', 'name', 'description', 'organization', 'is_active')
        read_only_fields = ('id',)

    def validate_organization(self, organization):
        user = self.context['request'].user
        if not user.is_superuser and user.organization != organization:
            raise serializers.ValidationError(
                "You can only create departments for your organization"
            )
        return organization


class PositionSerializer(BaseModelSerializer):
    class Meta:
        model = Position
        fields = ('id', 'title', 'department', 'description', 'is_active',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class PositionCreateUpdateSerializer(BaseModelSerializer):
    """Serializer for creating and updating positions"""

    class Meta:
        model = Position
        fields = ('id', 'title', 'department', 'description', 'is_active')
        read_only_fields = ('id',)

    def validate_department(self, department):
        user = self.context['request'].user
        if not user.is_superuser and user.organization != department.organization:
            raise serializers.ValidationError(
                "You can only create positions in your organization's departments"
            )
        return department


class OrganizationCreateUpdateSerializer(BaseModelSerializer):
    """Serializer for creating and updating organizations"""

    class Meta:
        model = Organization
        fields = ('id', 'name', 'timezone', 'settings', 'is_active')
        read_only_fields = ('id',)

    def validate(self, data):
        user = self.context['request'].user
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can create/update organizations")
        return data

    def create(self, validated_data):
        user = self.context['request'].user
        return Organization.objects.create(
            created_by=user,
            **validated_data
        )


class OrganizationSerializer(OrganizationCreateUpdateSerializer):
    """Serializer for reading organization details"""
    departments = DepartmentSerializer(many=True, read_only=True)
    active_users_count = serializers.SerializerMethodField()

    class Meta(OrganizationCreateUpdateSerializer.Meta):
        fields = OrganizationCreateUpdateSerializer.Meta.fields + (
            'departments', 'active_users_count', 'created_at', 'updated_at'
        )
        read_only_fields = OrganizationCreateUpdateSerializer.Meta.read_only_fields + (
            'created_at', 'updated_at'
        )

    def get_active_users_count(self, obj):
        if isinstance(obj, dict):
            return obj.get('active_users_count', 0)
        return obj.active_users_count


class UserSerializer(BaseModelSerializer):
    organization = OrganizationSerializer(read_only=True)
    department = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    full_title = serializers.CharField(read_only=True)
    employee_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'name', 'role', 'organization', 'department',
                  'position', 'full_title', 'is_active', 'created_at', 'updated_at', 'employee_id')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_department(self, obj):
        """
        Get department for the user. If the user is an admin, retrieve it from the Admin model.
        """
        if obj.role == 'ADMIN' and hasattr(obj, 'admin'):
            return DepartmentSerializer(obj.admin.department).data if obj.admin.department else None
        return DepartmentSerializer(obj.department).data if obj.department else None

    def get_position(self, obj):
        """
        Get position for the user. If the user is an admin, retrieve it from the Admin model.
        """
        if obj.role == 'ADMIN' and hasattr(obj, 'admin'):
            return PositionSerializer(obj.admin.position).data if obj.admin.position else None
        return PositionSerializer(obj.position).data if obj.position else None

    def get_employee_id(self, obj):
        """
        Get employee ID for the user if they have an associated Employee instance.
        """
        if hasattr(obj, 'employee') and obj.employee:
            return obj.employee.id
        return None


class UserUpdateSerializer(serializers.ModelSerializer):
    """Base serializer for user profile updates"""
    email = serializers.EmailField(read_only=True)  # Email cannot be changed

    class Meta:
        model = User
        fields = ('name', 'email', 'is_active')


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate_email(self, value):
        return value.lower().strip()


class TokenSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = UserSerializer()


class BaseUserCreateSerializer(serializers.Serializer):
    """Base serializer for user creation"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8)
    name = serializers.CharField()
    organization_id = serializers.UUIDField()
    department_id = serializers.UUIDField()
    position_id = serializers.UUIDField()

    def validate_email(self, value):
        email = value.lower().strip()
        if User.objects.filter(email=email).exists():
            raise serializers.ValidationError("User with this email already exists")
        return email

    def validate(self, data):
        # First validate organization
        try:
            organization = Organization.objects.get(id=data['organization_id'])
            if not organization.is_active:
                raise serializers.ValidationError({
                    'organization_id': 'This organization is not active'
                })
            data['organization'] = organization
        except Organization.DoesNotExist:
            raise serializers.ValidationError({
                'organization_id': 'Organization not found'
            })

        # Then validate department
        try:
            department = Department.objects.get(
                id=data['department_id']
            )
            if department.organization_id != organization.id:
                raise serializers.ValidationError({
                    'department_id': 'Department does not belong to the selected organization'
                })
            if not department.is_active:
                raise serializers.ValidationError({
                    'department_id': 'This department is not active'
                })
            data['department'] = department
        except Department.DoesNotExist:
            raise serializers.ValidationError({
                'department_id': 'Department not found'
            })

        # Finally validate position
        try:
            position = Position.objects.get(id=data['position_id'])
            if position.department_id != department.id:
                raise serializers.ValidationError({
                    'position_id': 'Position does not belong to the selected department'
                })
            if not position.is_active:
                raise serializers.ValidationError({
                    'position_id': 'This position is not active'
                })
            data['position'] = position
        except Position.DoesNotExist:
            raise serializers.ValidationError({
                'position_id': 'Position not found'
            })

        return data


class AdminSerializer(BaseModelSerializer):
    """Serializer for reading admin details"""
    user = UserSerializer()
    permissions = serializers.JSONField()
    department = DepartmentSerializer(source='user.department')
    position = PositionSerializer(source='user.position')

    class Meta:
        model = Admin
        fields = ('id', 'user', 'permissions', 'department', 'position',
                  'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')


class AdminCreateSerializer(BaseUserCreateSerializer):
    permissions = serializers.JSONField(required=False, default=dict)

    def validate(self, data):
        data = super().validate(data)
        user = self.context['request'].user
        if not user.is_superuser:
            raise PermissionDenied("Only superusers can create admin users")
        return data

    def create(self, validated_data):
        organization = validated_data.pop('organization')
        department = validated_data.pop('department')
        position = validated_data.pop('position')
        permissions = validated_data.pop('permissions', {})
        user = self.context['request'].user

        admin_user = User.objects.create_user(
            organization=organization,
            department=department,
            position=position,
            role='ADMIN',
            created_by=user,
            **validated_data
        )

        Admin.objects.create(
            user=admin_user,
            permissions=permissions,
            created_by=user,
            department=department,
            position=position
        )

        return admin_user


class AdminUpdateSerializer(BaseModelSerializer):
    """Serializer for updating admin details"""
    user = UserUpdateSerializer()
    permissions = serializers.JSONField(required=False)
    department_id = serializers.UUIDField(required=False)
    position_id = serializers.UUIDField(required=False)

    class Meta:
        model = Admin
        fields = ('id', 'user', 'permissions', 'department_id', 'position_id')
        read_only_fields = ('id',)

    def validate(self, data):
        if 'department_id' in data or 'position_id' in data:
            organization = self.instance.user.organization

            if 'department_id' in data:
                try:
                    department = Department.objects.get(
                        id=data['department_id'],
                        organization=organization
                    )
                    data['department'] = department
                except Department.DoesNotExist:
                    raise serializers.ValidationError({
                        'department_id': 'Invalid department ID'
                    })

            if 'position_id' in data:
                try:
                    position = Position.objects.get(
                        id=data['position_id'],
                        department=data.get('department', self.instance.user.department)
                    )
                    data['position'] = position
                except Position.DoesNotExist:
                    raise serializers.ValidationError({
                        'position_id': 'Invalid position ID'
                    })

        return data

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        permissions = validated_data.pop('permissions', None)
        department = validated_data.pop('department', None)
        position = validated_data.pop('position', None)

        # Update user data
        for attr, value in user_data.items():
            setattr(instance.user, attr, value)

        # Update department and position
        if department:
            instance.user.department = department
        if position:
            instance.user.position = position

        instance.user.save()

        # Update permissions if provided
        if permissions is not None:
            instance.permissions = permissions

        instance.save()
        return instance


class SignupSerializer(BaseUserCreateSerializer):
    role = serializers.ChoiceField(choices=['MANAGER', 'EMPLOYEE'])

    class Meta:
        model = User

        fields = ['email', 'name', 'role', 'organization_id', 'department_id', 'position_id']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop('password', None)  # Remove password field entirely

    def validate(self, data):
        if data.get('role') == 'ADMIN':
            raise PermissionDenied("Admin users can only be created through admin creation endpoint")
        return data

    def create(self, validated_data):
        # Generate temporary password
        temp_password = get_random_string(12)

        validated_data.pop('password', None)
        organization = Organization.objects.get(id=validated_data.pop('organization_id'))
        department = Department.objects.get(id=validated_data.pop('department_id'))
        position = Position.objects.get(id=validated_data.pop('position_id'))
        # Create user with temporary password
        user = User.objects.create_user(
            organization=organization,
            department=department,
            position=position,
            password=temp_password,
            created_by=self.context['request'].user,
            is_active=True,
            requires_password_change=True,  # Add this field to User model
            **validated_data
        )

        Employee.objects.create(
            user=user,
            joined_at=user.created_at
        )

        # Send email with temporary password
        self.send_welcome_email(user, temp_password)

        return user

    def send_welcome_email(self, user, temp_password):
        # Implement email sending logic here
        # You can use Django's send_mail or a custom email service
        subject = "Welcome to Our Platform"
        message = f"""
            Welcome {user.name},
            
            Your account has been created. Please use the following credentials to log in:
            
            Email: {user.email}
            Temporary Password: {temp_password}
            
            Please change your password upon first login.
            """
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )


class EmployeeSerializer(BaseModelSerializer):
    user = UserSerializer()
    manager = serializers.SerializerMethodField()
    team_size = serializers.IntegerField(read_only=True)
    active_projects = serializers.SerializerMethodField()

    class Meta:
        model = Employee
        fields = ('id', 'user', 'manager', 'team_size', 'active_projects', 'joined_at',
                  'is_active', 'created_at', 'updated_at')
        read_only_fields = ('id', 'created_at', 'updated_at')

    def get_manager(self, obj):
        if obj.manager:
            return UserSerializer(obj.manager.user).data
        return None

    def get_team_size(self, obj):
        return obj.get_team_size()

    def get_active_projects(self, obj):
        return list(obj.projects.filter(status='ACTIVE').values_list('name', flat=True))


class EmployeeUpdateSerializer(BaseModelSerializer):
    """Serializer for updating employee details"""
    user = UserUpdateSerializer()
    manager_id = serializers.UUIDField(required=False, allow_null=True)
    department_id = serializers.UUIDField(required=False)
    position_id = serializers.UUIDField(required=False)

    class Meta:
        model = Employee
        fields = ('id', 'user', 'manager_id', 'department_id', 'position_id', 'is_active')
        read_only_fields = ('id',)

    def validate(self, data):
        if 'department_id' in data or 'position_id' in data:
            organization = self.instance.user.organization

            if 'department_id' in data:
                try:
                    department = Department.objects.get(
                        id=data['department_id'],
                        organization=organization
                    )
                    data['department'] = department
                except Department.DoesNotExist:
                    raise serializers.ValidationError({
                        'department_id': 'Invalid department ID'
                    })

            if 'position_id' in data:
                try:
                    position = Position.objects.get(
                        id=data['position_id'],
                        department=data.get('department', self.instance.user.department)
                    )
                    data['position'] = position
                except Position.DoesNotExist:
                    raise serializers.ValidationError({
                        'position_id': 'Invalid position ID'
                    })

        return data

    def update(self, instance, validated_data):
        user_data = validated_data.pop('user', {})
        manager_id = validated_data.pop('manager_id', None)
        department = validated_data.pop('department', None)
        position = validated_data.pop('position', None)

        # Update user data
        for attr, value in user_data.items():
            setattr(instance.user, attr, value)

        # Update department and position
        if department:
            instance.user.department = department
        if position:
            instance.user.position = position

        instance.user.save()

        # Update manager if provided
        if manager_id is not None:
            instance.manager_id = manager_id

        instance.save()
        return instance


class ManagerAssignSerializer(serializers.Serializer):
    """Serializer for assigning managers to employees"""
    manager_id = serializers.UUIDField(allow_null=True)

    def validate_manager_id(self, value):
        if not value:
            return None

        try:
            employee = self.context.get('employee')
            manager = Employee.objects.get(
                id=value,  # Changed from user_id to id
                user__organization=employee.user.organization
            )

            # Prevent self-assignment
            if manager.id == employee.id:  # Changed from user_id to id
                raise serializers.ValidationError(
                    "An employee cannot be their own manager"
                )

            # Check for circular management chain
            current_manager = manager
            while current_manager:
                if current_manager.id == employee.id:
                    raise serializers.ValidationError(
                        "Circular management chain detected"
                    )
                current_manager = current_manager.manager

            return manager
        except Employee.DoesNotExist:
            raise serializers.ValidationError("Invalid manager ID")


class TeamMemberSerializer(BaseModelSerializer):
    """Serializer for team member listing"""
    user = UserSerializer()
    department = DepartmentSerializer(source='user.department')
    position = PositionSerializer(source='user.position')

    class Meta:
        model = Employee
        fields = ('id', 'user', 'department', 'position', 'joined_at')
        read_only_fields = ('id', 'joined_at')


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['confirm_password']:
            raise serializers.ValidationError({
                'confirm_password': 'Passwords do not match'
            })
        return data
