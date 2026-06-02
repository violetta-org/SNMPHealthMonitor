"""Entry point for `python -m manager`."""
import os
import sys

# Setup project root path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from utils.logging import configure_logger
from manager.manager import main as manager_main
from manager.config_prompt import prompt_config_interactive

logger = configure_logger(__name__)

def check_prerequisites():
    """Decoupled edge-node execution mode."""
    logger.info("Running in decoupled edge mode. Direct DB checks bypassed.")

if __name__ == '__main__':
    try:
        prompt_config_interactive()
        check_prerequisites()
        manager_main()
    except KeyboardInterrupt:
        logger.info("Manager stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to start: {e}", exc_info=True)
        sys.exit(1)
