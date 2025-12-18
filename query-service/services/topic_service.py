from typing import Optional
from datetime import datetime

from db.queries import (
    get_system_metrics,
    get_cpu_metrics,
    get_memory_metrics,
    get_status_metrics,
    get_network_metrics,
    get_disk_metrics,
    get_disk_io_metrics,
    get_temperature_metrics,
)
from websocket.websocket_manager import ws_manager


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
    print(
        f"[TopicService] Fetching {topic} data for {sysname}, "
        f"page={page}, per_page={per_page}, "
        f"start_time={start_time}, end_time={end_time}"
    )

    try:
        if topic == "systemstatus":
            print(f"[TopicService] Aggregating status (no disk usage) for {sysname}")
            return get_status_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
        elif topic == "network":
            return get_network_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
        elif topic == "disk":
            return get_disk_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time
            )
        elif topic == "diskio":
            return get_disk_io_metrics(
                sysname,
                start_time=start_time,
                end_time=end_time,
                page=page,
                per_page=per_page,
            )
        else:
            print(f"[TopicService] Unknown topic: {topic}")
            return {}
    except Exception as e:
        print(f"[TopicService] Error fetching {topic} data: {e}")
        import traceback
        traceback.print_exc()
        return {}


def stream_topic_data(
    sysname: str,
    topic: str,
    page: int = 1,
    per_page: int = 10,
) -> None:
    """Query database and stream data to subscribed clients (real-time updates, Snapshot Mode)."""
    try:
        print(
            f"[TopicService] Streaming {topic} data for {sysname}, "
            f"page={page}, per_page={per_page}"
        )
        # Real-time updates use Snapshot Mode (no start_time)
        data = get_topic_data(
            sysname,
            topic,
            page=page,
            per_page=per_page,
        )
        ws_manager.stream_data(sysname, topic, data)
        print(f"[TopicService] Successfully streamed {topic} data to clients")
    except Exception as e:
        print(f"[TopicService] Error streaming {topic}: {e}")
        import traceback
        traceback.print_exc()


