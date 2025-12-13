from typing import Optional

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
    notify_timestamp: Optional[float] = None,
    page: int = 1,
    per_page: int = 10,
) -> dict:
    """Fetch data for a specific topic."""
    print(
        f"[TopicService] Fetching {topic} data for {sysname}, "
        f"notify_timestamp={notify_timestamp}, page={page}, per_page={per_page}"
    )

    try:
        if topic == "systemstatus":
            print(f"[TopicService] Aggregating status (no disk usage) for {sysname}")
            return get_status_metrics(sysname, notify_timestamp=notify_timestamp)
        elif topic == "network":
            return get_network_metrics(sysname, notify_timestamp=notify_timestamp)
        elif topic == "disk":
            return get_disk_metrics(sysname, notify_timestamp=notify_timestamp)
        elif topic == "diskio":
            return get_disk_io_metrics(
                sysname,
                notify_timestamp=notify_timestamp,
                page=page,
                per_page=per_page,
            )
        else:
            print(f"[TopicService] Unknown topic: {topic}")
            return {}
    except Exception as e:
        print(f"[TopicService] Error fetching {topic} data: {e}")
        return {}


def stream_topic_data(
    sysname: str,
    topic: str,
    notify_timestamp: Optional[float] = None,
    page: int = 1,
    per_page: int = 10,
) -> None:
    """Query database and stream data to subscribed clients."""
    try:
        print(
            f"[TopicService] Streaming {topic} data for {sysname}, "
            f"notify_timestamp={notify_timestamp}, page={page}, per_page={per_page}"
        )
        data = get_topic_data(
            sysname,
            topic,
            notify_timestamp=notify_timestamp,
            page=page,
            per_page=per_page,
        )
        ws_manager.stream_data(sysname, topic, data)
        print(f"[TopicService] Successfully streamed {topic} data to clients")
    except Exception as e:
        print(f"[TopicService] Error streaming {topic}: {e}")


