"""
Audit Log API endpoint.
Serves paginated, filterable audit log data as JSON for the audit.html frontend.
"""
import math
from datetime import datetime, timedelta

from ninja import Router
from django.http import HttpRequest
from django.db.models import Q

from apps.core.models import AuditLog

router = Router()


@router.get("/logs")
def api_logs(
    request: HttpRequest,
    page: int = 1,
    limit: int = 15,
    start_date: str = '',
    end_date: str = '',
    action: str = '',
    user_id: str = '',
    target: str = '',
):
    """
    Paginated audit logs with filtering.
    Called by audit.html via fetch('/api/logs?page=1&limit=15&...').
    """
    try:
        queryset = AuditLog.objects.all()

        # Apply filters
        if action:
            queryset = queryset.filter(action__icontains=action)

        if user_id:
            try:
                queryset = queryset.filter(user_id=int(user_id))
            except (ValueError, TypeError):
                pass

        if target:
            queryset = queryset.filter(
                Q(target__icontains=target) |
                Q(details__icontains=target)
            )

        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                queryset = queryset.filter(timestamp__gte=start_dt)
            except ValueError:
                pass

        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
                queryset = queryset.filter(timestamp__lt=end_dt)
            except ValueError:
                pass

        # Order by most recent first
        queryset = queryset.order_by('-timestamp')

        # Pagination
        total = queryset.count()
        total_pages = max(1, math.ceil(total / limit)) if total else 1
        page = max(1, min(page, total_pages))
        offset = (page - 1) * limit

        logs_raw = queryset[offset:offset + limit]

        # Format for frontend
        logs = []
        for entry in logs_raw:
            logs.append({
                'timestamp': entry.timestamp.strftime('%Y-%m-%d %H:%M:%S') if entry.timestamp else '',
                'user': entry.user.username if entry.user else 'system',
                'action': entry.action or '',
                'target': entry.target or '',
                'details': entry.details or '',
                'ip_address': entry.ip_address or '',
            })

        return {
            'logs': logs,
            'total': total,
            'current_page': page,
            'pages': total_pages,
        }

    except Exception as e:
        return {'error': str(e), 'logs': [], 'total': 0, 'current_page': 1, 'pages': 1}
