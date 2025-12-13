"""Data retention manager - deletes old metrics from component tables."""

import pymysql as MySQLdb
import time
from datetime import datetime, timedelta


class RetentionManager:
    """Manages data retention policy with configurable periods per metric type."""
    
    def __init__(self, db_config: dict, retention_config: dict = None):
        """
        Initialize retention manager.
        
        Args:
            db_config: MySQL connection parameters
            retention_config: Dict with retention periods in minutes for each table
                             Default: 24 hours for all tables, 7 days for system_info
        """
        self.db_config = db_config
        
        # Default retention periods (in minutes)
        default_retention = {
            'load_avg': 1440,           # 24 hours
            'cpu_percent': 1440,        # 24 hours  
            'memory': 1440,             # 24 hours
            'swap_memory': 1440,        # 24 hours
            'disk_usage': 1440,         # 24 hours
            'disk_io_counters': 1440,  # 24 hours
            'net_io_counters': 1440,   # 24 hours
            'temperature': 1440,        # 24 hours
            'system_info': 10080,       # 7 days (keep latest per device)
        }
        
        self.retention_config = retention_config or default_retention
        
        self.conn = MySQLdb.connect(**db_config)
        self.conn.autocommit(True)
        
        print(f"[DEBUG] RetentionManager initialized with config: {self.retention_config}")
    
    def cleanup_old_metrics(self):
        """
        Delete metrics older than retention period for each table.
        
        Returns:
            dict: Number of deleted rows per table
        """
        try:
            cursor = self.conn.cursor()
            results = {}
            total_deleted = 0
            
            print(f"[DEBUG] RetentionManager: starting cleanup with config: {self.retention_config}")
            
            for table, retention_minutes in self.retention_config.items():
                if table == 'system_info':
                    # Special handling for system_info - keep only latest per device
                    deleted = self._cleanup_system_info(cursor)
                else:
                    # Regular time-based cleanup
                    cutoff = datetime.now() - timedelta(minutes=retention_minutes)
                    cursor.execute(f"DELETE FROM {table} WHERE time < %s", (cutoff,))
                    deleted = cursor.rowcount
                
                results[table] = deleted
                total_deleted += deleted
                
                if deleted > 0:
                    print(f"[DEBUG] RetentionManager: {table}: deleted {deleted} rows (retention: {retention_minutes}m)")
            
            print(f"[DEBUG] RetentionManager: total deleted {total_deleted} rows across all tables")
            return results
            
        except Exception as e:
            print(f"[ERROR] RetentionManager: cleanup failed: {e}")
            return {}
    
    def _cleanup_system_info(self, cursor):
        """
        Clean up system_info table - keep only the latest record per device.
        Since system_info has UNIQUE constraint on device_id, this should rarely delete anything.
        
        Returns:
            int: Number of deleted rows
        """
        try:
            # Count total rows before cleanup
            cursor.execute("SELECT COUNT(*) FROM system_info")
            total_before = cursor.fetchone()[0]
            
            # Delete old system_info records (keep latest per device)
            # This is mainly for cleanup if the UNIQUE constraint wasn't working properly
            cursor.execute("""
                DELETE si1 FROM system_info si1
                INNER JOIN system_info si2 
                WHERE si1.device_id = si2.device_id 
                AND si1.time < si2.time
            """)
            
            deleted = cursor.rowcount
            
            # Also delete very old system_info records (older than retention period)
            retention_minutes = self.retention_config.get('system_info', 10080)
            cutoff = datetime.now() - timedelta(minutes=retention_minutes)
            cursor.execute("DELETE FROM system_info WHERE time < %s", (cutoff,))
            deleted += cursor.rowcount
            
            if deleted > 0:
                print(f"[DEBUG] RetentionManager: system_info: deleted {deleted} old records")
            
            return deleted
            
        except Exception as e:
            print(f"[ERROR] RetentionManager: system_info cleanup failed: {e}")
            return 0
    
    def mark_offline_devices(self, timeout_seconds: int = 60):
        """
        Mark devices as offline if not seen recently.
        
        Args:
            timeout_seconds: Consider device offline after this many seconds
            
        Returns:
            int: Number of devices marked offline
        """
        try:
            cursor = self.conn.cursor()
            
            cutoff = datetime.now() - timedelta(seconds=timeout_seconds)
            
            cursor.execute("""
                UPDATE devices
                SET online = FALSE
                WHERE last_seen < %s AND online = TRUE
            """, (cutoff,))
            
            count = cursor.rowcount
            if count > 0:
                print(f"[DEBUG] RetentionManager: marked {count} devices offline")
            
            return count
            
        except Exception as e:
            print(f"[ERROR] RetentionManager: mark offline failed: {e}")
            return 0
    
    def get_database_stats(self):
        """
        Get database size and table statistics.
        
        Returns:
            dict: Database statistics
        """
        try:
            cursor = self.conn.cursor()
            stats = {}
            
            # Get database size
            cursor.execute("""
                SELECT 
                    ROUND(SUM(data_length + index_length) / 1024 / 1024, 2) AS 'DB Size in MB'
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
            """)
            stats['database_size_mb'] = cursor.fetchone()[0] or 0
            
            # Get table sizes and row counts
            cursor.execute("""
                SELECT 
                    table_name,
                    ROUND(((data_length + index_length) / 1024 / 1024), 2) AS 'Size in MB',
                    table_rows
                FROM information_schema.tables 
                WHERE table_schema = DATABASE()
                ORDER BY (data_length + index_length) DESC
            """)
            
            stats['tables'] = {}
            for row in cursor.fetchall():
                table_name, size_mb, row_count = row
                stats['tables'][table_name] = {
                    'size_mb': size_mb or 0,
                    'row_count': row_count or 0
                }
            
            # Get oldest and newest timestamps for each metric table
            metric_tables = ['load_avg', 'cpu_percent', 'memory', 'swap_memory', 
                           'disk_usage', 'disk_io_counters', 'net_io_counters', 'temperature', 'system_info']
            
            stats['time_ranges'] = {}
            for table in metric_tables:
                try:
                    cursor.execute(f"""
                        SELECT 
                            MIN(time) as oldest,
                            MAX(time) as newest,
                            COUNT(*) as total_rows
                        FROM {table}
                    """)
                    result = cursor.fetchone()
                    if result and result[0]:  # If table has data
                        stats['time_ranges'][table] = {
                            'oldest': result[0],
                            'newest': result[1], 
                            'total_rows': result[2]
                        }
                except Exception as e:
                    print(f"[WARNING] Could not get time range for {table}: {e}")
            
            return stats
            
        except Exception as e:
            print(f"[ERROR] RetentionManager: get_database_stats failed: {e}")
            return {}
    
    def close(self):
        """Close database connection."""
        self.conn.close()
        print("[DEBUG] RetentionManager: closed")
