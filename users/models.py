import uuid

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.core.validators import validate_email
from django.db import models
from django.utils import timezone


class TimestampedModel(models.Model):
    """Base model with timestamp fields"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """Base model with UUID primary key"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CreatorModel(models.Model):
    """Base model with creator tracking"""
    created_by = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='%(class)s_created',
    )

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimestampedModel):
    """Base model combining UUID and timestamps"""

    class Meta:
        abstract = True


class CustomUserManager(BaseUserManager):
    def _create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', None)
        extra_fields.setdefault('name', 'Superuser')
        extra_fields.setdefault('organization', None)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self._create_user(email, password, **extra_fields)


class Department(BaseModel):
    """Model for managing departments"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name='departments'
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'departments'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} - {self.organization.name}"


class Position(BaseModel):
    """Model for managing positions/roles within the organization"""
    title = models.CharField(max_length=100)
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='positions'
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'positions'
        ordering = ['title']
        unique_together = ['title', 'department']

    def __str__(self):
        return f"{self.title} - {self.department.name}"


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """Enhanced User model with role-based functionality"""
    ROLE_CHOICES = (
        ('ADMIN', 'Admin'),
        ('MANAGER', 'Manager'),
        ('EMPLOYEE', 'Employee'),
    )

    requires_password_change = models.BooleanField(default=False)
    organization = models.ForeignKey(
        'Organization',
        on_delete=models.CASCADE,
        related_name='users',
        null=True,
        blank=True
    )
    email = models.EmailField(unique=True, validators=[validate_email])
    name = models.CharField(max_length=255)
    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        null=True,
        blank=True
    )
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users'
    )
    preferences = models.JSONField(default=dict)
    last_login = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_users'
    )

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['name']

    class Meta:
        db_table = 'users'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.email})"

    def is_organization_admin(self):
        return self.role == 'ADMIN' and self.organization is not None

    def is_superuser_admin(self):
        return self.is_superuser and self.organization is None

    @property
    def full_title(self):
        if self.position:
            return f"{self.position.title} - {self.department.name}"
        return self.role


class Organization(BaseModel, CreatorModel):
    """Enhanced Organization model"""
    name = models.CharField(max_length=255)
    timezone = models.CharField(max_length=50)
    settings = models.JSONField(default=dict)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'organizations'
        ordering = ['name']

    def __str__(self):
        return self.name

    def get_active_departments(self):
        return self.departments.filter(is_active=True)

    def get_active_users_count(self):
        return self.users.filter(is_active=True).count()

    @property
    def active_users_count(self):
        return self.get_active_users_count()


class Admin(BaseModel, CreatorModel):
    """Enhanced Admin model with additional fields"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    permissions = models.JSONField(default=dict)
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admins'
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.SET_NULL,
        null=True,
        related_name='admins'
    )

    class Meta:
        db_table = 'admins'
        ordering = ['user__name']

    def __str__(self):
        return f"Admin: {self.user.name}"

    @property
    def organization(self):
        return self.user.organization


class Employee(BaseModel):
    """Enhanced Employee model with reporting structure"""
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='team_members'
    )
    joined_at = models.DateTimeField(default=timezone.now)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'employees'
        ordering = ['user__name']

    def __str__(self):
        return f"Employee: {self.user.name}"

    @property
    def department(self):
        return self.user.department

    @property
    def position(self):
        return self.user.position

    @property
    def organization(self):
        return self.user.organization

    def get_team_size(self):
        return self.team_members.filter(is_active=True).count()

    def get_active_projects(self):
        return self.projects.filter(status='ACTIVE')

    def get_pending_tasks(self):
        return self.assigned_tasks.exclude(status__in=['COMPLETED', 'ARCHIVED'])
