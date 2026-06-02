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


def log_audit(request=None, action="", target=None, details=None, user_id=None):
    """
    Log an audit action.
    Accepts Django request object or user_id (for WebSockets/background tasks).
    """
    try:
        from apps.core.models import AuditLog, User
        user = None
        ip_address = ""

        if request:
            ip_address = request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0].strip()
            if not ip_address:
                ip_address = request.META.get('REMOTE_ADDR', '')
            if not user_id:
                user_id = request.session.get('user_id')

        if user_id:
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                pass

        AuditLog.objects.create(
            user=user,
            action=action,
            target=target,
            details=details,
            ip_address=ip_address,
        )
    except Exception as e:
        print(f"Failed to log audit: {e}")
