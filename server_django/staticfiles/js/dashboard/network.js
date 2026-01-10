/**
 * Network Dashboard Module
 * Handles network metrics page
 */
import { BaseDashboardUI } from './base.js';

export class NetworkDashboard extends BaseDashboardUI {
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
     * Convert admin status code to friendly text
     */
    getAdminStatusText(status) {
        const statusMap = {
            1: { text: 'Up', icon: '✅', color: 'success' },
            2: { text: 'Down', icon: '❌', color: 'error' },
            3: { text: 'Testing', icon: '🔧', color: 'warning' }
        };
        return statusMap[status] || { text: 'Unknown', icon: '❓', color: 'unknown' };
    }

    /**
     * Convert operational status code to friendly text
     */
    getOperStatusText(status) {
        const statusMap = {
            1: { text: 'Up', icon: '🟢', color: 'success' },
            2: { text: 'Down', icon: '🔴', color: 'error' },
            3: { text: 'Testing', icon: '🟡', color: 'warning' },
            4: { text: 'Unknown', icon: '❓', color: 'unknown' },
            5: { text: 'Dormant', icon: '💤', color: 'warning' },
            6: { text: 'Not Present', icon: '🚫', color: 'error' },
            7: { text: 'Lower Layer Down', icon: '⬇️', color: 'error' }
        };
        return statusMap[status] || { text: 'Unknown', icon: '❓', color: 'unknown' };
    }

    /**
     * Register UI elements for network page
     */
    registerElements() {
        // Header elements only (network interfaces are dynamic)
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
    }

    /**
     * Update network metrics UI
     */
    update(processedData) {
        console.log('[NetworkDashboard] Updating network UI', processedData);

        // Update device info (online status, last_seen, ip_address)
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }

        const container = document.getElementById('network-interfaces-container');
        if (!container) {
            console.warn('[NetworkDashboard] Network interfaces container not found');
            return;
        }

        if (processedData.network && processedData.network.length > 0) {
            container.innerHTML = '';

            processedData.network.forEach((iface) => {
                const adminStatus = this.getAdminStatusText(iface.if_admin_status);
                const operStatus = this.getOperStatusText(iface.if_oper_status);

                const ifaceCard = document.createElement('div');
                ifaceCard.className = 'network-interface-card';
                ifaceCard.innerHTML = `
                    <div class="interface-header">
                        <h3>${iface.interface || 'Unknown'}</h3>
                        <div class="interface-status-badges">
                            <span class="status-badge status-${adminStatus.color}" title="Admin Status">
                                <span class="status-icon">${adminStatus.icon}</span>
                                <span class="status-text">Admin: ${adminStatus.text}</span>
                            </span>
                            <span class="status-badge status-${operStatus.color}" title="Operational Status">
                                <span class="status-icon">${operStatus.icon}</span>
                                <span class="status-text">Oper: ${operStatus.text}</span>
                            </span>
                        </div>
                    </div>
                    <div class="network-stats">
                        <div class="stat-item">
                            <label><span class="stat-icon">📤</span> Bytes Sent:</label>
                            <span>${this.dataProcessor.formatBytes(iface.bytes_sent || 0)}</span>
                        </div>
                        <div class="stat-item">
                            <label><span class="stat-icon">📥</span> Bytes Received:</label>
                            <span>${this.dataProcessor.formatBytes(iface.bytes_recv || 0)}</span>
                        </div>
                        <div class="stat-item">
                            <label><span class="stat-icon">⬆️</span> Send Rate:</label>
                            <span>${iface.send_bytes_s != null ? this.dataProcessor.formatBytes(iface.send_bytes_s) + '/s' : 'N/A'}</span>
                        </div>
                        <div class="stat-item">
                            <label><span class="stat-icon">⬇️</span> Receive Rate:</label>
                            <span>${iface.recv_bytes_s != null ? this.dataProcessor.formatBytes(iface.recv_bytes_s) + '/s' : 'N/A'}</span>
                        </div>
                    </div>
                `;
                container.appendChild(ifaceCard);
            });
        }
    }
}

