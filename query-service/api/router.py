from flask import Blueprint, request, jsonify, Response
from datetime import datetime, timedelta
from typing import Optional
from services.topic_service import get_topic_data
from services.plot_service import generate_history_plot_base64
from services.pdf_service import generate_history_pdf
from utils.time_range import parse_time_range


api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.route("/data/<sysname>/<topic>")
def get_topic_data_api(sysname: str, topic: str):
    try:
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


@api_bp.route("/history/plot/<sysname>")
def history_plot(sysname: str):
    """
    Generate a static PNG (base64) for historical CPU percent.
    Params:
      start_time (ISO8601, required)
      end_time   (ISO8601, optional)
      metric     (only 'cpu' supported for now)
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
            return jsonify({"error": "start_time is required"}), 400
        
        # end_time defaults to datetime.now() in parse_time_range if not provided

        metric = request.args.get("metric", "cpu")
        
        from db.queries import (
            get_cpu_metrics,
            get_memory_metrics,
            get_disk_metrics,
            get_network_metrics,
            get_temperature_metrics
        )
        from services.plot_service import (
            generate_history_plot_base64, # CPU default
            generate_memory_plot,
            generate_disk_plot,
            generate_network_plot,
            generate_temp_plot
        )

        result = None
        if metric == 'cpu':
            res = get_cpu_metrics(sysname, start_time, end_time)
            cpu = res.get("cpu_percent")
            result = generate_history_plot_base64(cpu, sysname)
        elif metric == 'memory':
            res = get_memory_metrics(sysname, start_time, end_time)
            mem = res.get("memory")
            result = generate_memory_plot(mem, sysname)
        elif metric == 'disk':
            res = get_disk_metrics(sysname, start_time, end_time)
            disk = res.get("disk_usage")
            result = generate_disk_plot(disk, sysname)
        elif metric == 'network':
            res = get_network_metrics(sysname, start_time, end_time)
            net = res.get("net_io")
            result = generate_network_plot(net, sysname)
        elif metric == 'temp':
            res = get_temperature_metrics(sysname, start_time, end_time)
            temp = res.get("temperature")
            result = generate_temp_plot(temp, sysname)
        else:
            return jsonify({"error": f"Unknown metric: {metric}"}), 400

        if not result:
             return jsonify({"error": f"No data available for {metric}"}), 404

        return jsonify(result)
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/history/metrics/<sysname>")
def history_metrics(sysname: str):
    """
    Get generic history metrics (JSON) for ApexCharts.
    Query Params:
      start_time: ISO8601
      end_time: ISO8601
      metrics: comma-separated list of metrics (cpu,memory,disk,network,temp). Default: all.
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
             # Default to last 1 hour if not specified (Local Time)
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=1)


        metrics_param = request.args.get("metrics", "cpu,memory,disk,network,temp")
        requested_metrics = [m.strip().lower() for m in metrics_param.split(",")]
        
        from db.queries import (
            get_cpu_metrics, 
            get_memory_metrics, 
            get_disk_metrics, 
            get_network_metrics, 
            get_temperature_metrics
        )

        data = {}
        
        from utils.serialize import normalize_list

        if 'cpu' in requested_metrics:
            res = get_cpu_metrics(sysname, start_time, end_time)
            data['cpu'] = normalize_list(res.get('cpu_percent'))

        if 'memory' in requested_metrics:
            res = get_memory_metrics(sysname, start_time, end_time)
            data['memory'] = normalize_list(res.get('memory'))
            if 'swap' in res:
                data['swap'] = normalize_list(res.get('swap'))

        if 'disk' in requested_metrics:
            res = get_disk_metrics(sysname, start_time, end_time)
            data['disk_usage'] = normalize_list(res.get('disk_usage'))

        if 'network' in requested_metrics:
            res = get_network_metrics(sysname, start_time, end_time)
            data['network'] = normalize_list(res.get('net_io'))

        if 'temp' in requested_metrics:
            res = get_temperature_metrics(sysname, start_time, end_time)
            data['temperature'] = normalize_list(res.get('temperature'))
        
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@api_bp.route("/history/export/pdf/<sysname>")
def history_export_pdf(sysname: str):
    """
    Export history report as PDF.
    """
    try:
        start_time, end_time = parse_time_range(
            request.args.get("start_time"),
            request.args.get("end_time"),
        )
        if not start_time:
             # Default to last 24h for report
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=24)


        # 1. Fetch Data
        data = get_topic_data(
            sysname=sysname,
            topic="systemstatus", 
            start_time=start_time,
            end_time=end_time,
        )
        
        # 2. Generate PDF
        pdf_bytes = generate_history_pdf(sysname, data, start_time, end_time)
        
        if not pdf_bytes:
            return Response("Failed to generate PDF (no data?)", status=404)

        # 3. Return File
        filename = f"report-{sysname}-{start_time.strftime('%Y%m%d%H%M')}.pdf"
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
