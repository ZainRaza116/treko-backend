from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
from users.models import BaseModel, CreatorModel, User, Employee, Organization


class Project(BaseModel, CreatorModel):
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    organization = models.ForeignKey(
        'users.Organization',
        on_delete=models.CASCADE,
        related_name='projects'
    )
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=(
            ('ACTIVE', 'Active'),
            ('PAUSED', 'Paused'),
            ('COMPLETED', 'Completed'),
            ('ARCHIVED', 'Archived'),
        ),
        default='ACTIVE'
    )
    budget_type = models.CharField(
        max_length=10,
        choices=(('FIXED', 'Fixed'), ('HOURLY', 'Hourly')),
        default='HOURLY'
    )
    budget_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    hourly_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )
    settings = models.JSONField(default=dict)
    is_billable = models.BooleanField(default=True)
    is_public = models.BooleanField(default=False)
    team_members = models.ManyToManyField(
        'users.Employee',
        related_name='projects'
    )

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']
        unique_together = ['name', 'organization']

    def __str__(self):
        return self.name


class Task(BaseModel, CreatorModel):
    """Model for tracking project tasks"""
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='tasks'
    )

    # Task management
    status = models.CharField(
        max_length=20,
        choices=(
            ('TODO', 'To Do'),
            ('IN_PROGRESS', 'In Progress'),
            ('REVIEW', 'In Review'),
            ('COMPLETED', 'Completed'),
            ('ARCHIVED', 'Archived'),
        ),
        default='TODO'
    )
    priority = models.CharField(
        max_length=10,
        choices=(
            ('LOW', 'Low'),
            ('MEDIUM', 'Medium'),
            ('HIGH', 'High'),
            ('URGENT', 'Urgent'),
        ),
        default='MEDIUM'
    )

    # Assignment
    assignee = models.ForeignKey(
        'users.Employee',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks'
    )

    # Scheduling
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        null=True,
        blank=True
    )

    # Task relationships
    parent_task = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='subtasks'
    )
    dependencies = models.ManyToManyField(
        'self',
        symmetrical=False,
        related_name='dependent_tasks',
        blank=True
    )

    # Task metadata
    tags = models.JSONField(default=list)
    category = models.CharField(max_length=50, blank=True)
    is_billable = models.BooleanField(default=True)
    completion_percentage = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    class Meta:
        db_table = 'tasks'
        ordering = ['due_date', 'priority', '-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['assignee', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]

    def __str__(self):
        return f"{self.name} - {self.project.name}"

    def get_total_time_spent(self):
        """
        Calculate the total time (in hours) spent on this task,
        based on `tasks_time` in ActivityInterval.
        """
        from .models import ActivityInterval  # local import to avoid circular dependency

        # Filter all intervals that include this task's ID in tasks_time
        intervals = ActivityInterval.objects.filter(tasks_time__has_key=str(self.id))

        total_seconds = 0
        for interval in intervals:
            # Safely retrieve the time from tasks_time if the key exists
            task_data = interval.tasks_time.get(str(self.id))
            if task_data:
                total_seconds += task_data.get('time', 0)

        return round(total_seconds / 3600, 2)

    def get_active_time_spent(self):
        """
        Calculate the active time (in hours) spent on this task,
        using `activity_level` from ActivityInterval.
        """
        from .models import ActivityInterval

        intervals = ActivityInterval.objects.filter(tasks_time__has_key=str(self.id))

        total_active_seconds = 0
        for interval in intervals:
            task_data = interval.tasks_time.get(str(self.id))
            if task_data:
                # Active time is a fraction of the total time based on activity_level
                interval_seconds = task_data.get('time', 0)
                active_seconds = int(interval_seconds * (interval.activity_level / 100))
                total_active_seconds += active_seconds

        return round(total_active_seconds / 3600, 2)

    def update_completion_percentage(self):
        """
        Update task completion based on time spent vs. estimated hours.
        """
        if not self.estimated_hours:
            return

        time_spent = self.get_total_time_spent()
        self.completion_percentage = min(
            round((time_spent / float(self.estimated_hours)) * 100),
            100
        )
        self.save()

    def is_overdue(self):
        """Check if the task is overdue (past due_date and not completed/archived)."""
        if self.due_date and self.status not in ['COMPLETED', 'ARCHIVED']:
            return timezone.now().date() > self.due_date
        return False

    def get_recent_activity(self, days=7):
        """
        Get recent activity for this task over the last `days` (default 7).
        Returns a dict with 'total_time', 'active_time', and 'avg_activity'.
        """
        from .models import ActivityInterval

        end_date = timezone.now().date()
        start_date = end_date - timezone.timedelta(days=days)

        # Filter intervals by date range AND containing this task in tasks_time
        intervals = ActivityInterval.objects.filter(
            timestamp__date__range=[start_date, end_date],
            tasks_time__has_key=str(self.id)
        )

        total_time = 0
        active_time = 0

        for interval in intervals:
            task_data = interval.tasks_time.get(str(self.id))
            if task_data:
                interval_seconds = task_data.get('time', 0)
                total_time += interval_seconds
                active_time += int(interval_seconds * (interval.activity_level / 100))

        avg_activity = 0
        if total_time > 0:
            avg_activity = round((active_time / total_time) * 100, 2)

        return {
            'total_time': total_time,       # in seconds
            'active_time': active_time,     # in seconds
            'avg_activity': avg_activity    # percentage
        }

    @property
    def status_display(self):
        return dict(self._meta.get_field('status').choices)[self.status]

    @property
    def priority_display(self):
        return dict(self._meta.get_field('priority').choices)[self.priority]


class ActivityInterval(BaseModel):
    """Model for storing activity intervals with media"""
    employee = models.ForeignKey('users.Employee', on_delete=models.CASCADE, related_name='intervals')
    timestamp = models.DateTimeField(default=timezone.now)
    is_online = models.BooleanField(default=True)
    activity_level = models.IntegerField(
        validators=[MinValueValidator(0), MaxValueValidator(100)]
    )

    # Store task-wise time breakdown
    tasks_time = models.JSONField(default=dict)
    # e.g. { "task_id": {"time": 600, "description": "Fixing bug"} }

    # Media storage
    screenshots = models.JSONField(default=list)
    # e.g. [{ "url": "...", "timestamp": "...", "window_title": "..." }]

    headshots = models.JSONField(default=list)
    # e.g. [{ "url": "...", "timestamp": "...", "status": "..." }]

    verification_status = models.CharField(
        max_length=20,
        choices=(
            ('PENDING', 'Pending Verification'),
            ('VERIFIED', 'Verified'),
            ('FAILED', 'Verification Failed'),
            ('SUSPICIOUS', 'Suspicious Activity'),
        ),
        default='PENDING'
    )

    class Meta:
        db_table = 'activity_intervals'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['employee', 'timestamp']),
        ]

    def get_projects_from_tasks(self):
        """Get unique Projects associated with any tasks in this interval."""
        task_ids = self.tasks_time.keys()
        return Project.objects.filter(tasks__id__in=task_ids).distinct()


