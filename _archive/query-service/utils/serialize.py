from datetime import datetime
from typing import Dict, Any, List, Union

def serialize_row(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """
    Convert datetime objects to ISO format strings.
    MySQL DATETIME is naive (no timezone), so we assume it's in server's local timezone.
    JavaScript will parse and display in browser's local timezone.
    """
    if not row:
        return row
    
    result = {}
    for key, value in row.items():
        # isinstance is used to check if the value is a datetime object
        if isinstance(value, datetime):
            # MySQL DATETIME is naive (no timezone info)
            # We keep it as-is and let JavaScript handle timezone conversion
            # If there's a timezone mismatch, it's a configuration issue
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert datetime objects in multiple rows to ISO format strings."""
    return [serialize_row(row) for row in rows]


def normalize_list(val: Union[List, Dict, None]) -> List:
    """
    Normalize a value to a list.
    - If None, returns empty list [].
    - If dict, returns list containing that dict [val].
    - If list, returns the list.
    Used for consistent frontend data consumption (ApexCharts expects arrays/time-series).
    """
    if val is None:
        return []
    if isinstance(val, dict):
        return [val]
    return val
