from typing import Dict, Any, Optional
from db.queries import get_device_info
import logging

logger = logging.getLogger(__name__)

class DeviceService:
    """Service for handling device-related operations."""

    @staticmethod
    def get_device_status(sysname: str) -> Dict[str, Any]:
        """
        Get basic device status (online/offline, last seen, IP).
        
        Args:
            sysname: System name identifier
            
        Returns:
            Dict containing device info or empty dict if not found
        """
        try:
            return get_device_info(sysname)
        except Exception as e:
            logger.error(f"Error fetching device status for {sysname}: {e}")
            return {}
