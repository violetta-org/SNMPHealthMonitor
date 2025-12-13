from flask import Blueprint, render_template

# Topic to template mapping
TOPIC_TEMPLATES = {
    "systemstatus": "dashboard.html",
    "network": "network.html",
    "disk": "disk.html",
    "diskio": "diskio.html",
}

# Flask Blueprint cho HTTP API
api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/dashboard/<sysname>")
def subscribe_dashboard_default(sysname: str):
    """Subscribe to default topic (systemstatus) and return dashboard template."""
    print(f"[API] Dashboard subscription requested (default): sysname={sysname}")
    return render_template("dashboard.html", sysname=sysname, topic="systemstatus")


@api_bp.route("/dashboard/<sysname>/<topic>")
def subscribe_dashboard(sysname: str, topic: str):
    """Subscribe to a topic and return appropriate template."""
    print(f"[API] Dashboard subscription requested: sysname={sysname}, topic={topic}")

    # Get template name for topic, fallback to dashboard.html if unknown
    template_name = TOPIC_TEMPLATES.get(topic, "dashboard.html")

    if template_name not in TOPIC_TEMPLATES.values():
        print(f"[API] Warning: Unknown topic {topic}, using default template")
        template_name = "dashboard.html"

    return render_template(template_name, sysname=sysname, topic=topic)


