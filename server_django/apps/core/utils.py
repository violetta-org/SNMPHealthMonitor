"""
Core utilities shared across apps.
Port common functions from query-service/utils/ here.
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_time_range(
    start_time: Optional[str],
    end_time: Optional[str],
    default_hours: int = 24
) -> Tuple[datetime, datetime]:
    """
    Parse time range from string inputs.
    Ported from: query-service/utils/time_range.py
    """
    now = datetime.now()
    
    if end_time:
        end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
    else:
        end_dt = now
    
    if start_time:
        start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
    else:
        start_dt = end_dt - timedelta(hours=default_hours)
    
    return start_dt, end_dt
