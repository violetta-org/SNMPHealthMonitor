from django.urls import path
from . import views

app_name = 'web'

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login, name='login'),
    path('dashboard/', views.dashboard_default, name='dashboard_default'),
    path('dashboard/<str:sysname>/', views.dashboard_sys, name='dashboard_sys'),
    path('dashboard/<str:sysname>/<str:topic>/', views.dashboard_topic, name='dashboard_topic'),
    path('files/', views.files, name='files'),
    path('files/<path:req_path>', views.files, name='files'),
    path('trash/', views.trash, name='trash'),
    path('system/', views.system, name='system'),
    path('logs/', views.logs_view, name='logs_view'),
    path('logout/', views.logout, name='logout'),
    path('download/backup/', views.download_backup, name='download_backup'),
    path('download/<path:filename>', views.download, name='download'),
    path('edit/<path:req_path>', views.edit, name='edit'),
]
