# Query Results Documentation

Tài liệu mô tả cấu trúc dữ liệu được trả về bởi các hàm trong `queries.py`.

## 1. get_system_metrics()

Trả về thông tin hệ thống và load averages.

### Topic
`"system"`

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "system_info": {
    "sysname": "string",
    "sys_location": "string | null",
    "sys_uptime": "integer | null",
    "time": "datetime"
  },
  "load_avg": {
    "load_1m": "float | null",
    "load_5m": "float | null",
    "load_15m": "float | null"
  }
}
```

### Fields Description

#### system_info
- `sysname`: Tên hệ thống (từ SNMP sys.name)
- `sys_location`: Vị trí hệ thống (từ SNMP sys.location)
- `sys_uptime`: Thời gian uptime tính bằng giây (từ SNMP sys.uptime)
- `time`: Thời gian ghi nhận thông tin hệ thống

#### load_avg
- `load_1m`: Load average 1 phút
- `load_5m`: Load average 5 phút
- `load_15m`: Load average 15 phút

---

## 2. get_cpu_metrics()

Trả về metrics CPU cho từng core.

### Topic
`"cpu"`

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "cpu_percent": [
    {
      "cpu": "string",
      "percent": "float | null"
    }
  ]
}
```

### Fields Description

#### cpu_percent (Array)
- `cpu`: Tên CPU core (ví dụ: "cpu0", "cpu1", "cpu2", ...)
- `percent`: Phần trăm sử dụng CPU của core đó

**Note**: Mảng được sắp xếp theo `cpu` (ORDER BY cpu). Chỉ trả về các cores có data gần đây (time >= cutoff).

---

## 3. get_memory_metrics()

Trả về metrics memory và swap.

### Topic
`"memory"`

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "memory": {
    "total": "integer | null",
    "available": "integer | null",
    "used": "integer | null",
    "free": "integer | null",
    "percent": "float | null",
    "buffers": "integer | null",
    "cached": "integer | null",
    "shared": "integer | null"
  },
  "swap": {
    "total": "integer | null",
    "used": "integer | null",
    "free": "integer | null",
    "percent": "float | null"
  }
}
```

### Fields Description

#### memory
- `total`: Tổng memory (bytes)
- `available`: Memory khả dụng (bytes)
- `used`: Memory đã sử dụng (bytes)
- `free`: Memory trống (bytes)
- `percent`: Phần trăm memory đã sử dụng
- `buffers`: Buffer memory (bytes)
- `cached`: Cached memory (bytes)
- `shared`: Shared memory (bytes)

#### swap
- `total`: Tổng swap memory (bytes)
- `used`: Swap đã sử dụng (bytes)
- `free`: Swap trống (bytes)
- `percent`: Phần trăm swap đã sử dụng

---

## 4. get_network_metrics()

Trả về metrics network I/O cho từng interface.

### Topic
`"network"`

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "net_io": [
    {
      "interface": "string",
      "time": "datetime",
      "bytes_sent": "integer",
      "bytes_recv": "integer",
      "if_oper_status": "integer | null",
      "send_bytes_s": "float",
      "recv_bytes_s": "float"
    }
  ]
}
```

### Fields Description

#### net_io (Array)
- `interface`: Tên network interface (ví dụ: "eth0", "wlan0", ...)
- `time`: Thời gian ghi nhận metrics
- `bytes_sent`: Tổng bytes đã gửi (tích lũy)
- `bytes_recv`: Tổng bytes đã nhận (tích lũy)
- `if_oper_status`: Operational status của interface
- `send_bytes_s`: Tốc độ gửi (bytes/giây) - được tính từ 2 điểm thời gian
- `recv_bytes_s`: Tốc độ nhận (bytes/giây) - được tính từ 2 điểm thời gian

**Note**: Mảng được sắp xếp theo `interface` (ORDER BY iface). Chỉ trả về interfaces có data gần đây (time >= cutoff).

---

## 5. get_disk_metrics()

Trả về disk usage cho từng mount point.

