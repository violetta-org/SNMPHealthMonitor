from typing import Optional
from datetime import datetime
from unittest import result
import logging
from db.queries import (
    get_system_metrics,
    get_cpu_metrics,
    get_memory_metrics,
    get_status_metrics,
    get_network_metrics,
    get_disk_metrics,
    get_disk_io_metrics,
    get_temperature_metrics,
    get_cpu_network_combined,
    get_device_info,
)
from websocket.websocket_manager import ws_manager
from utils.logging import configure_logger

logger = configure_logger(__name__)
logger.setLevel(logging.DEBUG)


def get_topic_data(
    sysname: str,
    topic: str,
    page: int = 1,
    per_page: int = 10,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> dict:
    """Fetch data for a specific topic with automatic downsampling.
    
    Args:
        sysname: System name
        topic: Topic name (systemstatus, network, disk, diskio)
        page: Page number for pagination (diskio only, Snapshot Mode only)
        per_page: Items per page (diskio only, Snapshot Mode only)
        start_time: Start time for Range Mode queries (Grafana-like)
        end_time: End time for Range Mode queries (Grafana-like)
    
    Note: 
    - If start_time is provided, Range Mode is used (historical data with automatic downsampling)
    - Otherwise, Snapshot Mode is used (latest data for real-time dashboard)
    - Downsampling is automatically applied based on time range duration (500-1000 points target)
    """
    try:
        if topic == "systemstatus":
            data = get_status_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
            return data
        elif topic == "network":
            data = get_network_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
            data['device_info'] = get_device_info(sysname)
            return data
        elif topic == "disk":
            data = get_disk_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
            data['device_info'] = get_device_info(sysname)
            return data
        elif topic == "diskio":
            data = get_disk_io_metrics(
                sysname,
                page=page,
                per_page=per_page,
                start_time=start_time,
                end_time=end_time
            )
            data['device_info'] = get_device_info(sysname)
            return data
        elif topic == "cpunetwork":
            data = get_cpu_network_combined(
                sysname,
                iface=None,  # Will use first available interface
                start_time=start_time,
                end_time=end_time
            )
            return data
        else:
            logger.debug(f"[TopicService] Unknown topic: {topic}")
            return {}
    except Exception as e:
        logger.error(f"[TopicService] Error fetching {topic} data: {e}", exc_info=True)
        return {}


def stream_topic_data(
    sysname: str,
    topic: str,
    page: int = 1,
    per_page: int = 10,
) -> None:
    """Query database and stream data to subscribed clients (real-time updates, Snapshot Mode)."""
    try:
        # Real-time updates use Snapshot Mode (no start_time)
        data = get_topic_data(
            sysname,
            topic,
            page=page,
            per_page=per_page,
        )
        ws_manager.stream_data(sysname, topic, data)
        logger.debug(f"[TopicService] Successfully streamed {topic} data to clients")
    except Exception as e:
        logger.error(f"[TopicService] Error streaming {topic}: {e}", exc_info=True)
        import traceback
        traceback.print_exc()

