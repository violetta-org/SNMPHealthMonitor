from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import HttpResponseNotFound
from apps.devices.models import Device
from apps.core.utils import parse_time_range

TEMPLATE_MAP = {
    'systemstatus': 'dashboard.html',
    'network': 'network.html',
    'disk': 'disk.html',
    'diskio': 'diskio.html',
    'history': 'history.html'
}

def index(request):
    """Landing page or redirect to dashboard/login."""
    # Mimic Flask logic: if not authorized, could redirect to login.
    # For now, just render index if exists, or redirect to dashboard.
    return render(request, 'index.html')

def login(request):
    """Login page."""
    if request.method == 'POST':
        # Auth logic placeholder
        # For prototype, allow any post to redirect to dashboard
        return redirect('web:dashboard_default')
    return render(request, 'login.html')

def dashboard_default(request):
    """Default dashboard view."""
    return render(request, "dashboard.html", {
            "sysname": "osboxes", 
            "topic": "systemstatus"
        })

def dashboard_sys(request, sysname):
    """Dashboard for specific system."""
    return render(request, "dashboard.html", {
            "sysname": sysname, 
            "topic": "systemstatus"
        })

def dashboard_topic(request, sysname, topic):
    """Dashboard detail views."""
    template_name = TEMPLATE_MAP.get(topic, "404.html")
    
    if template_name == "404.html":
         return render(request, "404.html", status=404)

    context = {
        "sysname": sysname,
        "topic": topic
    }

    # Inject Device Status
    try:
        device = Device.objects.get(sysname=sysname)
        context["device_info"] = {
            "name": device.sysname,
            "status": "online" if device.online else "offline",
            "online": device.online,
            "last_seen": device.last_seen.isoformat() if device.last_seen else None
        }
    except Device.DoesNotExist:
        context["device_info"] = {"status": "unknown"}
    except Exception as e:
        print(f"Error fetching device status: {e}")

    if topic == "history":
        start_str = request.GET.get("start")
        end_str = request.GET.get("end")
        start_dt, end_dt = parse_time_range(start_str, end_str)

        context.update({
            "history_start": start_dt.isoformat(timespec="minutes"),
            "history_end": end_dt.isoformat(timespec="minutes"),
        })
    
    return render(request, template_name, context)

def files(request, req_path=None):
    return render(request, "files.html", {"home_label": "Home", "crumb": {"path": "", "name": "Home"}, "parent_path": None, "current_path": ""})

def trash(request):
    return render(request, "trash.html")

def system(request):
    return render(request, "system.html")

def logs_view(request):
    return render(request, "audit.html")

def logout(request):
    return redirect('web:index')

def download_backup(request):
    return redirect('web:index')

def download(request, filename):
    return redirect('web:index')

def edit(request, req_path):
    return render(request, "edit.html", {"parent_path": None})