class ActivityStats(BaseModel):
    """Model for tracking activity statistics"""
    employee = models.ForeignKey('users.Employee', on_delete=models.CASCADE, related_name='activity_stats')
    date = models.DateField()

    # Time tracking
    total_time = models.PositiveIntegerField(default=0)
    active_time = models.PositiveIntegerField(default=0)
    idle_time = models.PositiveIntegerField(default=0)

    # Activity metadata
    average_activity = models.FloatField(
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0
    )
    first_activity = models.TimeField(null=True)
    last_activity = models.TimeField(null=True)

    # Summaries
    projects_summary = models.JSONField(default=dict)
    # e.g. { "project_id": {"name": "Project A", "time": 1200, "active_time": 900}, ... }

    tasks_summary = models.JSONField(default=dict)
    # e.g. { "task_id": {"name": "Task 1", "project_name": "Project A", "time": 600, "active_time": 450}, ... }

    hourly_breakdown = models.JSONField(default=dict)
    # e.g. { "9": {"total_time": 600, "active_time": 500, "level": 83.3}, ... }

    # Time period tracking
    week_number = models.PositiveIntegerField()
    month = models.PositiveIntegerField()

    class Meta:
        db_table = 'activity_stats'
        unique_together = ['employee', 'date']
        indexes = [
            models.Index(fields=['employee', 'date']),
            models.Index(fields=['employee', 'week_number']),
        ]

    @classmethod
    def update_stats(cls, interval):
        """Update stats with new interval data"""
        stats, _ = cls.objects.get_or_create(
            employee=interval.employee,
            date=interval.timestamp.date(),
            defaults={
                'week_number': interval.timestamp.isocalendar()[1],
                'month': interval.timestamp.month
            }
        )

        # Each interval is 10 minutes (600 seconds)
        time_period = 600
        active_time = int(time_period * (interval.activity_level / 100))
        idle_time = time_period - active_time

        stats.total_time += time_period
        stats.active_time += active_time
        stats.idle_time += idle_time

        # Update project and task summaries
        from .models import Task
        tasks = Task.objects.filter(id__in=interval.tasks_time.keys()).select_related('project')

        for task in tasks:
            project = task.project
            task_id = str(task.id)
            project_id = str(project.id)
            task_time = interval.tasks_time[task_id]['time']
            task_active_time = int(task_time * (interval.activity_level / 100))

            # Update project summary
            if project_id not in stats.projects_summary:
                stats.projects_summary[project_id] = {
                    'name': project.name,
                    'time': 0,
                    'active_time': 0
                }
            stats.projects_summary[project_id]['time'] += task_time
            stats.projects_summary[project_id]['active_time'] += task_active_time

            # Update task summary
            if task_id not in stats.tasks_summary:
                stats.tasks_summary[task_id] = {
                    'name': task.name,
                    'project_name': project.name,
                    'project_id': project_id,
                    'time': 0,
                    'active_time': 0
                }
            stats.tasks_summary[task_id]['time'] += task_time
            stats.tasks_summary[task_id]['active_time'] += task_active_time

        # Update hourly breakdown
        hour = str(interval.timestamp.hour)
        if hour not in stats.hourly_breakdown:
            stats.hourly_breakdown[hour] = {
                'total_time': 0,
                'active_time': 0,
                'level': 0
            }
        stats.hourly_breakdown[hour]['total_time'] += time_period
        stats.hourly_breakdown[hour]['active_time'] += active_time
        # Recompute activity level (active_time / total_time * 100)
        stats.hourly_breakdown[hour]['level'] = (
                stats.hourly_breakdown[hour]['active_time'] /
                stats.hourly_breakdown[hour]['total_time'] * 100
        )

        # Update activity times
        current_time = interval.timestamp.time()
        if not stats.first_activity or current_time < stats.first_activity:
            stats.first_activity = current_time
        if not stats.last_activity or current_time > stats.last_activity:
            stats.last_activity = current_time

        # Update average activity across all intervals in the day
        total_intervals = stats.total_time / 600.0  # how many 10-min intervals so far
        stats.average_activity = (
                (stats.average_activity * (total_intervals - 1) + interval.activity_level) /
                total_intervals
        )

        stats.save()
        return stats


