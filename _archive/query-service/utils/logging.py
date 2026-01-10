"""
Custom logging configuration with daily log files
"""
import logging
import sys
import os
from typing import Optional
from datetime import datetime

# Logs directory setup
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

class ColorFormatter(logging.Formatter):
    """Custom colored formatter for console"""
    COLORS = {
        logging.DEBUG: "\x1b[38;20m",
        logging.INFO: "\x1b[38;20m",
        logging.WARNING: "\x1b[33;20m",
        logging.ERROR: "\x1b[31;20m",
        logging.CRITICAL: "\x1b[31;1m"
    }
    RESET = "\x1b[0m"
    FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        return color + super().format(record) + self.RESET

def configure_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Configure logger with:
    - Colored console output
    - Daily rotating file logs
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(ColorFormatter())
    logger.addHandler(console)

    # File handler (daily logs)
    log_date = datetime.now().strftime("%Y-%m-%d")
    log_file = os.path.join(LOG_DIR, f"{log_date}.log")
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(file_handler)

    return logger
