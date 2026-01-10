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
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
        
        // Thử tìm element ngay lúc khởi tạo
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
        // Chờ 1 chút để đảm bảo DOM đã render xong
        setTimeout(() => this.setupPaginationListeners(), 500);
    }

    /**
     * Setup pagination button listeners
     */
    setupPaginationListeners() {
        // Thử lấy container, nếu chưa có thì query lại
        let container = this.elements['pagination-container'];
        if (!container) {
            container = document.querySelector('#pagination-container');
            if (container) this.elements['pagination-container'] = container;
        }

        if (!container) return;

        // Xóa listener cũ nếu có để tránh duplicate (cloneNode trick)
        const newContainer = container.cloneNode(true);
        container.parentNode.replaceChild(newContainer, container);
        this.elements['pagination-container'] = newContainer;

        // Event delegation
        newContainer.addEventListener('click', (e) => {
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
        const totalPages = Math.ceil(this.totalItems / this.perPage);
        const newPage = this.currentPage + delta;

        if (newPage < 1 || newPage > totalPages) {
            return;
        }

        this.currentPage = newPage;
        this.updateDiskIOTable();
    }

    /**
     * Update disk IO table with current data
     * [FIXED] Tự động tìm lại DOM element nếu lúc khởi tạo bị miss
     */
    updateDiskIOTable() {
        // 1. LAZY LOOKUP: Nếu chưa có trong cache, query trực tiếp từ DOM
        let tbody = this.elements['diskio-tbody'];
        if (!tbody) {
            tbody = document.querySelector('#diskio-tbody');
            if (tbody) this.elements['diskio-tbody'] = tbody;
        }

        let paginationContainer = this.elements['pagination-container'];
        if (!paginationContainer) {
            paginationContainer = document.querySelector('#pagination-container');
            if (paginationContainer) {
                this.elements['pagination-container'] = paginationContainer;
                // Nếu tìm thấy muộn, cần setup lại listener
                this.setupPaginationListeners();
            }
        }

        // 2. Nếu vẫn không tìm thấy thì mới báo lỗi (nhưng chỉ warn nhẹ)
        if (!tbody || !paginationContainer) {
            // Chỉ log nếu thực sự có dữ liệu mà không hiển thị được
            if (this.diskIOData.length > 0) {
                console.warn('[DiskIODashboard] Waiting for DOM elements: #diskio-tbody or #pagination-container...');
            }
            return;
        }

        // Clear table
        tbody.innerHTML = '';

        // 3. Logic phân trang hiển thị (Frontend Slicing vs Backend Slicing)
        let startIndex = 0;
        let endIndex = this.diskIOData.length;

        // Nếu Backend trả về full data (Range mode), ta tự cắt
        if (this.totalItems > this.diskIOData.length) {
            // Snapshot mode (Backend đã cắt sẵn)
            startIndex = 0;
            endIndex = this.diskIOData.length;
        } else {
            // Range mode (Frontend tự cắt)
            startIndex = (this.currentPage - 1) * this.perPage;
            endIndex = Math.min(startIndex + this.perPage, this.diskIOData.length);
        }

        // Fill table with data
        for (let i = startIndex; i < endIndex; i++) {
            const disk = this.diskIOData[i];
            if (!disk) continue;

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

        // Ẩn pagination nếu không có dữ liệu hoặc chỉ có 1 trang
        if (totalPages <= 1 && this.totalItems === 0) {
            paginationContainer.innerHTML = '';
            return;
        }

        paginationContainer.innerHTML = `
            <div class="pagination-info">
                Page ${this.currentPage} of ${totalPages || 1} (${this.totalItems} total)
            </div>
            <div class="pagination-buttons">
                <button id="prev-page" ${this.currentPage <= 1 ? 'disabled' : ''}>Previous</button>
                <button id="next-page" ${this.currentPage >= totalPages ? 'disabled' : ''}>Next</button>
            </div>
        `;
    }

    /**
     * Update disk IO metrics UI
     */
    update(processedData) {
        // 1. Update Header Info
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        // 2. Process Object Data Structure
        const diskIO = processedData.disk_io;

        // Check object structure validity
        if (diskIO && diskIO.data) {
            this.diskIOData = diskIO.data;
            
            // Handle Pagination Info
            if (diskIO.pagination) {
                this.currentPage = diskIO.pagination.page || 1;
                this.totalItems = diskIO.pagination.total || 0;
                if (diskIO.pagination.per_page) {
                    this.perPage = diskIO.pagination.per_page;
                }
            } else {
                // Fallback for Range mode
                this.totalItems = this.diskIOData.length;
            }
            
            this.updateDiskIOTable();
        }
    }
}