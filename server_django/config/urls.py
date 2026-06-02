"""
URL configuration for SNMPHealthMonitor Django project.
"""
from django.contrib import admin
from django.urls import path, include
from ninja import NinjaAPI

# Initialize Django Ninja API (CSRF is disabled by default for API endpoints)
api = NinjaAPI(
    title="SNMPHealthMonitor API",
    version="2.0.0",
    description="Django Ninja API for SNMP Health Monitoring Dashboard",
)

# Import and register routers from apps
from apps.metrics.api import router as metrics_router
from apps.metrics.ai_api import ai_router
from apps.metrics.ml_api import ml_router
from apps.files.api import router as files_router
from apps.core.api import router as audit_router
# from apps.devices.api import router as devices_router

api.add_router("/", metrics_router, tags=["metrics"])
api.add_router("/", files_router, tags=["files"])
api.add_router("/", audit_router, tags=["audit"])
api.add_router("/ai/", ai_router, tags=["ai-assistant"])
api.add_router("/ml/", ml_router, tags=["ml-prediction"])
# api.add_router("/devices/", devices_router)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', api.urls),
    path('', include('apps.web.urls')),
]
