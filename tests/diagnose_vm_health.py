
import psutil
import time
import sys
import os

def check_high_cpu_processes(threshold=50.0):
    print(f"--- Checking for processes consuming > {threshold}% CPU ---")
    found = False
    for proc in psutil.process_iter(['pid', 'name', 'username', 'cpu_percent', 'cmdline']):
        try:
            # cpu_percent needs interval to be accurate if called once, but iterative calls might have cached values
            # confusing in psutil. Let's rely on what process_iter gives or call cpu_percent explicitly
            cpu = proc.info['cpu_percent']
            if cpu is None: 
                cpu = 0.0
            
            # psutil quirk: first call often 0. Use a small sleep/interval if needed or trust the loop if running continuously.
            # For a one-shot script, we might need a specific check.
            pass
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
            
    # Better approach: Get all processes, wait a bit, get again to calculate CPU?
    # Or just grab the ones that stick out if the system is ALREADY actively lagging.
    
    # Snapshot 1
    procs = []
    for p in psutil.process_iter(['pid', 'name']):
        procs.append(p)
    
    # Wait short interval for CPU calc
    time.sleep(1)
    
    for p in procs:
        try:
            if not p.is_running(): continue
            cpu = p.cpu_percent(interval=None) # Interval 0/None returns slightly different stats depending on previous call
            if cpu and cpu > threshold:
                found = True
                cmd = " ".join(p.cmdline()) if p.cmdline() else "(no cmdline)"
                print(f"[ALERT] PID: {p.pid} | Name: {p.name()} | User: {p.username()} | CPU: {cpu}%")
                print(f"        Command: {cmd}")
                
                # Check for "yes" double piping signature
                if p.name() == 'yes':
                    print("        [ANALYSIS] 'yes' process found consuming high CPU.")
                    parent = p.parent()
                    if parent:
                        print(f"        Parent: {parent.name()} (PID: {parent.pid}) | Cmd: {' '.join(parent.cmdline())}")
                        # If parent is shell or python, it might be the culprit
                        if 'sh' in parent.name() or 'python' in parent.name():
                            print("        -> POTENTIAL LEAK: 'yes' might be orphaned or still piped to a finished process.")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not found:
        print("No single process found explicitly > threshold (might need longer monitoring).")

def check_zombies():
    print("\n--- Checking for Zombie Processes ---")
    zombies = [p for p in psutil.process_iter(['pid', 'status', 'name']) if p.info['status'] == psutil.STATUS_ZOMBIE]
    if zombies:
        for z in zombies:
            print(f"Zombie: PID {z.info['pid']} - {z.info['name']}")
    else:
        print("No zombie processes found.")

if __name__ == "__main__":
    print(f"Diagnosing System Health on {os.uname().sysname if hasattr(os, 'uname') else os.name}...")
    try:
        check_high_cpu_processes()
        check_zombies()
    except Exception as e:
        print(f"Error during diagnosis: {e}")
