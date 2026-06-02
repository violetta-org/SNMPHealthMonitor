import os
import json
import time
import random
from pathlib import Path
from datetime import datetime
from utils.logging import configure_logger
from .db_config import load_db_config
from .db_retention import RetentionManager

# Set up logging
logger = configure_logger(__name__)

def load_retention_config():
    """Load retention configuration from file or environment variables."""
    config_file = Path(__file__).parent / 'retention_config.json'
    
    # Default configuration
    default_config = {
        "retention_policies": {
            "load_avg": {"retention_minutes": 1440},
            "cpu_percent": {"retention_minutes": 1440},
            "memory": {"retention_minutes": 1440},
            "swap_memory": {"retention_minutes": 1440},
            "disk_usage": {"retention_minutes": 1440},
            "disk_io_counters": {"retention_minutes": 1440},
            "net_io_counters": {"retention_minutes": 1440},
            "temperature": {"retention_minutes": 1440},
            "system_info": {"retention_minutes": 10080}
        },
        "cleanup_settings": {
            "check_interval_seconds": 300,
            "agent_timeout_seconds": 60,
            "backoff_min_seconds": 1.0,
            "backoff_max_seconds": 30.0,
            "backoff_factor": 2.0
        },
        "monitoring": {
            "enable_stats_logging": True,
            "stats_log_interval_minutes": 60,
            "max_database_size_mb": 1000,
            "alert_on_size_exceeded": True
        }
    }
    
    # Try to load from file
    if config_file.exists():
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                # Merge with defaults
                for key, value in file_config.items():
                    if key in default_config:
                        default_config[key].update(value)
                    else:
                        default_config[key] = value
        except Exception as e:
            logger.warning(f"Could not load retention config from {config_file}: {e}")
    
    # Override with environment variables
    retention_policies = default_config["retention_policies"]
    for table in retention_policies:
        env_key = f"RETENTION_{table.upper()}_MINUTES"
        if env_key in os.environ:
            retention_policies[table]["retention_minutes"] = int(os.environ[env_key])
    
    cleanup_settings = default_config["cleanup_settings"]
    cleanup_settings["check_interval_seconds"] = int(os.environ.get('RETENTION_CHECK_INTERVAL_SEC', cleanup_settings["check_interval_seconds"]))
    cleanup_settings["agent_timeout_seconds"] = int(os.environ.get('AGENT_TIMEOUT_SECONDS', cleanup_settings["agent_timeout_seconds"]))
    cleanup_settings["backoff_min_seconds"] = float(os.environ.get('RET_BACKOFF_MIN', cleanup_settings["backoff_min_seconds"]))
    cleanup_settings["backoff_max_seconds"] = float(os.environ.get('RET_BACKOFF_MAX', cleanup_settings["backoff_max_seconds"]))
    cleanup_settings["backoff_factor"] = float(os.environ.get('RET_BACKOFF_FACTOR', cleanup_settings["backoff_factor"]))
    
    return default_config


def run_once(rm: RetentionManager, config: dict):
    """Run one cleanup cycle with monitoring."""
    cleanup_settings = config["cleanup_settings"]
    monitoring = config["monitoring"]
    
    # Run cleanup
    deleted_results = rm.cleanup_old_metrics()
    off = rm.mark_offline_devices(timeout_seconds=cleanup_settings["agent_timeout_seconds"])
    
    # Log results
    total_deleted = sum(deleted_results.values()) if deleted_results else 0
    logger.debug(f"Cleanup: deleted={total_deleted}, offline_marked={off}")
    
    # Log detailed results per table
    if deleted_results:
        for table, count in deleted_results.items():
            if count > 0:
                logger.debug(f"{table}: deleted {count} rows")
    
    # Get database stats if monitoring is enabled
    if monitoring.get("enable_stats_logging", False):
        stats = rm.get_database_stats()
        if stats:
            logger.debug(f"Database size: {stats.get('database_size_mb', 0):.2f} MB")
            
            # Check size limit
            max_size = monitoring.get("max_database_size_mb", 1000)
            if stats.get('database_size_mb', 0) > max_size:
                logger.warning(f"Database size ({stats['database_size_mb']:.2f} MB) exceeds limit ({max_size} MB)")
                
                if monitoring.get("alert_on_size_exceeded", True):
                    logger.warning("Consider reducing retention periods or increasing cleanup frequency")


def main():
    config = load_retention_config()
    cfg = load_db_config()
    
    # Extract retention policies for RetentionManager
    retention_config = {}
    for table, policy in config["retention_policies"].items():
        retention_config[table] = policy["retention_minutes"]
    
    rm = RetentionManager(cfg, retention_config=retention_config)
    
    cleanup_settings = config["cleanup_settings"]
    monitoring = config["monitoring"]
    
    logger.info(f"Retention CLI start:")
    logger.info(f"  - Retention policies: {retention_config}")
    logger.info(f"  - Check interval: {cleanup_settings['check_interval_seconds']}s")
    logger.info(f"  - Agent timeout: {cleanup_settings['agent_timeout_seconds']}s")
    logger.info(f"  - Monitoring: {'enabled' if monitoring.get('enable_stats_logging') else 'disabled'}")
    
    backoff = cleanup_settings["backoff_min_seconds"]
    last_stats_log = time.time()
    
    while True:
        try:
            run_once(rm, config)
            backoff = cleanup_settings["backoff_min_seconds"]
            
            # Log stats periodically if enabled
            if monitoring.get("enable_stats_logging", False):
                stats_interval = monitoring.get("stats_log_interval_minutes", 60) * 60
                if time.time() - last_stats_log >= stats_interval:
                    stats = rm.get_database_stats()
                    if stats:
                        logger.info(f"Database: {stats.get('database_size_mb', 0):.2f} MB")
                        for table, info in stats.get('tables', {}).items():
                            if info['row_count'] > 0:
                                logger.info(f"{table}: {info['row_count']} rows, {info['size_mb']:.2f} MB")
                    last_stats_log = time.time()
            
            time.sleep(cleanup_settings["check_interval_seconds"])
            
        except KeyboardInterrupt:
            logger.info("Retention CLI stopped by user")
            break
        except Exception as e:
            jitter = random.uniform(0, backoff * 0.2)
            wait = min(backoff + jitter, cleanup_settings["backoff_max_seconds"])
            logger.error(f"Retention CLI loop: {e} | backoff={wait:.1f}s")
            time.sleep(wait)
            backoff = min(backoff * cleanup_settings["backoff_factor"], cleanup_settings["backoff_max_seconds"])


if __name__ == "__main__":
    import pymysql as MySQLdb
    main()
