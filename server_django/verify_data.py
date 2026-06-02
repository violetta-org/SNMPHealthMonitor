import os
import sys
import pymysql
import django

# Install PyMySQL as MySQLdb
pymysql.install_as_MySQLdb()

# Setup Django environment
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.devices.models import Device
from apps.metrics.models import LoadAvg, CpuPercent, SystemInfo
from django.db.models import Count

def verify():
    print("=== Data Integrity Verification ===")
    
    # 1. Check Devices
    device_count = Device.objects.count()
    print(f"Devices found: {device_count}")
    for device in Device.objects.all():
        print(f" - Device: {device.sysname}")

    if device_count == 0:
        print("WARNING: No devices found in DB!")
        return

    # 2. Check Metrics
    metric_models = [
        ('SystemInfo', SystemInfo),
        ('LoadAvg', LoadAvg),
        ('CpuPercent', CpuPercent)
    ]
    
    for name, model in metric_models:
        count = model.objects.count()
        print(f"{name} records: {count}")
        if count > 0:
            latest = model.objects.order_by('-time').first()
            print(f"  Latest {name}: {latest.time} for {latest.sysname_id}")
        else:
            print(f"  WARNING: No data for {name}")

if __name__ == '__main__':
    verify()
