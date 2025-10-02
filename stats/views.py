from django.db.models import Sum, Avg, Q
from django.http import Http404
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from pprint import pprint
from collections import Counter
from .models import Task

from users.models import Employee
from .models import (
    Project, Task, ActivityStats, ActivityInterval
)
from .permissions import IsManagerOrAdmin
from .serializers import (
    ProjectSerializer, TaskSerializer, ActivityStatsSerializer, ActivityIntervalSerializer
)
from .tasks import verify_headshot_task
from django.db import transaction
from .models import TrackingSession, ActiveAppUsage, ScreenshotLog, HeadshotLog, TaskUsage
from rest_framework import generics
from .models import TrackingSession, ActiveAppUsage, TaskUsage, ScreenshotLog, HeadshotLog
from .serializers import (
    TrackingSessionSerializer,
    ActiveAppUsageSerializer,
    TaskUsageSerializer,
    ScreenshotLogSerializer,
    HeadshotLogSerializer
)


class ProjectViewSet(viewsets.ModelViewSet):
    serializer_class = ProjectSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'is_billable', 'is_public']
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at', 'start_date', 'end_date']

#     def get_permissions(self):
#         if self.action in ['list', 'my_daily_projects']:
#             # Both listing and retrieving objects only need IsAuthenticated
#             permission_classes = [{
#   "app_version": "treko-desktop-iced/0.1",
#   "apps": {
#     "active_by_app_sec": {},
#     "session_count": 0,
#     "session_duration_sec": 4
#   },
#   "by_task": [
#     {
#       "effective_sec": 4,
#       "overtime_sec": 0,
#       "recorded_sec": 4,
#       "remaining_task_time_sec": 43192,
#       "task_id": "4dde3ad9-d876-4569-8d4c-4ad82b30cd53",
#       "total_task_time_sec": 43200,
#       "total_worked_time_sec": 8
#     }
#   ],
#   "chunk_count": 1,
#   "chunk_id": "f45e4df7-8995-4fda-b5ea-30d2edf5865e",
#   "generated_at": "2025-09-16T08:27:30.570137570+00:00",
#   "is_partial": true,
#   "media": {
#     "headshots": [],
#     "screenshots": []
#   },
#   "project_id": "9a92974f-8821-4592-ac0d-c536bdc33b17",
#   "stats": {
#     "active_sec": 4,
#     "effective_sec": 4,
#     "idle_sec": 0,
#     "overtime_sec": 0,
#     "recorded_sec": 4
#   },
#   "window": {
#     "end": "2025-09-16T08:27:30.187296639+00:00",
#     "start": "2025-09-16T08:27:26.187296639+00:00"
#   }
# }]
#         else:
#             # All other actions (create, update, partial_update, destroy, etc.)
#             # require IsManagerOrAdmin
#             permission_classes = [IsManagerOrAdmin]
#         return [permission() for permission in permission_classes]

    def get_queryset(self):
        return Project.objects.filter(
            organization=self.request.user.organization
        ).select_related('organization').prefetch_related('team_members')

    @action(detail=False, methods=['get'])
    def my_daily_projects(self, request):
        """
        Returns a list of projects in which the current user is a team member,
        plus tasks they've tracked time for today, the time tracked per task,
        the total time tracked today, and each project’s settings.
        """
        user = request.user
        employee = user.employee  # Adjust if your user->employee logic is different
        today = timezone.now().date()

        # 1. Find all projects where this employee is a team member
        projects_qs = Project.objects.filter(team_members=employee)

        # 2. Get all intervals for this employee today
        intervals_today = ActivityInterval.objects.filter(
            employee=employee,
            timestamp__date=today
        )

        # 3. For easy lookup, we’ll accumulate time per task_id
        #    tasks_time_today = { <task_id_str>: total_seconds }
        tasks_time_today = {}

        for interval in intervals_today:
            for t_id_str, t_data in interval.tasks_time.items():
                tracked_seconds = t_data.get('time', 0)
                tasks_time_today[t_id_str] = tasks_time_today.get(t_id_str, 0) + tracked_seconds

        # 4. Build a mapping of task_id -> (task, project)
        #    so we can see which project each task belongs to.
        #    We only need to consider tasks that are in tasks_time_today
        #    AND belong to the projects we found in #1
        relevant_task_ids = list(tasks_time_today.keys())
        tasks_qs = Task.objects.filter(
            id__in=relevant_task_ids,
            project__in=projects_qs  # only tasks in the user’s projects
        ).select_related('project')

        # Create a dict: {task_id_str: { 'obj': <Task>, 'project': <Project> }}
        tasks_map = {}
        for t in tasks_qs:
            tasks_map[str(t.id)] = {
                'obj': t,
                'project': t.project
            }

        # 5. Now group tasks by Project to build the final structure
        #    We’ll also track total_time_today across all tasks.
        project_data = {}
        total_time_tracked_today = 0

        for t_id_str, total_seconds in tasks_time_today.items():
            # Only include tasks that belong to the user's projects (if not found, skip)
            if t_id_str not in tasks_map:
                continue

            task_obj = tasks_map[t_id_str]['obj']
            project_obj = tasks_map[t_id_str]['project']
            project_id = str(project_obj.id)

            # Initialize project_data if not present
            if project_id not in project_data:
                project_data[project_id] = {
                    'project_id': project_id,
                    'project_name': project_obj.name,
                    'settings': project_obj.settings,  # You mentioned project settings
                    'tasks': [],
                    'total_time_today': 0
                }

            # Add this task’s time
            project_data[project_id]['tasks'].append({
                'task_id': str(task_obj.id),
                'task_name': task_obj.name,
                'time_tracked_today': total_seconds  # seconds
            })
            project_data[project_id]['total_time_today'] += total_seconds
            total_time_tracked_today += total_seconds

        # 6. Convert dict -> list for the response
        projects_list = []
        for proj_id, data in project_data.items():
            projects_list.append({
                'project_id': data['project_id'],
                'project_name': data['project_name'],
                'settings': data['settings'],
                'total_time_today': data['total_time_today'],
                'tasks': data['tasks']
            })

        # 7. Optionally, add projects that had no tracked time today but the user is still a member
        #    If you want them in the response, you can do something like:
        for proj in projects_qs:
            p_id_str = str(proj.id)
            if p_id_str not in project_data:  # means no time was logged
                projects_list.append({
                    'project_id': p_id_str,
                    'project_name': proj.name,
                    'settings': proj.settings,
                    'total_time_today': 0,
                    'tasks': []
                })

        # Final response structure
        return Response({
            'projects': projects_list,
            'total_time_tracked_today': total_time_tracked_today  # in seconds
        })

    def perform_create(self, serializer):
        serializer.save(
            organization=self.request.user.organization,
            created_by=self.request.user
        )

    @action(detail=True, methods=['post'])
    def add_member(self, request, pk=None):
        project = self.get_object()
        employee_id = request.data.get('employee_id')
        if not employee_id:
            return Response({'error': 'employee_id is required'}, status=400)

        project.team_members.add(employee_id)
        return Response(self.get_serializer(project).data)

    @action(detail=True)
    def activity_summary(self, request, pk=None):
        """
        Provide a summary of activity (time, active time, average activity)
        for this project over the last `days` (defaults to 7).
        """
        project = self.get_object()
        days = int(request.query_params.get('days', 7))
        end_date = timezone.now().date()
        start_date = end_date - timezone.timedelta(days=days)

        # Gather all Task IDs under this Project
        task_ids = set(project.tasks.values_list('id', flat=True))

        # Get all ActivityIntervals in the date range
        all_intervals = ActivityInterval.objects.filter(
            timestamp__date__range=[start_date, end_date]
        )

        # Filter down to only intervals that contain at least one of the project's task_ids
        # in their `tasks_time` keys. (Python-level filtering shown here)
        relevant_intervals = []
        for interval in all_intervals:
            # Check if any Task ID in this interval matches a Task ID in the project
            if set(interval.tasks_time.keys()) & set(map(str, task_ids)):
                relevant_intervals.append(interval)

        # Calculate total_time & active_time for the entire project
        total_time = 0
        active_time = 0

        for interval in relevant_intervals:
            # For each task inside this interval, add time if it belongs to this Project
            for t_id_str, data in interval.tasks_time.items():
                if int(t_id_str) in task_ids:
                    t = data.get('time', 0)  # time in seconds
                    total_time += t
                    active_time += int(t * (interval.activity_level / 100))

        # Compute avg_activity at the project level
        if total_time > 0:
            avg_activity = round((active_time / total_time) * 100, 2)
        else:
            avg_activity = 0

        # Calculate per-employee (team) breakdown
        team_activity = {}
        for interval in relevant_intervals:
            employee_id = interval.employee.id
            employee_name = interval.employee.user.name  # or however you access the employee’s name

            if employee_id not in team_activity:
                team_activity[employee_id] = {
                    'name': employee_name,
                    'total_time': 0,
                    'active_time': 0,
                    'avg_activity': 0
                }

            for t_id_str, data in interval.tasks_time.items():
                if int(t_id_str) in task_ids:
                    t = data.get('time', 0)
                    team_activity[employee_id]['total_time'] += t
                    team_activity[employee_id]['active_time'] += int(
                        t * (interval.activity_level / 100)
                    )

        # Compute avg_activity for each team member
        for e_id, e_data in team_activity.items():
            if e_data['total_time'] > 0:
                e_data['avg_activity'] = round(
                    (e_data['active_time'] / e_data['total_time']) * 100, 2
                )

        summary = {
            'total_time': total_time,  # total seconds across all relevant intervals
            'active_time': active_time,  # total active seconds
            'avg_activity': avg_activity,  # % (0 - 100)
            'total_intervals': len(relevant_intervals),
            'team_activity': team_activity
        }

        return Response(summary)


