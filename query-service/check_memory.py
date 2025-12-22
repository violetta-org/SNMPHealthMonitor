from db.connection import get_db

print("Querying latest 10 memory records from database...")
print("=" * 180)

with get_db() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT time, sysname, total, available, used, free, percent, buffers, cached
            FROM memory
            ORDER BY time DESC
            LIMIT 10
        """)
        rows = cur.fetchall()
        
        if not rows:
            print("No memory records found!")
        else:
            # Print header
            print(f"{'time':<20} | {'sysname':<10} | {'total':<15} | {'available':<15} | {'used':<15} | {'free':<15} | {'percent':<8} | {'buffers':<12} | {'cached':<12}")
            print("-" * 180)
            
            # Print rows
            for row in rows:
                print(f"{str(row['time']):<20} | {row['sysname']:<10} | {row['total']:<15} | {row['available']:<15} | {row['used']:<15} | {row['free']:<15} | {row['percent']:<8.2f} | {row['buffers']:<12} | {row['cached']:<12}")
            
            print("\n" + "=" * 180)
            print(f"\nMemory Total (first record): {rows[0]['total']} bytes")
            print(f"  = {rows[0]['total'] / (1024**3):.2f} GB")
            print(f"  = Math.ceil({rows[0]['total'] / (1024**3):.2f}) = {int((rows[0]['total'] / (1024**3)) + 0.999)} GB (rounded up)")
