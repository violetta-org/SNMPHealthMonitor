"""
Verify which formula is correct for RAM free
"""

# SNMP Data (in KB)
mem_total_real = 3977108
mem_total_free = 6923792
mem_avail_real = 2732564
mem_total_swap = 4191228
mem_avail_swap = 4191228

print("=" * 100)
print("SNMP DATA")
print("=" * 100)
print(f"memTotalReal = {mem_total_real} kB = {mem_total_real / 1024:.2f} MB = {mem_total_real / 1024 / 1024:.2f} GB")
print(f"memTotalFree = {mem_total_free} kB = {mem_total_free / 1024:.2f} MB = {mem_total_free / 1024 / 1024:.2f} GB")
print(f"memAvailReal = {mem_avail_real} kB = {mem_avail_real / 1024:.2f} MB = {mem_avail_real / 1024 / 1024:.2f} GB")
print(f"memTotalSwap = {mem_total_swap} kB = {mem_total_swap / 1024:.2f} MB = {mem_total_swap / 1024 / 1024:.2f} GB")
print(f"memAvailSwap = {mem_avail_swap} kB = {mem_avail_swap / 1024:.2f} MB = {mem_avail_swap / 1024 / 1024:.2f} GB")

print("\n" + "=" * 100)
print("FORMULA VERIFICATION")
print("=" * 100)

# Formula: memTotalFree = memRAMFree + memSwapFree
mem_ram_free_calculated = mem_total_free - mem_avail_swap
print(f"Formula: memTotalFree = memRAMFree + memSwapFree")
print(f"  {mem_total_free} = memRAMFree + {mem_avail_swap}")
print(f"  memRAMFree = {mem_total_free} - {mem_avail_swap}")
print(f"  memRAMFree = {mem_ram_free_calculated} kB = {mem_ram_free_calculated / 1024 / 1024:.2f} GB")

print(f"\nmemAvailReal = {mem_avail_real} kB = {mem_avail_real / 1024 / 1024:.2f} GB")

print(f"\nDifference: {abs(mem_ram_free_calculated - mem_avail_real)} kB = {abs(mem_ram_free_calculated - mem_avail_real) / 1024:.2f} MB")

if mem_ram_free_calculated == mem_avail_real:
    print("\nCONCLUSION: memRAMFree (calculated) == memAvailReal (SNMP)")
    print("Both formulas work:")
    print("  1. memFree = memTotalFree - memSwapFree")
    print("  2. memFree = memAvailReal (simpler!)")
else:
    print(f"\nCONCLUSION: Small difference ({abs(mem_ram_free_calculated - mem_avail_real) / 1024:.2f} MB)")
    print("Recommended: Use memAvailReal (it's designed for this purpose)")

print("\n" + "=" * 100)
print("CURRENT IMPLEMENTATION")
print("=" * 100)
print("if free > total:")
print("    free = available  <- Using memAvailReal (CORRECT!)")
