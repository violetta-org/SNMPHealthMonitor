from datetime import datetime
from typing import Dict, Any, List


def serialize_row(row: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Convert datetime objects to ISO format strings."""
    if not row:
        return row
    
    result = {}
    for key, value in row.items():
        # isinstance is used to check if the value is a datetime object
        if isinstance(value, datetime):
            result[key] = value.isoformat()
        else:
            result[key] = value
    return result


def serialize_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert datetime objects in multiple rows to ISO format strings."""
    return [serialize_row(row) for row in rows]

