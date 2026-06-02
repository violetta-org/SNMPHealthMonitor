"""
Pydantic schemas for the Metrics API.
Provides strict request/response validation for Django Ninja.

Ported from: query-service/api/router.py response structures
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, Optional, List, Dict, Union
from pydantic import BaseModel, Field


# =============================================================================
# UTILITY SCHEMAS
# =============================================================================

class DeviceInfoSchema(BaseModel):
    """Device status information."""
    online: bool
    last_seen: Optional[str] = None
    ip_address: Optional[str] = None


class PaginationSchema(BaseModel):
    """Pagination metadata for paginated endpoints."""
    page: int
    per_page: int
    total: int
    total_pages: int


# =============================================================================
# SYSTEM STATUS SCHEMAS
# =============================================================================

class SystemInfoSchema(BaseModel):
    """System information (static device info)."""
    sysname: Optional[str] = None
    sys_location: Optional[str] = None
    sys_uptime: Optional[int] = None


class LoadAvgSchema(BaseModel):
    """Load average metrics."""
    time: Optional[str] = None
    load_1m: Optional[float] = None
    load_5m: Optional[float] = None
    load_15m: Optional[float] = None


class SystemStatusResponse(BaseModel):
    """Response schema for systemstatus topic."""
    system_info: Optional[SystemInfoSchema] = None
    load_avg: Optional[Union[LoadAvgSchema, List[LoadAvgSchema]]] = None
    device_info: Optional[DeviceInfoSchema] = None


# =============================================================================
# CPU SCHEMAS
# =============================================================================

class CpuPercentSchema(BaseModel):
    """Per-CPU usage percentage."""
    cpu: Optional[str] = None
    time: Optional[str] = None
    percent: Optional[float] = None


class CpuMetricsResponse(BaseModel):
    """Response for CPU metrics."""
    cpu_percent: List[CpuPercentSchema] = []


# =============================================================================
# MEMORY SCHEMAS
# =============================================================================

class MemorySchema(BaseModel):
    """Physical memory metrics."""
    time: Optional[str] = None
    total: Optional[int] = None
    available: Optional[int] = None
    used: Optional[int] = None
    free: Optional[int] = None
    percent: Optional[float] = None
    buffers: Optional[int] = None
    cached: Optional[int] = None
    shared: Optional[int] = None


class SwapSchema(BaseModel):
    """Swap memory metrics."""
    time: Optional[str] = None
    total: Optional[int] = None
    used: Optional[int] = None
    free: Optional[int] = None
    percent: Optional[float] = None


class MemoryMetricsResponse(BaseModel):
    """Response for memory metrics."""
    memory: Optional[Union[MemorySchema, List[MemorySchema]]] = None
    swap: Optional[Union[SwapSchema, List[SwapSchema]]] = None
    device_info: Optional[DeviceInfoSchema] = None


# =============================================================================
# NETWORK SCHEMAS
# =============================================================================

class NetworkInterfaceSchema(BaseModel):
    """Network interface metrics."""
    interface: Optional[str] = Field(None, alias="iface")
    iface: Optional[str] = None
    time: Optional[str] = None
    bytes_sent: Optional[int] = None
    bytes_recv: Optional[int] = None
    if_admin_status: Optional[int] = None
    if_oper_status: Optional[int] = None
    send_bytes_s: Optional[float] = None
    recv_bytes_s: Optional[float] = None

    class Config:
        populate_by_name = True


class NetworkMetricsResponse(BaseModel):
    """Response for network metrics."""
    network: List[Dict[str, Any]] = []
    device_info: Optional[DeviceInfoSchema] = None


# =============================================================================
# DISK SCHEMAS
# =============================================================================

class DiskUsageSchema(BaseModel):
    """Disk usage per mount point."""
    mount: Optional[str] = None
    device_partition: Optional[str] = None
    time: Optional[str] = None
    total: Optional[int] = None
    used: Optional[int] = None
    free: Optional[int] = None
    percent: Optional[float] = None


class DiskMetricsResponse(BaseModel):
    """Response for disk usage metrics."""
    disk_usage: List[DiskUsageSchema] = []
    device_info: Optional[DeviceInfoSchema] = None


class DiskIoSchema(BaseModel):
    """Disk I/O metrics."""
    disk: Optional[str] = None
    time: Optional[str] = None
    read_bytes: Optional[int] = None
    write_bytes: Optional[int] = None
    read_bytes_s: Optional[float] = None
    write_bytes_s: Optional[float] = None


class DiskIoPaginatedSchema(BaseModel):
    """Paginated disk I/O data."""
    data: List[DiskIoSchema] = []
    pagination: PaginationSchema


class DiskIoMetricsResponse(BaseModel):
    """Response for disk I/O metrics."""
    disk_io: Union[DiskIoPaginatedSchema, List[DiskIoSchema]] = []
    device_info: Optional[DeviceInfoSchema] = None


# =============================================================================
# TEMPERATURE SCHEMAS
# =============================================================================

class TemperatureSchema(BaseModel):
    """CPU temperature reading."""
    time: Optional[str] = None
    cpu_temp: Optional[float] = None


class TemperatureMetricsResponse(BaseModel):
    """Response for temperature metrics."""
    temperature: Optional[Union[TemperatureSchema, List[TemperatureSchema]]] = None
    device_info: Optional[DeviceInfoSchema] = None


# =============================================================================
# HISTORY METRICS SCHEMAS (ApexCharts)
# =============================================================================

class HistoryMetricsResponse(BaseModel):
    """
    Response for /api/history/metrics/<sysname>.
    Returns normalized arrays for ApexCharts consumption.
    """
    cpu: List[Dict[str, Any]] = []
    memory: List[Dict[str, Any]] = []
    swap: List[Dict[str, Any]] = []
    disk_usage: List[Dict[str, Any]] = []
    network: List[Dict[str, Any]] = []
    temperature: List[Dict[str, Any]] = []


# =============================================================================
# GENERIC TOPIC DATA RESPONSE
# =============================================================================

class TopicDataResponse(BaseModel):
    """
    Generic response for /api/data/<sysname>/<topic>.
    The actual structure depends on the topic.
    """
    # Allow arbitrary data since structure varies by topic
    class Config:
        extra = 'allow'


# =============================================================================
# ERROR SCHEMAS
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    detail: Optional[str] = None

