from db.queries import get_device_info, get_db
import sys

sysname = 'raspi-pbl'
print(f"Checking status for {sysname}...")

try:
    info = get_device_info(sysname)
    print(f"Result: {info}")
    
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM devices WHERE sysname = %s", (sysname,))
            row = cur.fetchone()
            print(f"Raw Row: {row}")
except Exception as e:
    print(f"Error: {e}")
