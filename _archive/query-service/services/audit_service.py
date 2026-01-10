import logging
from extensions import db
from db.models import AuditLog

logger = logging.getLogger(__name__)

def log_action(user_id, action, target, details=None, ip_address=None):
    """
    Log a user action to the database.
    
    :param user_id: ID of the user performing the action (can be None).
    :param action: Short string identifying the action (e.g., 'DELETE_FILE').
    :param target: The object being acted upon (e.g., file path).
    :param details: Additional context or details.
    :param ip_address: IP address of the user.
    """
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action=action,
            target=target,
            details=details,
            ip_address=ip_address
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        db.session.rollback()

def get_recent_logs(page=1, per_page=20, start_date=None, end_date=None, action=None, user_id=None, target=None):
    """Fetch recent audit logs with pagination and filtering."""
    query = AuditLog.query

    if start_date:
        query = query.filter(AuditLog.timestamp >= start_date)
    if end_date:
        query = query.filter(AuditLog.timestamp <= end_date)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if target:
        query = query.filter(AuditLog.target.contains(target))

    pagination = query.order_by(AuditLog.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return {
        "items": pagination.items,
        "total": pagination.total,
        "pages": pagination.pages,
        "current_page": page
    }
