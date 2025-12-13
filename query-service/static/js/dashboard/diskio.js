/**
 * DiskIO Dashboard Module
 * Handles disk IO metrics page with pagination
 */
import { BaseDashboardUI } from './base.js';

export class DiskIODashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
    }

    /**
     * Register UI elements for diskio page
     */
    registerElements() {
        // Header elements only (diskio table is dynamic)
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
    }

    /**
     * Update disk IO metrics UI
     */
    update(processedData) {
        console.log('[DiskIODashboard] Updating disk IO UI', processedData);
        
        // Update device info (online status, last_seen, ip_address)
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        const tbody = document.getElementById('diskio-tbody');
        const paginationContainer = document.getElementById('pagination-container');
        
        if (!tbody) {
            console.warn('[DiskIODashboard] DiskIO table body not found');
            return;
        }

        if (processedData.disk_io && processedData.disk_io.data) {
            tbody.innerHTML = '';
            
            processedData.disk_io.data.forEach((disk) => {
                const row = document.createElement('tr');
                row.innerHTML = `
                    <td>${disk.disk || 'Unknown'}</td>
                    <td>${disk.read_bytes_s != null ? this.dataProcessor.formatBytes(disk.read_bytes_s) + '/s' : 'N/A'}</td>
                    <td>${disk.write_bytes_s != null ? this.dataProcessor.formatBytes(disk.write_bytes_s) + '/s' : 'N/A'}</td>
                    <td>${this.dataProcessor.formatBytes(disk.read_bytes || 0)}</td>
                    <td>${this.dataProcessor.formatBytes(disk.write_bytes || 0)}</td>
                `;
                tbody.appendChild(row);
            });

            // Update pagination
            if (paginationContainer && processedData.disk_io.pagination) {
                const pagination = processedData.disk_io.pagination;
                paginationContainer.innerHTML = `
                    <div class="pagination-info">
                        Page ${pagination.page} of ${pagination.total_pages} (${pagination.total} total)
                    </div>
                    <div class="pagination-buttons">
                        <button id="prev-page" ${pagination.page <= 1 ? 'disabled' : ''}>Previous</button>
                        <button id="next-page" ${pagination.page >= pagination.total_pages ? 'disabled' : ''}>Next</button>
                    </div>
                `;
            }
        }
    }
}

