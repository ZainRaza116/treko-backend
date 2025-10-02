# middleware.py
import logging

from django.http import JsonResponse
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError, AuthenticationFailed

logger = logging.getLogger(__name__)


class JWTAuthMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_auth = JWTAuthentication()

        # Paths that don't require authentication
        self.PUBLIC_PATHS = [
            '/api/auth/login/',
            '/api/auth/signup/',
            '/api/auth/refresh/',
            '/admin/',
        ]

        # Paths that only superuser can access
        self.SUPERUSER_PATHS = [
            '/api/organizations/',  # Organization creation
            '/api/admins/',  # Admin user creation
        ]

    def __call__(self, request):
        try:
            # Skip authentication for public paths
            if self.is_path_public(request.path):
                return self.get_response(request)

            # Try to authenticate
            auth_result = self.jwt_auth.authenticate(request)
            if auth_result:
                user, token = auth_result
                request.user = user

                # Check superuser-only paths
                if any(request.path.startswith(path) for path in self.SUPERUSER_PATHS):
                    if not user.is_superuser:
                        return JsonResponse(
                            {'error': 'Only superusers can access this resource'},
                            status=status.HTTP_403_FORBIDDEN
                        )

                # Regular user endpoint validations
                if '/api/auth/signup/' in request.path and request.method == 'POST':
                    if not (user.is_superuser or user.role == 'ADMIN'):
                        return JsonResponse(
                            {'error': 'Only superusers and admins can create users'},
                            status=status.HTTP_403_FORBIDDEN
                        )

            else:
                if not self.is_path_public(request.path):
                    return JsonResponse(
                        {'error': 'Authentication required'},
                        status=status.HTTP_401_UNAUTHORIZED
                    )

        except (InvalidToken, TokenError, AuthenticationFailed) as e:
            return JsonResponse(
                {'error': str(e)},
                status=status.HTTP_401_UNAUTHORIZED
            )
        except Exception as e:
            logger.error(f"Authentication error: {str(e)}")
            return JsonResponse(
                {'error': 'Authentication error occurred'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return self.get_response(request)

    def is_path_public(self, path):
        """Check if the path is in public paths list"""
        return any(path.startswith(public_path) for public_path in self.PUBLIC_PATHS)