class TaskViewSet(viewsets.ModelViewSet):
    serializer_class = TaskSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'assignee', 'project', 'is_billable']
    search_fields = ['name', 'description', 'tags']
    ordering_fields = ['due_date', 'priority', 'created_at']

    def get_permissions(self):
        if self.action == 'list':
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsManagerOrAdmin]
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        return Task.objects.filter(
            project__organization=self.request.user.organization
        ).select_related('project', 'assignee', 'parent_task')

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        task = self.get_object()
        employee_id = request.data.get('employee_id')
        if not employee_id:
            return Response({'error': 'employee_id is required'}, status=400)

        task.assignee_id = employee_id
        task.save()
        return Response(self.get_serializer(task).data)

    @action(detail=True)
    def recent_activity(self, request, pk=None):
        task = self.get_object()
        days = int(request.query_params.get('days', 7))
        activity = task.get_recent_activity(days)
        return Response(activity)

    @action(detail=True)
    def intervals(self, request, pk=None):
        """Get detailed activity intervals for a task"""
        task = self.get_object()

        # Find intervals where this task appears in tasks_time
        intervals = ActivityInterval.objects.filter(
            tasks_time__has_key=str(task.id)  # Look for task_id in the JSON field
        ).order_by('-timestamp')

        serializer = ActivityIntervalSerializer(intervals, many=True)
        return Response({
            'task_id': str(task.id),
            'task_name': task.name,
            'total_intervals': intervals.count(),
            'intervals': serializer.data
        })


