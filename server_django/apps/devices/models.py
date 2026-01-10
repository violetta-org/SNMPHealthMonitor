"""
Device models.
Ported from query-service/db/models.py to match existing MySQL schema.
"""
from django.db import models


class Device(models.Model):
    """
    Represents an SNMP-monitored device.
    Maps to existing 'devices' table in MySQL.
    
    Schema reference (database/snmp_linux_setup.sql):
    - sysname is the primary identifier (UNIQUE, used as FK in metric tables)
    - ip_address is IPv4 only, can change
    - last_seen tracks device activity
    - online flag for quick status check
    """
    id = models.AutoField(primary_key=True)
    sysname = models.CharField(
        max_length=255, 
        unique=True, 
        db_index=True,
        help_text="System name from SNMP (static identifier)"
    )
    ip_address = models.CharField(
        max_length=15, 
        null=True, 
        blank=True,
        help_text="IPv4 address (may change dynamically)"
    )
    last_seen = models.DateTimeField(
        db_column='last_seen',
        help_text="Last time device was seen online"
    )
    online = models.BooleanField(
        default=True,
        help_text="Device online status"
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_column='created_at'
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        db_column='updated_at'
    )

    class Meta:
        managed = False  # Do NOT alter existing table
        db_table = 'devices'
        verbose_name = 'Device'
        verbose_name_plural = 'Devices'
        indexes = [
            models.Index(fields=['last_seen'], name='idx_devices_last_seen'),
            models.Index(fields=['sysname'], name='idx_devices_sysname'),
        ]

    def __str__(self) -> str:
        return f"{self.sysname} ({'online' if self.online else 'offline'})"

    @property
    def is_online(self) -> bool:
        """Alias for online status."""
        return self.online
