#!/bin/bash
# Read CPU thermal zone on NVIDIA Jetson Nano
if [ -f /sys/devices/virtual/thermal/thermal_zone0/temp ]; then
    temp_raw=$(cat /sys/devices/virtual/thermal/thermal_zone0/temp)
    # Jetson Nano temperature is in millicelsius, divide by 1000 to get Celsius
    echo "scale=1; $temp_raw / 1000" | bc
else
    echo "0"
fi
