#!/bin/bash
# Verify Sudo Performance and Resource Usage

echo "--- Starting Sudo Performance Test ---"
echo "Date: $(date)"

# Function to measure execution time
measure_exec() {
    CMD="$@"
    echo "Running: $CMD"
    
    START=$(date +%s.%N)
    $CMD
    EXIT_CODE=$?
    END=$(date +%s.%N)
    
    DIFF=$(echo "$END - $START" | bc)
    echo "Exit Code: $EXIT_CODE"
    echo "Time Taken: $DIFF seconds"
    echo "-----------------------------------"
}

# 1. Test basic non-interactive sudo (should be fast if cached/nopasswd)
echo "1. Testing basic sudo (list privs)"
measure_exec sudo -l

# 2. Test apt-get update (dry run or simulate if possible, but real update is better for load)
# Warning: actually running update might take time depending on network. 
# We'll use a harmless process check using sudo first.
echo "2. Testing sudo kill -0 (Signal 0 check on PID 1)"
measure_exec sudo kill -0 1

# 3. Check for specific apt lock or issues
echo "3. Checking apt locks"
sudo lsof /var/lib/dpkg/lock-frontend
sudo lsof /var/lib/apt/lists/lock

# 4. Check CPU usage before and during
echo "4. CPU/Memory Snapshot (Top 5 CPU)"
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -n 6

echo "--- End Test ---"
