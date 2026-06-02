/**
 * Disk Dashboard Module
 * Handles disk metrics page
 */
import { BaseDashboardUI } from '/static/js/dashboard/base.js';

export class DiskDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.wsManager = null;
        this.sysname = null;
        this.topic = null;
    }

    attachWebSocketManager(wsManager, sysname, topic) {
        this.wsManager = wsManager;
        this.sysname = sysname;
        this.topic = topic;
    }

    /**
     * Register UI elements for disk page
     */
    registerElements() {
        // Header elements only (disk usage is dynamic)
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
    }

    /**
     * Update disk metrics UI
     */
    update(processedData) {
        console.log('[DiskDashboard] Updating disk UI', processedData);
        
        // Update device info (online status, last_seen, ip_address)
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        const container = document.getElementById('disk-usage-container');
        if (!container) {
            console.warn('[DiskDashboard] Disk usage container not found');
            return;
        }

        if (processedData.disk_usage && processedData.disk_usage.length > 0) {
            container.innerHTML = '';
            
            processedData.disk_usage.forEach((disk) => {
                const diskCard = document.createElement('div');
                diskCard.className = 'disk-card';
                const percent = disk.percent || 0;
                // Use correct field names: mount and device_partition (from query)
                const displayName = disk.mount || disk.device_partition || 'Unknown';
                const deviceName = disk.device_partition || disk.mount || '';
                
                diskCard.innerHTML = `
                    <h3>${displayName}</h3>
                    <div class="disk-gauge">
                        <svg class="gauge" viewBox="0 0 120 120">
                            <circle class="gauge-background" cx="60" cy="60" r="45" fill="none" stroke="#3a4d5f" stroke-width="8"/>
                            <circle class="gauge-progress disk-${deviceName.replace(/[^a-zA-Z0-9]/g, '-') || 'unknown'}" cx="60" cy="60" r="45" fill="none" stroke="#00bcd4" stroke-width="8" 
                                    stroke-dasharray="283" stroke-dashoffset="283" transform="rotate(-90 60 60)" stroke-linecap="round"/>
                            <text x="60" y="55" text-anchor="middle" class="gauge-value">${Math.round(percent)}%</text>
                            <text x="60" y="70" text-anchor="middle" class="gauge-sublabel">${deviceName || ''}</text>
                        </svg>
                    </div>
                    <div class="disk-info">
                        <div class="disk-stat">
                            <label>Total:</label>
                            <span>${this.dataProcessor.formatBytes(disk.total || 0)}</span>
                        </div>
                        <div class="disk-stat">
                            <label>Used:</label>
                            <span>${this.dataProcessor.formatBytes(disk.used || 0)}</span>
                        </div>
                        <div class="disk-stat">
                            <label>Free:</label>
                            <span>${this.dataProcessor.formatBytes(disk.free || 0)}</span>
                        </div>
                    </div>
                `;
                container.appendChild(diskCard);
                
                // Update gauge
                setTimeout(() => {
                    const progressCircle = diskCard.querySelector('.gauge-progress');
                    if (progressCircle) {
                        const circumference = 2 * Math.PI * 45;
                        const offset = circumference - (percent / 100) * circumference;
                        progressCircle.style.strokeDashoffset = offset;
                    }
                }, 100);
            });
        }
    }
}