class ActivityIntervalViewSet(viewsets.ModelViewSet):
    """ViewSet for handling ActivityInterval entries."""

    serializer_class = ActivityIntervalSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['employee', 'is_online', 'verification_status']
    ordering_fields = ['timestamp', 'created_at']

    def get_queryset(self):
        """
        Enforce role-based visibility with optimized query.
        Returns filtered queryset based on user role.
        """
        user = self.request.user
        base_qs = ActivityInterval.objects.select_related('employee')

        role_filters = {
            'ADMIN': Q(employee__organization=user.organization),
            'MANAGER': Q(employee=user.employee) | Q(employee__manager=user.employee),
            'EMPLOYEE': Q(employee=user.employee)
        }

        return base_qs.filter(role_filters.get(user.role, Q(employee=user.employee)))

    def _get_employee(self, employee_id=None):
        """
        Get employee based on ID or current user with permission check.
        Returns Employee instance or raises appropriate exception.
        """
        if not employee_id:
            return self.request.user.employee

        try:
            employee = Employee.objects.get(id=employee_id)
            if not self._can_manage_employee(employee):
                raise PermissionDenied("Not authorized for this employee.")
            return employee
        except Employee.DoesNotExist:
            raise NotFound("Employee not found.")

    def _can_manage_employee(self, employee):
        """Check if current user can manage given employee."""
        user = self.request.user
        return any([
            employee == user.employee,
            user.role == 'ADMIN' and employee.organization == user.organization,
            user.role == 'MANAGER' and employee.manager == user.employee
        ])

    def _verify_headshots(self, interval):
        """Queue verification tasks for headshots with URLs."""
        tasks = [(idx, headshot) for idx, headshot in enumerate(interval.headshots)
                 if headshot.get('url')]

        for idx, _ in tasks:
            verify_headshot_task.apply_async(
                args=[interval.id, idx],
                task_id=f"{interval.id}-{idx}"  # Unique task ID
            )

    def perform_create(self, serializer):
        """Create interval with proper employee and trigger verifications."""
        employee = self._get_employee(self.request.data.get('employee'))
        interval = serializer.save(employee=employee, is_online=True)

        self._verify_headshots(interval)
        ActivityStats.update_stats(interval)

    def perform_update(self, serializer):
        """Update interval with permission check."""
        interval = self.get_object()
        if not self._can_manage_employee(interval.employee):
            raise PermissionDenied("Not authorized to update this interval.")
        return serializer.save()

    @action(detail=False)
    def current_activity(self, request):
        """Get most recent online interval for an employee."""
        employee = self._get_employee(request.query_params.get('employee'))

        latest_interval = ActivityInterval.objects.filter(
            employee=employee,
            is_online=True
        ).order_by('-timestamp').first()

        if not latest_interval:
            return Response({'error': 'No recent activity'}, status=404)

        return Response(self.get_serializer(latest_interval).data)

    @action(detail=False, methods=['post'])
    def record_activity(self, request):
        """Record new activity interval and update stats."""
        employee = self._get_employee(request.data.get('employee'))

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        interval = serializer.save(employee=employee, is_online=True)

        stats = ActivityStats.update_stats(interval)

        return Response({
            'interval': self.get_serializer(interval).data,
            'stats': ActivityStatsSerializer(stats).data
        }, status=201)

    @action(detail=False)
    def daily_timeline(self, request):
        """Get all intervals for a specific date."""
        employee = self._get_employee(request.query_params.get('employee'))
        date_str = request.query_params.get('date')

        try:
            date = (timezone.datetime.strptime(date_str, '%Y-%m-%d').date()
                    if date_str else timezone.now().date())
        except ValueError:
            return Response(
                {'error': 'Invalid date format. Use YYYY-MM-DD.'},
                status=400
            )

        intervals = self.get_queryset().filter(
            employee=employee,
            timestamp__date=date
        ).order_by('timestamp')

        return Response(self.get_serializer(intervals, many=True).data)

    @action(detail=True, methods=['POST'])
    def reverify_headshots(self, request, pk=None):
        """Manually trigger headshot verification."""
        interval = self.get_object()
        self._verify_headshots(interval)
        return Response({
            'status': 'Verification tasks queued',
            'headshot_count': len(interval.headshots)
        })


class ActivityStatsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only ViewSet for ActivityStats. Stats are automatically
    updated via ActivityInterval creation.
    """
    serializer_class = ActivityStatsSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]

    # Fields available in your model: date, week_number, month, employee, etc.
    filterset_fields = ['date', 'week_number', 'month', 'employee']
    ordering_fields = ['date', 'total_time', 'active_time', 'idle_time']

    def get_queryset(self):
        """
        Role-based visibility:
        - ADMIN: all stats in the same organization.
        - MANAGER: own stats + direct reports.
        - EMPLOYEE: only their own.
        """
        user = self.request.user
        qs = ActivityStats.objects.select_related('employee')

        if user.role == 'ADMIN':
            return qs.filter(employee__organization=user.organization)

        if user.role == 'MANAGER':
            return qs.filter(
                Q(employee=user.employee) |
                Q(employee__manager=user.employee)
            )

        return qs.filter(employee=user.employee)

    @action(detail=False, methods=['get'], url_path='today')
    def today(self, request):
        """
        Get today's stats for a given employee or the current user.
        """
        employee = self._get_employee(request.query_params.get('employee'))
        stats = ActivityStats.objects.filter(
            employee=employee, date=timezone.now().date()
        ).first()

        if not stats:
            return Response({'error': 'No stats for today'}, status=404)

        return Response(self.get_serializer(stats).data)

    @action(detail=False, methods=['get'], url_path='summary')
    def summary(self, request):
        """
        Aggregated stats over a date range (start_date, end_date).
        """
        employee = self._get_employee(request.query_params.get('employee'))
        queryset = ActivityStats.objects.filter(employee=employee)

        start_date = request.query_params.get('start_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)

        end_date = request.query_params.get('end_date')
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        # Sum or average only the fields that actually exist in your model
        stats = queryset.aggregate(
            total_time=Sum('total_time'),
            active_time=Sum('active_time'),
            idle_time=Sum('idle_time'),
            avg_activity=Avg('average_activity')
        )

        # Compute derived metrics
        total_time = stats['total_time'] or 0
        active_time = stats['active_time'] or 0
        idle_time = stats['idle_time'] or 0
        avg_activity = stats['avg_activity'] or 0

        return Response({
            'employee_id': employee.id,
            'employee_name': employee.user.name,
            'total_hours': round(total_time / 3600, 2),
            'active_hours': round(active_time / 3600, 2),
            'idle_hours': round(idle_time / 3600, 2),
            'average_activity': round(avg_activity, 2),
        })

    @action(detail=False, methods=['get'], url_path='weekly')
    def weekly(self, request):
        """
        Get weekly activity summary.
        Accepts `week` and `year` query params.
        """
        employee = self._get_employee(request.query_params.get('employee'))
        week = request.query_params.get('week')
        year = request.query_params.get('year')

        queryset = ActivityStats.objects.filter(employee=employee)
        if week and year:
            queryset = queryset.filter(week_number=week, date__year=year)

        stats = queryset.aggregate(
            total_time=Sum('total_time'),
            active_time=Sum('active_time'),
            idle_time=Sum('idle_time'),
            avg_activity=Avg('average_activity')
        )

        total_time = stats['total_time'] or 0
        active_time = stats['active_time'] or 0

        return Response({
            'employee_id': employee.id,
            'employee_name': employee.user.name,
            'week': week,
            'year': year,
            'total_hours': round(total_time / 3600, 2),
            'active_hours': round(active_time / 3600, 2),
            'idle_hours': round((stats['idle_time'] or 0) / 3600, 2),
            'average_activity': round(stats['avg_activity'] or 0, 2),
            'productivity': round(active_time / (total_time or 1) * 100, 2)
        })

    @action(detail=False, methods=['get'], url_path='daily-breakdown')
    def daily_breakdown(self, request):
        """
        Get daily stats for each date in a range.
        """
        employee = self._get_employee(request.query_params.get('employee'))
        queryset = ActivityStats.objects.filter(employee=employee)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        daily_stats = queryset.values('date').annotate(
            total_hours=Sum('total_time') / 3600.0,
            active_hours=Sum('active_time') / 3600.0,
            idle_hours=Sum('idle_time') / 3600.0,
            avg_activity=Avg('average_activity')
        ).order_by('date')

        return Response({
            'employee_id': employee.id,
            'employee_name': employee.user.name,
            'stats': list(daily_stats)
        })

    @action(detail=False, methods=['get'], url_path='team-summary')
    def team_summary(self, request):
        """
        Summaries for an entire team. Only MANAGER/ADMIN can view.
        """
        user = request.user
        if user.role not in ['MANAGER', 'ADMIN']:
            raise PermissionDenied("Only managers and admins can view team summary.")

        # Find employees in the manager’s team or the admin’s entire organization
        if user.role == 'ADMIN':
            team_members = Employee.objects.filter(organization=user.organization)
        else:
            team_members = Employee.objects.filter(manager=user.employee)

        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        team_stats = []
        for member in team_members:
            queryset = ActivityStats.objects.filter(employee=member)
            if start_date:
                queryset = queryset.filter(date__gte=start_date)
            if end_date:
                queryset = queryset.filter(date__lte=end_date)

            agg = queryset.aggregate(
                total_time=Sum('total_time'),
                active_time=Sum('active_time'),
                idle_time=Sum('idle_time'),
                avg_activity=Avg('average_activity')
            )

            if agg['total_time']:
                total_time = agg['total_time'] or 0
                active_time = agg['active_time'] or 0
                idle_time = agg['idle_time'] or 0
                avg_activity = agg['avg_activity'] or 0

                team_stats.append({
                    'employee_id': member.id,
                    'employee_name': member.user.name,
                    'total_hours': round(total_time / 3600, 2),
                    'active_hours': round(active_time / 3600, 2),
                    'idle_hours': round(idle_time / 3600, 2),
                    'average_activity': round(avg_activity, 2),
                    'productivity': round(active_time / (total_time or 1) * 100, 2),
                })

        return Response({
            'team_size': len(team_members),
            'active_members': len(team_stats),
            'team_stats': team_stats
        })

    def _get_employee(self, employee_id=None):
        """
        Helper to retrieve employee by ID (or default to current user’s employee).
        Ensures the requesting user has permission to view the data.
        """
        user = self.request.user

        if not employee_id:
            return user.employee  # default

        try:
            employee = Employee.objects.get(id=employee_id)
        except Employee.DoesNotExist:
            raise Http404("Employee not found.")

        # Admin can see any employee in their organization
        if user.role == 'ADMIN':
            if employee.organization != user.organization:
                raise PermissionDenied("Not in the same organization.")
            return employee

        # Manager can see themselves + direct reports
        if user.role == 'MANAGER':
            if employee != user.employee and employee.manager != user.employee:
                raise PermissionDenied("Not your direct report.")
            return employee

        # Regular employee can only see themselves
        if employee != user.employee:
            raise PermissionDenied("Cannot view other employees.")

        return employee


class PayloadDataProcessView(APIView):
    """
    Accepts payload every 10 minutes, logs activity, apps, screenshots, headshots, tasks.
    """

    def post(self, request, *args, **kwargs):
        payload = request.data
        print("[DEBUG]: ", payload)
        user_id = payload.get("user_id")
        if not user_id:
            return Response({"error": "user_id missing"}, status=status.HTTP_400_BAD_REQUEST)

        # Extract fields from new payload structure
        app_version = payload.get("app_version", "")
        project_id = payload.get("project_id")
        chunk_id = payload.get("chunk_id")
        is_partial = payload.get("is_partial", False)
        generated_at = payload.get("generated_at")
        
        # Extract stats
        stats = payload.get("stats", {})
        active_sec = stats.get("active_sec", 0)
        effective_sec = stats.get("effective_sec", 0)
        idle_sec = stats.get("idle_sec", 0)
        overtime_sec = stats.get("overtime_sec", 0)
        recorded_sec = stats.get("recorded_sec", 0)
        
        # Extract app usage
        apps_data = payload.get("apps", {})
        active_by_app_sec = apps_data.get("active_by_app_sec", {})
        session_count = apps_data.get("session_count", 0)
        session_duration_sec = apps_data.get("session_duration_sec", 0)
        
        # Extract media
        media = payload.get("media", {})
        screenshots = media.get("screenshots", [])
        headshots = media.get("headshots", [])
        
        # Extract window time range
        window = payload.get("window", {})
        window_start = window.get("start")
        window_end = window.get("end")
        
        # Extract task data
        tasks_data = payload.get("by_task", [])
        
        # Get current date
        today = timezone.now().date()

        try:
            with transaction.atomic():
                # Find or create daily tracking session
                session, _ = TrackingSession.objects.get_or_create(
                    employee_id=user_id,
                    date=today,
                    defaults={"is_online": True},
                )

                # Update session with new payload data
                session.app_version = app_version
                session.project_id = project_id
                
                # Update stats
                session.active_sec += active_sec
                session.effective_sec += effective_sec
                session.idle_sec += idle_sec
                session.overtime_sec += overtime_sec
                session.recorded_sec += recorded_sec
                
                # Calculate activity level as percentage
                if recorded_sec > 0:
                    session.activity_level = round((active_sec / recorded_sec) * 100)
                
                # Update window times if provided
                if window_start:
                    session.window_start = window_start if not session.window_start else min(session.window_start, window_start)
                if window_end:
                    session.window_end = window_end if not session.window_end else max(session.window_end, window_end)
                
                # Update app usage data
                session.app_session_count += session_count
                session.app_session_duration_sec += session_duration_sec
                
                # Merge active_by_app_sec into session
                for app_name, seconds in active_by_app_sec.items():
                    if app_name in session.active_by_app_sec:
                        session.active_by_app_sec[app_name] += seconds
                    else:
                        session.active_by_app_sec[app_name] = seconds
                
                # Update total duration
                session.total_duration += recorded_sec
                
                # Save session
                session.save()

                # Save ActiveAppUsage
                app_objects = []
                for app_name, seconds in active_by_app_sec.items():
                    app_objects.append(
                        ActiveAppUsage(
                            session=session,
                            app_name=app_name,
                            seconds=seconds,
                            minutes=round(seconds / 60, 2),  # Convert to minutes for backward compatibility
                            samples=1,  # Default to 1 for backward compatibility
                            chunk_id=chunk_id,
                        )
                    )
                if app_objects:
                    ActiveAppUsage.objects.bulk_create(app_objects)

                # Save TaskUsage
                task_objects = []
                for task_data in tasks_data:
                    task_objects.append(
                        TaskUsage(
                            session=session,
                            task_id=task_data.get("task_id"),
                            project_id=project_id,  # Use the project_id from the payload
                            effective_sec=task_data.get("effective_sec", 0),
                            overtime_sec=task_data.get("overtime_sec", 0),
                            recorded_sec=task_data.get("recorded_sec", 0),
                            remaining_task_time_sec=task_data.get("remaining_task_time_sec", 0),
                            total_task_time_sec=task_data.get("total_task_time_sec", 0),
                            total_worked_time_sec=task_data.get("total_worked_time_sec", 0),
                            minutes=round(task_data.get("recorded_sec", 0) / 60, 2),  # Convert to minutes for backward compatibility
                            chunk_id=chunk_id,
                        )
                    )
                if task_objects:
                    TaskUsage.objects.bulk_create(task_objects)

                # Save Screenshot logs
                screenshot_objs = [
                    ScreenshotLog(
                        session=session,
                        url=item["url"] if isinstance(item, dict) else item,
                        window_title=item.get("window_title", "") if isinstance(item, dict) else "",
                        timestamp=item.get("timestamp", timezone.now()) if isinstance(item, dict) else timezone.now(),
                    )
                    for item in screenshots
                ]
                if screenshot_objs:
                    ScreenshotLog.objects.bulk_create(screenshot_objs)

                # Save Headshot logs
                headshot_objs = [
                    HeadshotLog(
                        session=session,
                        url=item["url"] if isinstance(item, dict) else item,
                        status=item.get("status", "active") if isinstance(item, dict) else "active",
                        timestamp=item.get("timestamp", timezone.now()) if isinstance(item, dict) else timezone.now(),
                    )
                    for item in headshots
                ]
                if headshot_objs:
                    HeadshotLog.objects.bulk_create(headshot_objs)

            return Response({"message": "Payload processed successfully"}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# 1. Today’s session
class TodaySessionView(generics.RetrieveAPIView):
    serializer_class = TrackingSessionSerializer

    def get_object(self):
        user_id = self.kwargs["user_id"]
        today = timezone.now().date()
        return TrackingSession.objects.filter(employee_id=user_id, date=today).first()


# 2. History (list of past sessions)
class SessionHistoryView(generics.ListAPIView):
    serializer_class = TrackingSessionSerializer

    def get_queryset(self):
        user_id = self.kwargs["user_id"]
        return TrackingSession.objects.filter(employee_id=user_id).order_by("-date")


# 3. Apps detail
class SessionAppsView(generics.ListAPIView):
    serializer_class = ActiveAppUsageSerializer

    def get_queryset(self):
        session_id = self.kwargs["session_id"]
        return ActiveAppUsage.objects.filter(session_id=session_id)


# 4. Screenshots list
class SessionScreenshotsView(generics.ListAPIView):
    serializer_class = ScreenshotLogSerializer

    def get_queryset(self):
        session_id = self.kwargs["session_id"]
        return ScreenshotLog.objects.filter(session_id=session_id).order_by("timestamp")


# 5. Headshots list
class SessionHeadshotsView(generics.ListAPIView):
    serializer_class = HeadshotLogSerializer

    def get_queryset(self):
        session_id = self.kwargs["session_id"]
        return HeadshotLog.objects.filter(session_id=session_id).order_by("timestamp")


# 6. Tasks breakdown
class SessionTasksView(generics.ListAPIView):
    serializer_class = TaskUsageSerializer

    def get_queryset(self):
        session_id = self.kwargs["session_id"]
        return TaskUsage.objects.filter(session_id=session_id)
