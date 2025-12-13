# Full SNMP Monitoring on

# Raspberry Pi 5 for LibreNMS

# (UCD-SNMP + Extend

# Workaround)

## Date: May 14, 2025

## Category: Monitoring / SNMP

## Backlink: LibreNMS Docker Deployment on Raspberry Pi 5

## 𐀀򊐀 Overview

This update documents how I configured full-featured SNMP monitoring on a Raspberry Pi 5 running
LibreNMS inside Docker. Since hrProcessorLoad and traditional Host Resources MIB features are
often unavailable or broken on ARM-based systems, I used UCD-SNMP and NET-SNMP-EXTEND-MIB to
monitor:

```
✅ CPU usage
✅ Memory usage (real, buffers, cache, swap)
✅ Disk space
✅ Temperature via custom script
✅ Graphs and health sensors in LibreNMS dashboard
```
## 𐀀񙰀 Step-by-Step Setup

## 1. Edit SNMP Configuration


Update /etc/snmp/snmpd.conf with:

### 2. Create Extend Script for CPU Temp

Paste:

Make it executable:

### 3. Give SNMP Access to Pi

### Temperature Sensor

```
rocommunity public
disk / 10000
```
```
view systemonly included .1.3.6.1.2.1.
view systemonly included .1.3.6.1.2.1.
view systemonly included .1.3.6.1.4.1.
view systemonly included .1.3.6.1.4.1.8072.
```
```
extend temp /bin/bash /usr/local/bin/snmp-temperature.sh
```
```
The disk line enables / monitoring. The extend line provides temperature
```
#### “ monitoring.

```
sudo nano /usr/local/bin/snmp-temperature.sh
```
```
#!/bin/bash
vcgencmd measure_temp | sed "s/temp=//;s/'C//"
```
```
sudo chmod +x /usr/local/bin/snmp-temperature.sh
```
```
sudo usermod -aG video Debian-snmp
sudo reboot
```

### 4. Verify SNMP Outputs

### 5. Ensure Pi is Added in LibreNMS

In the web UI:

```
Add device: 192.168.1.174 (not localhost)
SNMP v2c, community public
Confirm SNMP test passes
```
## 𐀀񉠀 Inside the Docker Container

### Enter container:

### Run poller and rediscovery:

## 𐀀񂠀 Final Results in LibreNMS

```
snmpwalk -v2c -c public localhost .1.3.6.1.4.1.2021.4 # Memory
snmpwalk -v2c -c public localhost .1.3.6.1.4.1.2021.9 # Disk
snmpwalk -v2c -c public localhost hrProcessorLoad # CPU per core
snmpwalk -v2c -c public localhost .1.3.6.1.4.1.2021.10 # Load avg
snmpwalk -v2c -c public localhost NET-SNMP-EXTEND-MIB::nsExtendOutput1Line.\"temp\" # Temperature
```
```
docker exec -it librenms bash
cd /opt/librenms
```
```
php artisan config:clear
./lnms poller:discovery 1
./lnms device:poll 1
```

From the Pi's page:

```
Graphs → CPU, Memory, Storage, Temperature are all active
Health tab shows temperature sensor: temp
Storage tab shows / and /boot/firmware
Dashboard Device Graphs widget now shows mini graphs for each metric
```
## 𐀀򮠀 Troubleshooting Addendum

### ❌ Memory Graphs Not Appearing?

Make sure:

```
SNMP returns .1.3.6.1.4.1.2021.4 correctly
ucd-mib, mempools, and storage modules are enabled in UI
You’ve updated the device hostname to use the Pi’s IP , not localhost
Use:
./lnms poller:discovery 1
./lnms device:poll 1
```
## ✅ Wrap-Up

With this configuration, the Pi 5 running LibreNMS inside Docker is now monitoring itself via SNMP,
including:

```
UCD-based metrics
Custom extend temperature sensor
Full graph integration
```
This setup is now replicable for other ARM-based Linux systems with similar SNMP limitations!

```
Revision #
Created 14 May 2025 23:35:38 by Nate Nash
Updated 8 June 2025 00:16:10 by Nate Nash
```

