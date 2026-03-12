"""
URL configuration for SNMPHealthMonitor Django project.
"""
from django.contrib import admin
from django.urls import path, include
from ninja import NinjaAPI

# Initialize Django Ninja API (csrf_exempt because JS fetch calls don't send CSRF tokens)
api = NinjaAPI(
    title="SNMPHealthMonitor API",
    version="2.0.0",
    description="Django Ninja API for SNMP Health Monitoring Dashboard",
    csrf=False,
)

# Import and register routers from apps
from apps.metrics.api import router as metrics_router
from apps.files.api import router as files_router
# from apps.devices.api import router as devices_router

api.add_router("/", metrics_router, tags=["metrics"])
api.add_router("/", files_router, tags=["files"])
# api.add_router("/devices/", devices_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    path('', include('apps.web.urls')),
]
