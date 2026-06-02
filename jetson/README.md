# Jetson Nano SNMP Configuration & Troubleshooting

This folder contains configuration files and setup scripts to monitor an **NVIDIA Jetson Nano** using SNMP.

## Setup Instructions

1. **Copy the Configuration files to your Jetson Nano:**
   ```bash
   scp -r jetson/ user@<jetson_ip>:~/
   ```

2. **Install Net-SNMP daemon on the Jetson Nano:**
   ```bash
   sudo apt update
   sudo apt install -y snmpd bc
   ```

3. **Deploy the files:**
   - Copy `snmpd.conf` to `/etc/snmp/`:
     ```bash
     sudo cp ~/jetson/snmpd.conf /etc/snmp/snmpd.conf
     ```
   - Copy the temperature monitoring script to `/usr/local/bin/` and make it executable:
     ```bash
     sudo cp ~/jetson/snmp-temperature.sh /usr/local/bin/snmp-temperature.sh
     sudo chmod +x /usr/local/bin/snmp-temperature.sh
     ```

4. **Restart SNMP service:**
   ```bash
   sudo systemctl restart snmpd
   sudo systemctl enable snmpd
   ```

---

## Troubleshooting "Error opening specified endpoint"

If you encounter the error:
```
snmpd[9473]: Error opening specified endpoint "udp:0.0.0.0:161"
snmpd[9473]: Server Exiting with code 1
```

This means that port `161` is already in use by another process or daemon. Follow these steps to resolve it:

### 1. Identify conflicting processes
Find out what is already binding to UDP port 161:
```bash
sudo ss -ulpn | grep :161
# or
sudo lsof -i udp:161
```
If you see another SNMP daemon or monitoring agent running (e.g. `mini-snmpd`), you can stop and disable it:
```bash
sudo systemctl stop mini-snmpd
sudo systemctl disable mini-snmpd
```

### 2. Check for duplicate snmpd runs
If the default systemd unit configuration also binds SNMP to the same loopback address, it might conflict with the `agentAddress` directive in `/etc/snmp/snmpd.conf`.
Check the service definition or configurations in `/etc/default/snmpd`:
```bash
cat /etc/default/snmpd
```
Look for lines starting with `SNMPDOPTS`. If they contain endpoints (like `127.0.0.1` or `udp:161`), edit `/etc/default/snmpd` and clean up conflicting address flags, leaving the configuration to be managed by `snmpd.conf`.

### 3. Alternative: Change the SNMP port
If port 161 cannot be freed, you can edit `/etc/snmp/snmpd.conf` and change:
```conf
agentAddress  udp:161
```
to another port (e.g. `udp:1161`), restart snmpd:
```bash
sudo systemctl restart snmpd
```
Remember to update the SNMP port configuration to `1161` in the collector application's `config.json`.
