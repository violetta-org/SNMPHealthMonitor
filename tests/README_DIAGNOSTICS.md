# VM Diagnostics Packet
This directory contains tools to diagnose high CPU and SUDO performance on your VM.

## Contents
1. `diagnose_vm_health.py`: Checks process tree for "Double Piping" (`yes | sudo`) and CPU hogs.
2. `verify_sudo_performance.sh`: Benchmarks `sudo` execution time.

## Instructions
1. Copy `tests/` folder to your VM.
2. Install dependencies: `pip install psutil`
3. Run:
   ```bash
   chmod +x verify_sudo_performance.sh
   ./verify_sudo_performance.sh
   python3 diagnose_vm_health.py
   ```
