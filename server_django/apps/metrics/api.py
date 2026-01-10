"""
Metrics API endpoints using Django Ninja.
Ported from: query-service/api/router.py

Implements async API endpoints for SNMP metric data retrieval.
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from ninja import Router

from apps.metrics.schemas import (
    ErrorResponse,
    HistoryMetricsResponse,
)
from apps.metrics.services import (
    get_topic_data as topic_service,
    get_cpu_metrics,
    get_memory_metrics,
    get_disk_metrics,
    get_network_metrics,
    get_temperature_metrics,
    normalize_list,
)

logger = logging.getLogger(__name__)

router = Router(tags=["metrics"])


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def parse_time_range(
    start_time: Optional[datetime],
    end_time: Optional[datetime],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Parse time range from datetime inputs.
    Converts to Local Naive time.
    Ported from: query-service/utils/time_range.py
    """
    if not start_time:
        return None, None
    
    # Convert to Local Naive
    start_dt = start_time.astimezone().replace(tzinfo=None)
    
    if end_time:
        end_dt = end_time.astimezone().replace(tzinfo=None)
    else:
        end_dt = datetime.now()
    
    return start_dt, end_dt


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.get(
    "/data/{sysname}/{topic}",
    summary="Get Topic Data",
    description="""
    Get historical or real-time metric data for a specific topic.
    
    **Topics available:**
    - `systemstatus`: System info, load averages, CPU, memory, temperature
    - `network`: Network I/O rates per interface
    - `disk`: Disk usage per mount point
    - `diskio`: Disk I/O rates per disk
    
    **Modes:**
    - **Snapshot Mode** (no start_time): Returns latest data for real-time dashboard
    - **Range Mode** (with start_time): Returns historical data with automatic downsampling
    """,
    response={200: Dict[str, Any], 400: ErrorResponse, 422: Any, 500: ErrorResponse}
)
async def get_topic_data_api(
    request,
    sysname: str,
    topic: str,
    page: int = 1,
    per_page: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Get historical metric data for a specific topic.
    
    Ported from: query-service/api/router.py::get_topic_data_api
    """
    try:
        start_dt, end_dt = parse_time_range(start_time, end_time)
        
        data = await topic_service(
            sysname=sysname,
            topic=topic,
            page=page,
            per_page=per_page,
            start_time=start_dt,
            end_time=end_dt,
        )
        return data
    except ValueError as ve:
        return 400, {"error": str(ve)}
    except OSError as oe:
        # Handle "Invalid argument" for out-of-range dates on Windows/DB
        return 400, {"error": f"Invalid date/time range: {oe}"}
    except Exception as e:
        logger.exception(f"Error fetching topic data: {e}")
        return 500, {"error": str(e)}


@router.get(
    "/history/metrics/{sysname}",
    summary="Get History Metrics",
    description="""
    Get generic history metrics (JSON) for ApexCharts.
    
    Returns normalized arrays suitable for time-series chart consumption.
    
    **Query Params:**
    - `start_time`: ISO8601 start time
    - `end_time`: ISO8601 end time (defaults to now)
    - `metrics`: Comma-separated list of metrics (cpu,memory,disk,network,temp). Default: all
    """,
    response={200: HistoryMetricsResponse, 400: ErrorResponse, 422: Any, 500: ErrorResponse}
)
async def history_metrics(
    request,
    sysname: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    metrics: str = "cpu,memory,disk,network,temp",
) -> Dict[str, Any]:
    """
    Get generic history metrics for ApexCharts.
    
    Ported from: query-service/api/router.py::history_metrics
    """
    try:
        start_dt, end_dt = parse_time_range(start_time, end_time)
        
        # Default to last 1 hour if not specified
        if not start_dt:
            end_dt = datetime.now()
            start_dt = end_dt - timedelta(hours=1)
        
        requested_metrics = [m.strip().lower() for m in metrics.split(",")]
        
        logger.debug(
            f"API HISTORY: {sysname} range={start_dt}-{end_dt} metrics={requested_metrics}"
        )
        
        data: Dict[str, Any] = {}
        
        if 'cpu' in requested_metrics:
            res = await get_cpu_metrics(sysname, start_dt, end_dt)
            data['cpu'] = normalize_list(res.get('cpu_percent'))
        
        if 'memory' in requested_metrics:
            res = await get_memory_metrics(sysname, start_dt, end_dt)
            data['memory'] = normalize_list(res.get('memory'))
            if 'swap' in res:
                data['swap'] = normalize_list(res.get('swap'))
        
        if 'disk' in requested_metrics:
            res = await get_disk_metrics(sysname, start_dt, end_dt)
            data['disk_usage'] = normalize_list(res.get('disk_usage'))
        
        if 'network' in requested_metrics:
            res = await get_network_metrics(sysname, start_dt, end_dt)
            data['network'] = normalize_list(res.get('network'))
        
        if 'temp' in requested_metrics:
            res = await get_temperature_metrics(sysname, start_dt, end_dt)
            data['temperature'] = normalize_list(res.get('temperature'))
        
        return data
    except ValueError as ve:
        return 400, {"error": str(ve)}
    except OSError as oe:
        return 400, {"error": f"Invalid date/time range: {oe}"}
    except Exception as e:
        logger.exception(f"Error fetching history metrics: {e}")
        return 500, {"error": str(e)}


# =============================================================================
# FUTURE ENDPOINTS (to be implemented as needed)
# =============================================================================
# - GET /api/logs - Audit logs (requires authentication)
# - POST /api/check_exists - File existence check
# - POST /api/upload_chunk - Chunked file upload
# - POST /api/zip - Create zip archive
# - POST /api/unzip - Extract archive
# - POST /api/save - Save file content
