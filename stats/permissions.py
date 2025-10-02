from rest_framework import permissions


class IsManagerUser(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.role == 'MANAGER')


class IsManagerOrAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user and
            (request.user.role in ['MANAGER', 'ADMIN'] or request.user.is_superuser)
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == 'ADMIN' or request.user.is_superuser:
            return True

        # For manager, check if object belongs to their organization
        if hasattr(obj, 'organization'):
            return obj.organization == request.user.organization
        elif hasattr(obj, 'project'):
            return obj.project.organization == request.user.organization
        elif hasattr(obj, 'employee'):
            return obj.employee.organization == request.user.organization

        return False
