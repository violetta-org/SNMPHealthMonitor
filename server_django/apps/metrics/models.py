"""
Metric models - the core data storage.
Ported from query-service/db/models.py to match existing MySQL schema.

IMPORTANT: All tables use `sysname` as FK (not device_id).
All models have `managed = False` to prevent Django from altering existing tables.

Schema reference: database/snmp_linux_setup.sql
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from apps.devices.models import Device


# =============================================================================
# BASE CLASSES
# =============================================================================

class BaseMetric(models.Model):
    """
    Abstract base class for all metric tables.
    Common fields: id, time, sysname (FK to devices).
    """
    id = models.BigAutoField(primary_key=True)
    time = models.DateTimeField(db_column='time')
    sysname = models.ForeignKey(
        'devices.Device',
        on_delete=models.CASCADE,
        db_column='sysname',
        to_field='sysname',
        related_name='%(class)s_set'
    )

    class Meta:
        abstract = True


# =============================================================================
# SYSTEM INFO
# =============================================================================

class SystemInfo(BaseMetric):
    """
    System information table - one record per device (latest info).
    Maps to 'system_info' table.
    """
    sys_location = models.CharField(max_length=255, null=True, blank=True)
    sys_uptime = models.IntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'system_info'
        verbose_name = 'System Info'
        verbose_name_plural = 'System Info'

    def __str__(self) -> str:
        return f"SystemInfo({self.sysname_id})"


# =============================================================================
# CPU METRICS
# =============================================================================

class LoadAvg(BaseMetric):
    """
    Load average metrics (1m, 5m, 15m).
    Maps to 'load_avg' table.
    """
    load_1m = models.FloatField(null=True, blank=True)
    load_5m = models.FloatField(null=True, blank=True)
    load_15m = models.FloatField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'load_avg'
        verbose_name = 'Load Average'
        verbose_name_plural = 'Load Averages'

    def __str__(self) -> str:
        return f"LoadAvg({self.sysname_id}, {self.load_1m}/{self.load_5m}/{self.load_15m})"


class CpuPercent(BaseMetric):
    """
    Per-CPU usage percentage.
    Maps to 'cpu_percent' table.
    """
    cpu = models.CharField(max_length=16)
    percent = models.FloatField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'cpu_percent'
        verbose_name = 'CPU Percent'
        verbose_name_plural = 'CPU Percents'

    def __str__(self) -> str:
        return f"CPU({self.sysname_id}/{self.cpu}: {self.percent}%)"


# =============================================================================
# MEMORY METRICS
# =============================================================================

class Memory(BaseMetric):
    """
    Physical memory metrics.
    Maps to 'memory' table.
    """
    total = models.BigIntegerField(null=True, blank=True)
    available = models.BigIntegerField(null=True, blank=True)
    used = models.BigIntegerField(null=True, blank=True)
    free = models.BigIntegerField(null=True, blank=True)
    percent = models.FloatField(null=True, blank=True)
    buffers = models.BigIntegerField(null=True, blank=True)
    cached = models.BigIntegerField(null=True, blank=True)
    shared = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'memory'
        verbose_name = 'Memory'
        verbose_name_plural = 'Memory Records'

    def __str__(self) -> str:
        return f"Memory({self.sysname_id}: {self.percent}%)"


class SwapMemory(BaseMetric):
    """
    Swap memory metrics.
    Maps to 'swap_memory' table.
    """
    total = models.BigIntegerField(null=True, blank=True)
    used = models.BigIntegerField(null=True, blank=True)
    free = models.BigIntegerField(null=True, blank=True)
    percent = models.FloatField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'swap_memory'
        verbose_name = 'Swap Memory'
        verbose_name_plural = 'Swap Memory Records'

    def __str__(self) -> str:
        return f"Swap({self.sysname_id}: {self.percent}%)"


# =============================================================================
# DISK METRICS
# =============================================================================

class DiskUsage(BaseMetric):
    """
    Disk usage per mount point.
    Maps to 'disk_usage' table.
    """
    mount = models.CharField(max_length=255, null=True, blank=True)
    device_partition = models.CharField(max_length=255, null=True, blank=True)
    total = models.BigIntegerField(null=True, blank=True)
    used = models.BigIntegerField(null=True, blank=True)
    free = models.BigIntegerField(null=True, blank=True)
    percent = models.FloatField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'disk_usage'
        verbose_name = 'Disk Usage'
        verbose_name_plural = 'Disk Usages'

    def __str__(self) -> str:
        return f"Disk({self.sysname_id}/{self.mount}: {self.percent}%)"


class DiskIoCounters(BaseMetric):
    """
    Disk I/O counters per disk.
    Maps to 'disk_io_counters' table.
    """
    disk = models.CharField(max_length=128, null=True, blank=True)
    read_count = models.BigIntegerField(null=True, blank=True)
    write_count = models.BigIntegerField(null=True, blank=True)
    read_bytes = models.BigIntegerField(null=True, blank=True)
    write_bytes = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'disk_io_counters'
        verbose_name = 'Disk IO Counter'
        verbose_name_plural = 'Disk IO Counters'

    def __str__(self) -> str:
        return f"DiskIO({self.sysname_id}/{self.disk})"


# =============================================================================
# NETWORK METRICS
# =============================================================================

class NetIoCounters(BaseMetric):
    """
    Network I/O counters per interface.
    Maps to 'net_io_counters' table.
    """
    if_index = models.IntegerField(null=True, blank=True)
    iface = models.CharField(max_length=128, null=True, blank=True)
    if_high_speed_mbps = models.BigIntegerField(null=True, blank=True)
    if_admin_status = models.IntegerField(null=True, blank=True)
    if_oper_status = models.IntegerField(null=True, blank=True)
    bytes_sent = models.BigIntegerField(null=True, blank=True)
    bytes_recv = models.BigIntegerField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'net_io_counters'
        verbose_name = 'Network IO Counter'
        verbose_name_plural = 'Network IO Counters'

    def __str__(self) -> str:
        return f"NetIO({self.sysname_id}/{self.iface})"


# =============================================================================
# TEMPERATURE METRICS
# =============================================================================

class Temperature(BaseMetric):
    """
    CPU temperature readings.
    Maps to 'temperature' table.
    """
    cpu_temp = models.FloatField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = 'temperature'
        verbose_name = 'Temperature'
        verbose_name_plural = 'Temperatures'

    def __str__(self) -> str:
        return f"Temp({self.sysname_id}: {self.cpu_temp}°C)"


# =============================================================================
# MODEL REGISTRY (for dynamic access)
# =============================================================================

METRIC_MODELS: dict[str, type[BaseMetric]] = {
    'system_info': SystemInfo,
    'load_avg': LoadAvg,
    'cpu_percent': CpuPercent,
    'memory': Memory,
    'swap_memory': SwapMemory,
    'disk_usage': DiskUsage,
    'disk_io_counters': DiskIoCounters,
    'net_io_counters': NetIoCounters,
    'temperature': Temperature,
}


def get_metric_model(table_name: str) -> type[BaseMetric] | None:
    """Get the model class for a given metric table name."""
    return METRIC_MODELS.get(table_name)
