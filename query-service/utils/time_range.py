from datetime import datetime, timedelta
from typing import Optional, Tuple

def parse_time_range(
    start_time_str: Optional[str],
    end_time_str: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    if not start_time_str:
        return None, None

    # Parse as UTC Aware then convert to Local Naive
    start_time = datetime.fromisoformat(start_time_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    
    if end_time_str:
        end_time = datetime.fromisoformat(end_time_str.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)
    else:
        end_time = datetime.now()

    return start_time, end_time


def get_default_range() -> Tuple[datetime, datetime]:
    """Get default time range (last 1 hour) in local time."""
    end = datetime.now().replace(second=0, microsecond=0)
    start = end - timedelta(hours=1)
    return start, end