class TrackingSession(models.Model):
    """Master record per employee per day/shift"""

    employee = models.ForeignKey(
        "users.Employee",
        on_delete=models.CASCADE,
        related_name="tracking_sessions"
    )
    is_online = models.BooleanField(default=True, blank=True)
    activity_level = models.IntegerField(  # percentage (0–100)
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        default=0
    )
    date = models.DateField(auto_now_add=True)   # one per day

    # New fields to match updated payload structure
    app_version = models.CharField(max_length=100, blank=True, null=True)
    project_id = models.UUIDField(null=True, blank=True)
    
    # Stats fields
    active_sec = models.PositiveIntegerField(default=0)
    effective_sec = models.PositiveIntegerField(default=0)
    idle_sec = models.PositiveIntegerField(default=0)
    overtime_sec = models.PositiveIntegerField(default=0)
    recorded_sec = models.PositiveIntegerField(default=0)
    
    # Window tracking
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)
    
    # Aggregated data
    task_time = models.JSONField(default=dict)  # For backward compatibility
    active_apps = models.JSONField(default=dict)  # For backward compatibility
    screenshots = models.JSONField(default=list)
    headshots = models.JSONField(default=list)
    
    # App usage data
    app_session_count = models.PositiveIntegerField(default=0)
    app_session_duration_sec = models.PositiveIntegerField(default=0)
    active_by_app_sec = models.JSONField(default=dict)  # {app_name: seconds}
    
    total_duration = models.PositiveIntegerField(default=0)  # in seconds

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tracking_sessions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["employee", "updated_at"]),
        ]

    def __str__(self):
        return f"{self.employee} - {self.date}"


