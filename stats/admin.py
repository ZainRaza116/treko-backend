from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Project,
    Task,
    # WorkSession,  <-- REMOVE if no longer used in the updated code
    ActivityStats,
    ActivityInterval
)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'organization',
        'status',
        'budget_type',
        'team_members_count',
        'created_at'
    ]
    list_filter = [
        'status',
        'budget_type',
        'is_billable',
        'organization'
    ]
    search_fields = ['name', 'description']
    raw_id_fields = ['organization', 'created_by', 'team_members']
    date_hierarchy = 'created_at'

    def team_members_count(self, obj):
        return obj.team_members.count()

    team_members_count.short_description = 'Team Size'


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'project',
        'status',
        'priority',
        'assignee',
        'due_date',
        'completion_percentage',
        'total_hours'
    ]
    list_filter = ['status', 'priority', 'is_billable', 'project']
    search_fields = ['name', 'description', 'tags']
    raw_id_fields = ['project', 'assignee', 'parent_task', 'dependencies', 'created_by']
    date_hierarchy = 'created_at'

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'project', 'status', 'priority')
        }),
        ('Assignment & Scheduling', {
            'fields': ('assignee', 'start_date', 'due_date', 'estimated_hours')
        }),
        ('Task Relationships', {
            'fields': ('parent_task', 'dependencies')
        }),
        ('Metadata', {
            'fields': ('tags', 'category', 'is_billable', 'completion_percentage')
        })
    )

    def total_hours(self, obj):
        return f"{obj.get_total_time_spent()}h"

    total_hours.short_description = 'Total Hours'


@admin.register(ActivityInterval)
class ActivityIntervalAdmin(admin.ModelAdmin):
    """
    Updated to match the new ActivityInterval model fields:
    - employee, timestamp, is_online, activity_level, tasks_time, screenshots, headshots, etc.
    """
    list_display = [
        'employee',  # Assuming you have a FK to Employee
        'timestamp',
        'activity_level',
        'verification_status',
        'media_count'
    ]
    list_filter = ['timestamp', 'activity_level', 'verification_status', 'is_online']
    raw_id_fields = ['employee']
    date_hierarchy = 'timestamp'

    # If you want to show screenshots / headshots previews as read-only
    # (like in your old code), define them similarly:
    readonly_fields = [
        'screenshots_preview',
        'headshots_preview',
        'screenshots',
        'headshots',
        'tasks_time'
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': ('employee', 'timestamp', 'is_online', 'activity_level', 'verification_status')
        }),
        ('Task Time Logs', {
            'fields': ('tasks_time',)
        }),
        ('Media', {
            'fields': ('screenshots_preview', 'headshots_preview'),
            'classes': ('collapse',)
        }),
        ('Raw JSON Data', {
            'fields': ('screenshots', 'headshots'),
            'classes': ('collapse',)
        })
    )

    def media_count(self, obj):
        screenshots_count = len(obj.screenshots or [])
        headshots_count = len(obj.headshots or [])
        return f"{screenshots_count} screenshots, {headshots_count} headshots"

    media_count.short_description = 'Media Count'

    def screenshots_preview(self, obj):
        if not obj.screenshots:
            return "No screenshots"
        html = []
        for shot in obj.screenshots:
            url = shot.get('url')
            if url:
                html.append(
                    f'<a href="{url}" target="_blank">'
                    f'<img src="{url}" height="100" style="margin:5px" />'
                    f'</a>'
                )
        return format_html(''.join(html)) if html else "No screenshots"

    screenshots_preview.short_description = 'Screenshot Previews'

    def headshots_preview(self, obj):
        if not obj.headshots:
            return "No headshots"
        html = []
        for shot in obj.headshots:
            url = shot.get('url')
            if url:
                html.append(
                    f'<a href="{url}" target="_blank">'
                    f'<img src="{url}" height="100" style="margin:5px" />'
                    f'</a>'
                )
        return format_html(''.join(html)) if html else "No headshots"

    headshots_preview.short_description = 'Headshot Previews'


