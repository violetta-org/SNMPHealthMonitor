from flask import Blueprint, render_template, redirect, url_for

web_bp = Blueprint("web", __name__)

template_map = {
    'systemstatus': 'dashboard.html',
    'network': 'network.html',
    'disk': 'disk.html',
    'diskio': 'diskio.html'
}

@web_bp.route("/")
def index():
    # entry point
    return redirect(url_for("web.dashboard_default"))

@web_bp.route("/dashboard")
def dashboard_default():
    return render_template(
        "dashboard.html",
        sysname="viole",
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
    
    return render_template(
        template_name,  # THÊM tên template
        sysname=sysname,
        topic=topic
    )