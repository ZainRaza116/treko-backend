from django.utils import timezone
from rest_framework import serializers

from .models import Project, Task, ActivityStats, ActivityInterval
from .models import TrackingSession, ActiveAppUsage, TaskUsage, ScreenshotLog, HeadshotLog


class ProjectSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source='organization.name', read_only=True)
    team_members_count = serializers.SerializerMethodField()
    total_hours = serializers.FloatField(source='get_total_hours_logged', read_only=True)
    active_hours = serializers.FloatField(source='get_active_hours_logged', read_only=True)
    remaining_budget = serializers.DecimalField(
        source='get_remaining_budget',
        max_digits=12,
        decimal_places=2,
        read_only=True
    )
    completion_percentage = serializers.IntegerField(
        source='get_completion_percentage',
        read_only=True
    )

    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'organization', 'organization_name',
            'start_date', 'end_date', 'status', 'budget_type', 'budget_amount',
            'hourly_rate', 'settings', 'is_billable', 'is_public', 'team_members',
            'team_members_count', 'total_hours', 'active_hours', 'remaining_budget',
            'completion_percentage', 'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_team_members_count(self, obj):
        return obj.team_members.count()


class TaskSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source='project.name', read_only=True)
    assignee_name = serializers.CharField(source='assignee.user.name', read_only=True)
    total_time_spent = serializers.FloatField(source='get_total_time_spent', read_only=True)
    active_time_spent = serializers.FloatField(source='get_active_time_spent', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    status_display = serializers.CharField(read_only=True)
    priority_display = serializers.CharField(read_only=True)
    recent_activity = serializers.SerializerMethodField()

    class Meta:
        model = Task
        fields = [
            'id', 'name', 'description', 'project', 'project_name', 'status',
            'status_display', 'priority', 'priority_display', 'assignee',
            'assignee_name', 'start_date', 'due_date', 'estimated_hours',
            'parent_task', 'dependencies', 'tags', 'category', 'is_billable',
            'completion_percentage', 'total_time_spent', 'active_time_spent',
            'is_overdue', 'recent_activity', 'created_at', 'updated_at', 'created_by'
        ]
        read_only_fields = ['created_at', 'updated_at', 'created_by']

    def get_recent_activity(self, obj):
        return obj.get_recent_activity()


class TaskTimeSerializer(serializers.Serializer):
    task_id = serializers.UUIDField()
    time = serializers.IntegerField(min_value=0)
    description = serializers.CharField(required=False, allow_blank=True)


class ActivityIntervalSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.name', read_only=True)
    tasks_time = serializers.ListField(child=TaskTimeSerializer(), write_only=True)
    tasks_details = serializers.SerializerMethodField()
    verification_details = serializers.SerializerMethodField()
    media_count = serializers.SerializerMethodField()
    projects = serializers.SerializerMethodField()

    class Meta:
        model = ActivityInterval
        fields = [
            'id', 'employee', 'employee_name', 'timestamp', 'is_online',
            'activity_level', 'tasks_time', 'tasks_details', 'projects',
            'screenshots', 'headshots', 'verification_status',
            'verification_details', 'media_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['verification_status', 'created_at', 'updated_at']

    def get_projects(self, obj):
        """Get unique projects from tasks"""
        projects = {}
        for task_id in obj.tasks_time.keys():
            try:
                task = Task.objects.get(id=task_id)
                project_id = str(task.project.id)
                if project_id not in projects:
                    projects[project_id] = {
                        'id': project_id,
                        'name': task.project.name
                    }
            except Task.DoesNotExist:
                continue
        return list(projects.values())

    def get_tasks_details(self, obj):
        tasks_data = {}
        for task_id, details in obj.tasks_time.items():
            try:
                task = Task.objects.get(id=task_id)
                tasks_data[task_id] = {
                    'name': task.name,
                    'project_name': task.project.name,
                    'project_id': str(task.project.id),
                    'time': details['time'],
                    'description': details.get('description', ''),
                    'status': task.status,
                    'status_display': task.status_display,
                    'priority': task.priority,
                    'priority_display': task.priority_display
                }
            except Task.DoesNotExist:
                continue
        return tasks_data

    def get_verification_details(self, obj):
        if not obj.headshots:
            return None

        return {
            'status': obj.verification_status,
            'headshots': [{
                'url': shot['url'],
                'timestamp': shot['timestamp'],
                'status': shot['status'],
                'confidence_score': shot.get('confidence_score', 0),
                'verified_by': shot.get('verified_by', 'system')
            } for shot in obj.headshots]
        }

    def get_media_count(self, obj):
        return {
            'screenshots': len(obj.screenshots),
            'headshots': len(obj.headshots)
        }

    def validate(self, data):
        # Validate activity level
        if data.get('activity_level', 0) < 0 or data.get('activity_level', 0) > 100:
            raise serializers.ValidationError({
                'activity_level': 'Activity level must be between 0 and 100'
            })

        # Validate tasks_time
        tasks_time = data.get('tasks_time', [])
        if not tasks_time:
            raise serializers.ValidationError({
                'tasks_time': 'At least one task is required'
            })

        total_time = sum(item['time'] for item in tasks_time)
        if total_time != 600:  # 10 minutes in seconds
            raise serializers.ValidationError({
                'tasks_time': 'Total task time must equal 10 minutes (600 seconds)'
            })

        # Validate task existence and collect unique projects
        task_ids = [str(item['task_id']) for item in tasks_time]
        tasks = Task.objects.filter(id__in=task_ids).select_related('project')

        if tasks.count() != len(task_ids):
            raise serializers.ValidationError({
                'tasks_time': 'One or more tasks do not exist'
            })

        # Convert tasks_time to storage format
        data['tasks_time'] = {
            str(item['task_id']): {
                'time': item['time'],
                'description': item.get('description', '')
            } for item in tasks_time
        }

        # Validate media
        self._validate_media(data)

        return data

    def _validate_media(self, data):
        """Validate media attachments"""
        screenshots = data.get('screenshots', [])
        for screenshot in screenshots:
            if not isinstance(screenshot, dict) or 'url' not in screenshot:
                raise serializers.ValidationError({
                    'screenshots': 'Each screenshot must have a URL and timestamp'
                })

        headshots = data.get('headshots', [])
        for headshot in headshots:
            if not isinstance(headshot, dict) or 'url' not in headshot:
                raise serializers.ValidationError({
                    'headshots': 'Each headshot must have a URL and timestamp'
                })

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['timestamp'] = instance.timestamp.isoformat()
        time_elapsed = (timezone.now() - instance.timestamp).total_seconds() / 60
        data['minutes_ago'] = int(time_elapsed)
        return data


class ActivityStatsSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee.user.name', read_only=True)
    organization_name = serializers.CharField(
        source='employee.organization.name',
        read_only=True
    )
    projects_breakdown = serializers.SerializerMethodField()
    tasks_breakdown = serializers.SerializerMethodField()
    hourly_activity = serializers.SerializerMethodField()
    daily_metrics = serializers.SerializerMethodField()

    class Meta:
        model = ActivityStats
        fields = [
            'id', 'employee', 'employee_name', 'organization_name', 'date',
            'total_time', 'active_time', 'idle_time', 'average_activity',
            'first_activity', 'last_activity', 'projects_breakdown',
            'tasks_breakdown', 'hourly_activity', 'daily_metrics',
            'week_number', 'month', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_projects_breakdown(self, obj):
        """Format projects summary with additional metrics"""
        return {
            project_id: {
                'name': data['name'],
                'total_hours': round(data['time'] / 3600, 2),
                'active_hours': round(data['active_time'] / 3600, 2),
                'activity_percentage': round((data['active_time'] / data['time'] * 100) if data['time'] > 0 else 0, 2)
            }
            for project_id, data in obj.projects_summary.items()
        }

    def get_tasks_breakdown(self, obj):
        """Format tasks summary with additional metrics"""
        return {
            task_id: {
                'name': data['name'],
                'project_name': data['project_name'],
                'total_hours': round(data['time'] / 3600, 2),
                'active_hours': round(data['active_time'] / 3600, 2),
                'activity_percentage': round((data['active_time'] / data['time'] * 100) if data['time'] > 0 else 0, 2)
            }
            for task_id, data in obj.tasks_summary.items()
        }

    def get_hourly_activity(self, obj):
        """Format hourly breakdown with percentages"""
        return {
            hour: {
                'total_hours': round(data['total_time'] / 3600, 2),
                'active_hours': round(data['active_time'] / 3600, 2),
                'activity_level': round(data['level'], 2)
            }
            for hour, data in obj.hourly_breakdown.items()
        }

    def get_daily_metrics(self, obj):
        """Calculate daily summary metrics"""
        total_hours = round(obj.total_time / 3600, 2)
        active_hours = round(obj.active_time / 3600, 2)
        idle_hours = round(obj.idle_time / 3600, 2)

        return {
            'total_hours': total_hours,
            'active_hours': active_hours,
            'idle_hours': idle_hours,
            'productivity_score': round((obj.active_time / obj.total_time * 100) if obj.total_time > 0 else 0, 2),
            'time_tracked': {
                'start': obj.first_activity.strftime('%H:%M') if obj.first_activity else None,
                'end': obj.last_activity.strftime('%H:%M') if obj.last_activity else None,
                'duration': total_hours
            },
            'activity_level': round(obj.average_activity, 2)
        }


class ActiveAppUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActiveAppUsage
        fields = ['id', 'app_name', 'minutes', 'samples']


class TaskUsageSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskUsage
        fields = ['id', 'task_id', 'project_id', 'minutes', 'timestamp']


class ScreenshotLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ScreenshotLog
        fields = ['id', 'url', 'window_title', 'timestamp']


class HeadshotLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = HeadshotLog
        fields = ["id", "url", "status", "timestamp"]

class TrackingSessionSerializer(serializers.ModelSerializer):
    apps = ActiveAppUsageSerializer(many=True, read_only=True)
    tasks = TaskUsageSerializer(many=True, read_only=True)
    screenshot_logs = ScreenshotLogSerializer(many=True, read_only=True)
    headshot_logs = HeadshotLogSerializer(many=True, read_only=True)

    class Meta:
        model = TrackingSession
        fields = [
            "id", "employee", "date", "is_online",
            "activity_level", "task_time", "active_apps",
            "total_duration", "apps", "tasks",
            "screenshot_logs", "headshot_logs",
            "created_at", "updated_at"
        ]