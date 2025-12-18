from flask import Blueprint, render_template, request, jsonify
from datetime import datetime
from typing import Optional
from services.topic_service import get_topic_data

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


@api_bp.route("/data/<sysname>/<topic>")
def get_topic_data_api(sysname: str, topic: str):
    """
    REST API endpoint to fetch topic data.
    Supports both Snapshot Mode (default) and Range Mode (with query parameters).
    
    Query Parameters:
    - start_time: ISO format datetime string (e.g., "2025-12-14T01:00:00")
    - end_time: ISO format datetime string (defaults to now if start_time provided)
    - page: Page number for pagination (diskio only, Snapshot Mode only, default: 1)
    - per_page: Items per page (diskio only, Snapshot Mode only, default: 10)
    
    Examples:
    - GET /api/data/viole/systemstatus (Snapshot Mode - latest data)
    - GET /api/data/viole/systemstatus?start_time=2025-12-14T01:00:00&end_time=2025-12-14T02:00:00 (Range Mode with automatic downsampling)
    """
    try:
        # Parse query parameters
        start_time_str = request.args.get("start_time")
        end_time_str = request.args.get("end_time")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        
        # Parse datetime strings
        start_time: Optional[datetime] = None
        end_time: Optional[datetime] = None
        
        if start_time_str:
            try:
                start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00"))
                if end_time_str:
                    end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00"))
                else:
                    end_time = datetime.now()
            except ValueError as e:
                return jsonify({"error": f"Invalid datetime format: {e}"}), 400
        
        print(
            f"[API] GET /data/{sysname}/{topic}, "
            f"start_time={start_time}, end_time={end_time}, "
            f"page={page}, per_page={per_page}"
        )
        
        # Fetch data (automatic downsampling applied in Range Mode)
        data = get_topic_data(
            sysname=sysname,
            topic=topic,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
        )
        
        return jsonify(data)
    except Exception as e:
        print(f"[API] Error fetching data for {sysname}/{topic}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


