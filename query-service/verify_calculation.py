"""
Manual verification of memory calculation logic
Using current SNMP values from 192.168.80.130
"""

# SNMP Raw Values (in KB)
snmp_total_kb = 3977108
snmp_free_kb = 6913696  # INVALID: > total
snmp_available_kb = 2722468
snmp_buffers_kb = 167072
snmp_cached_kb = 482680

# Convert to bytes (× 1024)
total_bytes = snmp_total_kb * 1024
free_bytes = snmp_free_kb * 1024
available_bytes = snmp_available_kb * 1024
buffers_bytes = snmp_buffers_kb * 1024
cached_bytes = snmp_cached_kb * 1024

print("=" * 100)
print("SNMP RAW VALUES (after × 1024 scale)")
print("=" * 100)
print(f"total     = {total_bytes:,} bytes = {total_bytes / (1024**3):.2f} GB")
print(f"free      = {free_bytes:,} bytes = {free_bytes / (1024**3):.2f} GB  <- INVALID (> total)")
print(f"available = {available_bytes:,} bytes = {available_bytes / (1024**3):.2f} GB")
print(f"buffers   = {buffers_bytes:,} bytes = {buffers_bytes / (1024**3):.2f} GB")
print(f"cached    = {cached_bytes:,} bytes = {cached_bytes / (1024**3):.2f} GB")

# Apply db_writer logic
free_was_capped = False
if free_bytes > total_bytes:
    free_bytes = total_bytes
    free_was_capped = True

if free_was_capped and available_bytes is not None:
    # Free was invalid, use available
    used_bytes = total_bytes - available_bytes
else:
    # Normal calculation
    used_bytes = total_bytes - free_bytes - buffers_bytes - cached_bytes

used_bytes = max(0, used_bytes)
percent = (used_bytes / total_bytes) * 100 if total_bytes > 0 else 0

print("\n" + "=" * 100)
print("DB_WRITER CALCULATION (New Logic)")
print("=" * 100)
print(f"free_was_capped = {free_was_capped}")
print(f"Calculation: used = total - {'available' if free_was_capped else 'free - buffers - cached'}")
if free_was_capped:
    print(f"           = {total_bytes:,} - {available_bytes:,}")
else:
    print(f"           = {total_bytes:,} - {free_bytes:,} - {buffers_bytes:,} - {cached_bytes:,}")
print(f"           = {used_bytes:,} bytes")
print(f"           = {used_bytes / (1024**3):.2f} GB")
print(f"percent    = {percent:.2f}%")

print("\n" + "=" * 100)
print("EXPECTED DATABASE VALUES")
print("=" * 100)
print(f"total     = {total_bytes:,}")
print(f"available = {available_bytes:,}")
print(f"free      = {total_bytes:,}  <- capped at total")
print(f"cached    = {cached_bytes:,}")
print(f"used      = {used_bytes:,}")
print(f"percent   = {percent:.2f}")

print("\n" + "=" * 100)
print("FRONTEND CALCULATION (from DB values)")
print("=" * 100)
# Frontend gets: total, free (capped), buffers, cached
# Frontend calculates: used = total - free - buffers - cached
frontend_used = max(0, total_bytes - total_bytes - buffers_bytes - cached_bytes)
frontend_percent = (frontend_used / total_bytes) * 100 if total_bytes > 0 else 0
print(f"Frontend formula: used = total - free - buffers - cached")
print(f"                = {total_bytes:,} - {total_bytes:,} - {buffers_bytes:,} - {cached_bytes:,}")
print(f"                = {frontend_used:,} bytes")
print(f"                = {frontend_used / (1024**3):.2f} GB")
print(f"percent         = {frontend_percent:.2f}%")

print("\n" + "=" * 100)
print("ISSUE DETECTED!")
print("=" * 100)
print("X Frontend will get 0% because it receives free = total (capped)")
print("OK Database percent calculation is correct (from available)")
print("WARNING Database should send uncapped 'available' for frontend calculation")
