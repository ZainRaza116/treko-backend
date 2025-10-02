from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, Organization, Department, Position, Employee, Admin


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('email', 'name', 'role', 'organization', 'department', 'position', 'is_active')
    list_filter = ('is_active', 'role', 'organization', 'department', 'position')
    search_fields = ('email', 'name')
    ordering = ('email',)
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal info', {'fields': ('name', 'role')}),
        ('Organization', {'fields': ('organization', 'department', 'position')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Important dates', {'fields': ('last_login', 'created_at', 'updated_at')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'name', 'role', 'organization'),
        }),
    )
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ('name', 'timezone', 'is_active', 'created_at')
    list_filter = ('is_active', 'timezone')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'organization', 'is_active', 'created_at')
    list_filter = ('organization', 'is_active')
    search_fields = ('name', 'organization__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('title', 'department', 'is_active', 'created_at')
    list_filter = ('department', 'is_active')
    search_fields = ('title', 'department__name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'get_email', 'get_department', 'get_position', 'manager', 'joined_at')
    list_filter = ('user__department', 'user__position', 'is_active')
    search_fields = ('user__email', 'user__name')
    readonly_fields = ('created_at', 'updated_at')

    def get_name(self, obj):
        return obj.user.name

    get_name.short_description = 'Name'
    get_name.admin_order_field = 'user__name'

    def get_email(self, obj):
        return obj.user.email

    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'

    def get_department(self, obj):
        return obj.user.department

    get_department.short_description = 'Department'
    get_department.admin_order_field = 'user__department'

    def get_position(self, obj):
        return obj.user.position

    get_position.short_description = 'Position'
    get_position.admin_order_field = 'user__position'


@admin.register(Admin)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('get_name', 'get_email', 'get_department', 'get_position')
    list_filter = ('user__department', 'user__position')
    search_fields = ('user__email', 'user__name')
    readonly_fields = ('created_at', 'updated_at')

    def get_name(self, obj):
        return obj.user.name

    get_name.short_description = 'Name'
    get_name.admin_order_field = 'user__name'

    def get_email(self, obj):
        return obj.user.email

    get_email.short_description = 'Email'
    get_email.admin_order_field = 'user__email'

    def get_department(self, obj):
        return obj.user.department

    get_department.short_description = 'Department'
    get_department.admin_order_field = 'user__department'

    def get_position(self, obj):
        return obj.user.position

    get_position.short_description = 'Position'
    get_position.admin_order_field = 'user__position'
