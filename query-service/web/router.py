from flask import Blueprint, render_template, redirect, url_for, request
from utils.time_range import get_default_range


web_bp = Blueprint("web", __name__)

template_map = {
    'systemstatus': 'dashboard.html',
    'network': 'network.html',
    'disk': 'disk.html',
    'diskio': 'diskio.html',
    'history': 'history.html'
}

@web_bp.route("/")
def index():
    # entry point
    return redirect(url_for("web.dashboard_default"))

@web_bp.route("/dashboard")
def dashboard_default():
    return render_template(
        "dashboard.html",
        sysname="raspi-pbl",
        topic="systemstatus"
    )

@web_bp.route("/dashboard/<sysname>")
def dashboard_sys(sysname: str):
    return render_template(
        "dashboard.html",
        sysname=sysname,
        topic="systemstatus"
    )

@web_bp.route("/dashboard/<sysname>/<topic>")
def dashboard_topic(sysname: str, topic: str):
    # Lấy template từ map hoặc fallback
    template_name = template_map.get(topic, "404.html")
    context = {
        "sysname": sysname,
        "topic": topic
    }

    # Inject Device Status (Online/Offline, Last Update)
    try:
        from services.device_service import DeviceService
        device_info = DeviceService.get_device_status(sysname)
        if device_info:
            context["device_info"] = device_info
    except Exception as e:
        print(f"Error fetching device status for header: {e}")

    if topic == "history":
        default_start, default_end = get_default_range()
        start_value = request.args.get("start") or default_start.isoformat(timespec="minutes")
        end_value = request.args.get("end") or default_end.isoformat(timespec="minutes")

        context.update({
            "history_start": start_value,
            "history_end": end_value,
        })
    
    return render_template(
        template_name,  # THÊM tên template
        **context
    )