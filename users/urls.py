from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    OrganizationViewSet,
    DepartmentViewSet,
    PositionViewSet,
    EmployeeViewSet,
    AdminViewSet,
    LoginView,
    SignupView, ChangePasswordView
)

# Initialize router
router = DefaultRouter()

# Register viewsets
router.register(r'organizations', OrganizationViewSet, basename='organization')
router.register(r'departments', DepartmentViewSet, basename='department')
router.register(r'positions', PositionViewSet, basename='position')
router.register(r'employees', EmployeeViewSet, basename='employee')
router.register(r'admins', AdminViewSet, basename='admin')

# URL patterns
urlpatterns = [
    # Include router URLs
    path('', include(router.urls)),

    # Auth endpoints
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/signup/', SignupView.as_view(), name='signup'),
    path('auth/change-password/', ChangePasswordView.as_view(), name='change-password'),
]
