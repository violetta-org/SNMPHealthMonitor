
import sys
import os
from datetime import datetime

# Add project root to path
sys.path.append(os.getcwd())

from app import app, db
from services.audit_service import log_action, get_recent_logs
from db.models import AuditLog

def verify_audit():
    print("Initializing Flask App Context...")
    with app.app_context():
        print("Creating Database Tables...")
        db.create_all()
        
        print("Testing log_action...")
        try:
            log_action(
                user_id=1,
                action="TEST_ACTION",
                target="test_target",
                details="Verification script test",
                ip_address="127.0.0.1"
            )
            print("Action logged successfully.")
        except Exception as e:
            print(f"FAILED to log action: {e}")
            return

        print("Testing get_recent_logs...")
        logs = get_recent_logs(limit=5)
        if logs:
            print(f"Retrieved {len(logs)} logs.")
            for log in logs:
                print(f"[{log.timestamp}] {log.action}: {log.target} (User: {log.user_id})")
                if log.action == "TEST_ACTION":
                    print("SUCCESS: Found test action log.")
        else:
            print("FAILED: No logs retrieved.")

if __name__ == "__main__":
    verify_audit()
