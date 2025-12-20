from flask import Blueprint, request, jsonify
from datetime import datetime
from typing import Optional
from services.topic_service import get_topic_data
from db.queries import get_cpu_network_combined
from utils.time_range import parse_time_range

api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route("/data/<sysname>/<topic>")
def get_topic_data_api(sysname: str, topic: str):
    try:
        start_time_str = request.args.get("start_time")
        end_time_str = request.args.get("end_time")
        page = int(request.args.get("page", 1))
        per_page = int(request.args.get("per_page", 10))
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )

        data = get_topic_data(
            sysname=sysname,
            topic=topic,
            page=page,
            per_page=per_page,
            start_time=start_time,
            end_time=end_time,
        )
        return jsonify(data)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/cpunetwork/<sysname>")
def get_cpu_network_api(sysname: str):
    """Get combined CPU average and Network rate data for dual-axis chart."""
    try:
        iface = request.args.get("iface")
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        limit = int(request.args.get("limit", 60))
        
        data = get_cpu_network_combined(
            sysname=sysname,
            iface=iface,
            start_time=start_time,
            end_time=end_time,
            limit=limit
        )
        return jsonify(data)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500
