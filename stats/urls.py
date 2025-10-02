from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views
from .views import (
    TodaySessionView,
    SessionHistoryView,
    SessionAppsView,
    SessionScreenshotsView,
    SessionHeadshotsView,
    SessionTasksView
)

router = DefaultRouter()
# Project routes
router.register(r'projects', views.ProjectViewSet, basename='project')

# Task routes
router.register(r'tasks', views.TaskViewSet, basename='task')

# WorkSession routes
router.register(r'sessions', views.ActivityIntervalViewSet, basename='session')

# ActivityStats routes
router.register(r'stats', views.ActivityStatsViewSet, basename='stats')

urlpatterns = [
    path('', include(router.urls)),
    path('payload/', views.PayloadDataProcessView.as_view(), name='payload-data-process'),
    path("tracking-sessions/<str:user_id>/today/", TodaySessionView.as_view(), name="today-session"),
    path("tracking-sessions/<str:user_id>/history/", SessionHistoryView.as_view(), name="session-history"),
    path("tracking-sessions/<int:session_id>/apps/", SessionAppsView.as_view(), name="session-apps"),
    path("tracking-sessions/<int:session_id>/screenshots/", SessionScreenshotsView.as_view(), name="session-screenshots"),
    path("tracking-sessions/<int:session_id>/headshots/", SessionHeadshotsView.as_view(), name="session-headshots"),
    path("tracking-sessions/<int:session_id>/tasks/", SessionTasksView.as_view(), name="session-tasks"),
]