"""Entry point for `python -m manager`.
"""
import os
import sys

# Setup project root path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db_service.db_config import ensure_db_ready
from .manager import main as manager_main
from .config_prompt import prompt_config_interactive


def check_prerequisites():
    """Kiểm tra database trước khi chạy main."""
    print("[Manager] Checking database readiness...")
    ensure_db_ready()
    print("[Manager] Database ready")


if __name__ == '__main__':
    try:
        prompt_config_interactive()  # Đã tự lưu vào _config_dict rồi
        check_prerequisites()
        manager_main()
    except KeyboardInterrupt:
        print("\n[Manager] Interrupted by user")
        sys.exit(0)
    except Exception as e:
        print(f"[ERROR] Failed to start: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
