-- MySQL schema for Linux via SNMP (no psutil, no SNMPv3, no SNMP conn configs in DB)

CREATE DATABASE IF NOT EXISTS metrics
  DEFAULT CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
USE metrics;

-- devices: chỉ dùng sysname làm identifier chính (static, do admin cấu hình)
CREATE TABLE IF NOT EXISTS devices (
  id INT AUTO_INCREMENT PRIMARY KEY,
  sysname VARCHAR(255) NOT NULL UNIQUE,  -- sys.name từ SNMP (static identifier)
  ip_address VARCHAR(15),                 -- IPv4 only, có thể thay đổi
  last_seen DATETIME(3) NOT NULL,
  online BOOLEAN NOT NULL DEFAULT TRUE,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  INDEX idx_devices_last_seen (last_seen),
  INDEX idx_devices_sysname (sysname)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Tất cả các bảng metrics: đổi device_id thành sysname
-- system_info: mỗi device chỉ có 1 record (latest system info)
CREATE TABLE IF NOT EXISTS system_info (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL UNIQUE,  -- Đổi từ device_id, UNIQUE vì mỗi device chỉ có 1 system info
  sys_location VARCHAR(255),
  sys_uptime INTEGER,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_system_info_sysname_time (sysname, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- load_avg
CREATE TABLE IF NOT EXISTS load_avg (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  load_1m DOUBLE,
  load_5m DOUBLE,
  load_15m DOUBLE,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_load_sysname_time (sysname, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- cpu_percent
CREATE TABLE IF NOT EXISTS cpu_percent (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  cpu VARCHAR(16) NOT NULL,
  percent DOUBLE,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_cpu_percent_sysname_cpu_time (sysname, cpu, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- memory
CREATE TABLE IF NOT EXISTS memory (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  total BIGINT,
  available BIGINT,
  used BIGINT,
  free BIGINT,
  percent DOUBLE,
  buffers BIGINT,
  cached BIGINT,
  shared BIGINT,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_memory_sysname_time (sysname, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- swap_memory
CREATE TABLE IF NOT EXISTS swap_memory (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  total BIGINT,
  used BIGINT,
  free BIGINT,
  percent DOUBLE,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_swap_sysname_time (sysname, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- disk_usage
CREATE TABLE IF NOT EXISTS disk_usage (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,
  mount VARCHAR(255),
  device_partition VARCHAR(255),
  total BIGINT,
  used BIGINT,
  free BIGINT,
  percent DOUBLE,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_disk_usage_sysname_mount_time (sysname, mount, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- disk_io_counters
CREATE TABLE IF NOT EXISTS disk_io_counters (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  disk VARCHAR(128),
  read_count BIGINT,
  write_count BIGINT,
  read_bytes BIGINT,
  write_bytes BIGINT,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_disk_io_sysname_disk_time (sysname, disk, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- net_io_counters
CREATE TABLE IF NOT EXISTS net_io_counters (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,  -- Đổi từ device_id
  if_index INT,
  iface VARCHAR(128),
  if_high_speed_mbps BIGINT,
  if_admin_status INT,
  if_oper_status INT,
  bytes_sent BIGINT,
  bytes_recv BIGINT,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_net_io_sysname_iface_time (sysname, iface, time),
  INDEX idx_net_io_if_index (if_index)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- temperature
CREATE TABLE IF NOT EXISTS temperature (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  time DATETIME(3) NOT NULL,
  sysname VARCHAR(255) NOT NULL,
  cpu_temp DOUBLE,
  FOREIGN KEY (sysname) REFERENCES devices(sysname) ON DELETE CASCADE,
  INDEX idx_temperature_sysname_time (sysname, time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;