@admin.register(ActivityStats)
class ActivityStatsAdmin(admin.ModelAdmin):
    """
    Updated to match the new ActivityStats model:
    - total_time, active_time, idle_time, average_activity,
      first_activity, last_activity, projects_summary, tasks_summary, hourly_breakdown, etc.
    - No offline_time, mouse_clicks, keystrokes in the updated version.
    """
    list_display = [
        'employee',
        'date',
        'total_hours',
        'active_hours',
        'average_activity',
        'first_activity',
        'last_activity'
    ]
    list_filter = ['date', 'week_number', 'month']
    search_fields = ['employee__user__name']  # or 'employee__name' if that's how it's related
    raw_id_fields = ['employee']
    date_hierarchy = 'date'

    readonly_fields = [
        'total_time',
        'active_time',
        'idle_time',
        'average_activity',
        'projects_summary',
        'tasks_summary',
        'hourly_breakdown',
        'first_activity',
        'last_activity',
        'week_number',
        'month'
    ]

    fieldsets = (
        ('Employee & Date', {
            'fields': ('employee', 'date', 'week_number', 'month')
        }),
        ('Time Tracking', {
            'fields': ('total_time', 'active_time', 'idle_time')
        }),
        ('Activity Metrics', {
            'fields': ('average_activity', 'first_activity', 'last_activity')
        }),
        ('Summaries', {
            'fields': ('projects_summary', 'tasks_summary', 'hourly_breakdown'),
            'classes': ('collapse',)
        })
    )

    def total_hours(self, obj):
        return f"{round(obj.total_time / 3600, 2)}h" if obj.total_time else "0h"

    total_hours.short_description = 'Total Hours'

    def active_hours(self, obj):
        return f"{round(obj.active_time / 3600, 2)}h" if obj.active_time else "0h"

    active_hours.short_description = 'Active Hours'


from django.contrib import admin
from .models import TrackingSession, ActiveAppUsage, TaskUsage, ScreenshotLog, HeadshotLog


class ActiveAppUsageInline(admin.TabularInline):
    model = ActiveAppUsage
    extra = 0
    readonly_fields = ("app_name", "minutes", "samples", "timestamp")
    ordering = ("-timestamp",)


class TaskUsageInline(admin.TabularInline):
    model = TaskUsage
    extra = 0
    readonly_fields = ("task_id", "project_id", "minutes", "timestamp")
    ordering = ("-timestamp",)


class ScreenshotLogInline(admin.TabularInline):
    model = ScreenshotLog
    extra = 0
    readonly_fields = ("url", "window_title", "timestamp")
    ordering = ("-timestamp",)


class HeadshotLogInline(admin.TabularInline):
    model = HeadshotLog
    extra = 0
    readonly_fields = ("url", "status", "timestamp")
    ordering = ("-timestamp",)


@admin.register(TrackingSession)
class TrackingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "employee", "date", "is_online",
        "activity_level", "total_duration",
        "created_at", "updated_at",
    )
    list_filter = ("is_online", "date", "created_at")
    search_fields = ("employee__name", "employee__email")
    inlines = [ActiveAppUsageInline, TaskUsageInline, ScreenshotLogInline, HeadshotLogInline]
    ordering = ("-created_at",)


@admin.register(ActiveAppUsage)
class ActiveAppUsageAdmin(admin.ModelAdmin):
    list_display = ("session", "app_name", "minutes", "samples", "timestamp")
    list_filter = ("app_name", "timestamp")
    search_fields = ("app_name",)
    ordering = ("-timestamp",)


@admin.register(TaskUsage)
class TaskUsageAdmin(admin.ModelAdmin):
    list_display = ("session", "task_id", "project_id", "minutes", "timestamp")
    list_filter = ("timestamp",)
    search_fields = ("task_id", "project_id")
    ordering = ("-timestamp",)


@admin.register(ScreenshotLog)
class ScreenshotLogAdmin(admin.ModelAdmin):
    list_display = ("session", "timestamp", "window_title")
    list_filter = ("timestamp",)
    search_fields = ("window_title",)
    ordering = ("-timestamp",)


@admin.register(HeadshotLog)
class HeadshotLogAdmin(admin.ModelAdmin):
    list_display = ("session", "timestamp", "status")
    list_filter = ("status", "timestamp")
    ordering = ("-timestamp",)
