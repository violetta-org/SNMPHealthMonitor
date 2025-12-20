/**
 * DiskIO Dashboard Module
 * Handles disk IO metrics page with pagination
 */
import { BaseDashboardUI } from './base.js';

export class DiskIODashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.currentPage = 1;
        this.perPage = 10;
        this.diskIOData = [];
        this.totalItems = 0;
    }

    /**
     * Register UI elements for diskio page
     */
    registerElements() {
        // Header elements only (diskio table is dynamic)
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
        
        // Disk IO elements
        this.registerElement('diskio-tbody', '#diskio-tbody');
        this.registerElement('pagination-container', '#pagination-container');
    }

    /**
     * Attach WebSocket manager for range queries
     */
    attachWebSocketManager(wsManager, sysname, topic) {
        this.wsManager = wsManager;
        this.sysname = sysname;
        this.topic = topic;
        
        // Setup pagination event listeners
        setTimeout(() => this.setupPaginationListeners(), 100);
    }

    /**
     * Setup pagination button listeners
     */
    setupPaginationListeners() {
        const container = this.elements['pagination-container'];
        if (!container) return;
        
        // Event delegation for pagination buttons
        container.addEventListener('click', (e) => {
            const target = e.target;
            
            if (target.id === 'prev-page') {
                this.changePage(-1);
            } else if (target.id === 'next-page') {
                this.changePage(1);
            }
        });
    }

    /**
     * Change current page
     */
    changePage(delta) {
        const newPage = this.currentPage + delta;
        if (newPage < 1 || newPage > Math.ceil(this.totalItems / this.perPage)) {
            return;
        }
        
        this.currentPage = newPage;
        this.updateDiskIOTable();
    }

    /**
     * Update disk IO table with current data
     */
    updateDiskIOTable() {
        const tbody = this.elements['diskio-tbody'];
        const paginationContainer = this.elements['pagination-container'];
        
        if (!tbody || !paginationContainer) {
            console.warn('[DiskIODashboard] DiskIO table elements not found');
            return;
        }

        // Clear table
        tbody.innerHTML = '';
        
        // Calculate pagination bounds
        const startIndex = (this.currentPage - 1) * this.perPage;
        const endIndex = Math.min(startIndex + this.perPage, this.diskIOData.length);
        
        // Fill table with data
        for (let i = startIndex; i < endIndex; i++) {
            const disk = this.diskIOData[i];
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${disk.disk || disk.device || 'Unknown'}</td>
                <td>${disk.read_bytes_s != null ? this.dataProcessor.formatBytes(disk.read_bytes_s) + '/s' : 'N/A'}</td>
                <td>${disk.write_bytes_s != null ? this.dataProcessor.formatBytes(disk.write_bytes_s) + '/s' : 'N/A'}</td>
                <td>${this.dataProcessor.formatBytes(disk.read_bytes || 0)}</td>
                <td>${this.dataProcessor.formatBytes(disk.write_bytes || 0)}</td>
            `;
            tbody.appendChild(row);
        }

        // Update pagination UI
        this.updatePaginationUI();
    }

    /**
     * Update pagination UI
     */
    updatePaginationUI() {
        const paginationContainer = this.elements['pagination-container'];
        if (!paginationContainer) return;
        
        const totalPages = Math.ceil(this.totalItems / this.perPage);
        
        let paginationHTML = '';
        if (totalPages > 0) {
            paginationHTML = `
                <div class="pagination-info">
                    Page ${this.currentPage} of ${totalPages} (${this.totalItems} total)
                </div>
                <div class="pagination-buttons">
                    <button id="prev-page" ${this.currentPage <= 1 ? 'disabled' : ''}>Previous</button>
                    <button id="next-page" ${this.currentPage >= totalPages ? 'disabled' : ''}>Next</button>
                </div>
            `;
        }
        
        paginationContainer.innerHTML = paginationHTML;
    }

    /**
     * Update disk IO metrics UI
     */
    update(processedData) {
        console.log('[DiskIODashboard] Updating disk IO UI', processedData);
        
        // Update device info
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        // Update disk IO data
        if (processedData.disk_io && Array.isArray(processedData.disk_io)) {
            this.diskIOData = processedData.disk_io;
            this.totalItems = this.diskIOData.length;
            
            // If server provides pagination info, use it
            if (processedData.disk_io.pagination) {
                const pagination = processedData.disk_io.pagination;
                this.currentPage = pagination.page || 1;
                this.totalItems = pagination.total || this.diskIOData.length;
                
                // Update table if data is already paginated
                if (processedData.disk_io.data) {
                    this.diskIOData = processedData.disk_io.data;
                }
            }
            
            this.updateDiskIOTable();
        }
    }
}