### Topic
`"disk"`

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "disk_usage": [
    {
      "time": "datetime",
      "mount": "string",
      "device_partition": "string | null",
      "total": "integer | null",
      "used": "integer | null",
      "free": "integer | null",
      "percent": "float | null"
    }
  ]
}
```

### Fields Description

#### disk_usage (Array)
- `time`: Thời gian ghi nhận metrics
- `mount`: Mount point (ví dụ: "/", "/home", "/var", ...)
- `device_partition`: Device/partition (ví dụ: "/dev/sda1", "/dev/sda2", ...)
- `total`: Tổng dung lượng (bytes)
- `used`: Dung lượng đã sử dụng (bytes)
- `free`: Dung lượng trống (bytes)
- `percent`: Phần trăm đã sử dụng

**Note**: Trả về bản ghi mới nhất cho mỗi mount point. Chỉ trả về mounts có data gần đây (time >= cutoff).

---

## 6. get_disk_io_metrics()

Trả về disk I/O metrics với tốc độ và IOPS, có pagination.

### Topic
`"diskio"`

**Note**: Topic này hỗ trợ pagination parameters:
- `page`: Số trang (default: 1)
- `per_page`: Số items mỗi trang (default: 10)

### Return Type
```python
Dict[str, Any]
```

### Structure
```json
{
  "disk_io": {
    "data": [
      {
        "disk": "string",
        "time": "datetime",
        "read_bytes": "integer",
        "write_bytes": "integer",
        "read_count": "integer",
        "write_count": "integer",
        "read_bytes_s": "float",
        "write_bytes_s": "float",
        "read_iops": "float",
        "write_iops": "float"
      }
    ],
    "pagination": {
      "page": "integer",
      "per_page": "integer",
      "total": "integer",
      "total_pages": "integer"
    }
  }
}
```

### Fields Description

#### disk_io.data (Array)
- `disk`: Tên disk device (ví dụ: "sda", "sdb", ...)
- `time`: Thời gian ghi nhận metrics
- `read_bytes`: Tổng bytes đã đọc (tích lũy)
- `write_bytes`: Tổng bytes đã ghi (tích lũy)
- `read_count`: Tổng số lần đọc (tích lũy)
- `write_count`: Tổng số lần ghi (tích lũy)
- `read_bytes_s`: Tốc độ đọc (bytes/giây) - được tính từ 2 điểm thời gian
- `write_bytes_s`: Tốc độ ghi (bytes/giây) - được tính từ 2 điểm thời gian
- `read_iops`: Read IOPS (operations/giây) - được tính từ 2 điểm thời gian
- `write_iops`: Write IOPS (operations/giây) - được tính từ 2 điểm thời gian

#### disk_io.pagination
- `page`: Trang hiện tại (1-based)
- `per_page`: Số items mỗi trang
- `total`: Tổng số items (sau khi filter)
- `total_pages`: Tổng số trang

**Note**: 
- Mảng được sắp xếp theo tổng tốc độ I/O giảm dần `(read_bytes_s + write_bytes_s) DESC`
- Tự động filter bỏ các loopback devices, RAM disks, và optical drives (loop*, sr*, ram*, zram*)
- Chỉ trả về disks có data gần đây (time >= cutoff)

---

## Topic Mapping Summary

| Topic | Function | Description |
|-------|----------|-------------|
| `"system"` | `get_system_metrics()` | System info và load averages |
| `"cpu"` | `get_cpu_metrics()` | CPU metrics per core |
| `"memory"` | `get_memory_metrics()` | Memory và swap metrics |
| `"network"` | `get_network_metrics()` | Network I/O metrics |
| `"disk"` | `get_disk_metrics()` | Disk usage metrics |
| `"diskio"` | `get_disk_io_metrics()` | Disk I/O với pagination |

## Common Notes

### Topic Usage

Các topic được sử dụng trong WebSocket API:
- Subscribe: `subscribe:system`, `subscribe:cpu`, `subscribe:memory`, etc.
- Pagination (chỉ cho diskio): `subscribe:diskio:page=1,per_page=10`

### notify_timestamp Parameter

Tất cả các hàm đều nhận parameter `notify_timestamp: Optional[float]`:
- Nếu có `notify_timestamp`: Query từ timestamp đó trừ buffer 30 giây
- Nếu không có (None): Query từ thời gian hiện tại (hoặc trừ 1 phút cho một số hàm)

### Data Types

- `string`: VARCHAR từ database
- `integer`: BIGINT từ database
- `float`: DOUBLE từ database
- `datetime`: DATETIME(3) từ database, được serialize thành string ISO format
- `null`: Giá trị NULL từ database

### Serialization

- `serialize_row()`: Convert single row thành dictionary (hoặc None nếu không có data)
- `serialize_rows()`: Convert multiple rows thành list of dictionaries

### Time Window

Tất cả các queries sử dụng time-based window:
- Filter data theo `time >= cutoff`
- Không giới hạn số lượng điểm dữ liệu, chỉ giới hạn theo thời gian
- Đảm bảo chỉ lấy data gần đây và phù hợp với monitoring real-time