class ActiveAppUsage(models.Model):
    """Granular app usage logs from payload"""

    session = models.ForeignKey(
        TrackingSession,
        on_delete=models.CASCADE,
        related_name="apps"
    )
    app_name = models.CharField(max_length=255)
    seconds = models.PositiveIntegerField(default=0)  # time in seconds
    
    # Keep these for backward compatibility
    minutes = models.FloatField(default=0.0)  # derived from seconds
    samples = models.PositiveIntegerField(default=0)  # for backward compatibility
    
    timestamp = models.DateTimeField(auto_now_add=True)
    chunk_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "active_app_usage"
        indexes = [models.Index(fields=["app_name", "timestamp"])]

    def __str__(self):
        return f"{self.app_name} ({self.seconds} sec)"


class TaskUsage(models.Model):
    """Granular task time logs from payload"""

    session = models.ForeignKey(
        TrackingSession,
        on_delete=models.CASCADE,
        related_name="tasks"
    )
    task_id = models.UUIDField()
    project_id = models.UUIDField()
    
    # New fields to match updated payload structure
    effective_sec = models.PositiveIntegerField(default=0)
    overtime_sec = models.PositiveIntegerField(default=0)
    recorded_sec = models.PositiveIntegerField(default=0)
    remaining_task_time_sec = models.PositiveIntegerField(default=0)
    total_task_time_sec = models.PositiveIntegerField(default=0)
    total_worked_time_sec = models.PositiveIntegerField(default=0)
    
    # Keep minutes for backward compatibility
    minutes = models.FloatField(default=0.0)
    
    timestamp = models.DateTimeField(auto_now_add=True)
    chunk_id = models.UUIDField(null=True, blank=True)

    class Meta:
        db_table = "task_usage"
        indexes = [models.Index(fields=["task_id", "timestamp"])]

    def __str__(self):
        return f"Task {self.task_id} - {self.recorded_sec} sec"


class ScreenshotLog(models.Model):
    """Screenshots taken during session"""

    session = models.ForeignKey(
        TrackingSession,
        on_delete=models.CASCADE,
        related_name="screenshot_logs"
    )
    url = models.TextField()
    window_title = models.TextField(null=True, blank=True)
    timestamp = models.DateTimeField()

    class Meta:
        db_table = "screenshot_logs"
        indexes = [models.Index(fields=["timestamp"])]

    def __str__(self):
        return f"Screenshot at {self.timestamp}"


class HeadshotLog(models.Model):
    """Headshots captured during session"""

    session = models.ForeignKey(
        TrackingSession,
        on_delete=models.CASCADE,
        related_name="headshot_logs"
    )
    url = models.TextField()
    status = models.CharField(max_length=50, null=True, blank=True)  # e.g. "active", "away"
    timestamp = models.DateTimeField()

    class Meta:
        db_table = "headshot_logs"
        indexes = [models.Index(fields=["timestamp"])]

    def __str__(self):
        return f"Headshot at {self.timestamp} ({self.status})"

