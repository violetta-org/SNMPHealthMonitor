/**
 * SystemStatus Dashboard Module
 * Handles system status page (aggregated metrics)
 */
import { BaseDashboardUI } from '/static/js/dashboard/base.js';
import { MemoryChart } from '/static/js/memory-chart.js';
import { MemoryPercentChart } from '/static/js/memory-percent-chart.js';

export class SystemStatusDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.cpuCoresInitialized = false;
        // Khởi tạo các chart instance
        this.memoryChart = new MemoryChart();
        this.memoryPercentChart = new MemoryPercentChart();
    }

    /**
     * Register UI elements for systemstatus page
     * Ánh xạ các ID trong HTML vào biến để update sau này
     */
    registerElements() {
        // Header elements
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
        
        // System info
        this.registerElement('sysname', '#sysname');
        this.registerElement('sys-location', '#sys-location');
        this.registerElement('sys-uptime', '#sys-uptime');
        
        // CPU Global: removed Total CPU display; per-core gauges are created dynamically
        
        // Memory Section
        this.registerElement('memory-gauge', '#memory-gauge');
        this.registerElement('memory-value', '#memory-value');
        this.registerElement('memory-total', '#memory-total');
        this.registerElement('memory-free', '#memory-free');
        this.registerElement('memory-used', '#memory-used');
        this.registerElement('memory-total-detail', '#memory-total-detail');
        
        // Swap Section
        this.registerElement('swap-gauge', '#swap-gauge');
        this.registerElement('swap-value', '#swap-value');
        this.registerElement('swap-total', '#swap-total');
        this.registerElement('swap-free', '#swap-free');
        this.registerElement('swap-used', '#swap-used');
        this.registerElement('swap-total-detail', '#swap-total-detail');
        
        // Load averages
        this.registerElement('load-1m-gauge', '#load-1m-gauge');
        this.registerElement('load-1m-value', '#load-1m-value');
        this.registerElement('load-5m-gauge', '#load-5m-gauge');
        this.registerElement('load-5m-value', '#load-5m-value');
        this.registerElement('load-15m-gauge', '#load-15m-gauge');
        this.registerElement('load-15m-value', '#load-15m-value');
        
        // Temperature
        this.registerElement('temperature-gauge', '#temperature-gauge');
        this.registerElement('temperature-value', '#temperature-value');
        this.registerElement('temperature-info', '#temperature-info');
    }

    /**
     * Update system status UI
     * Hàm này được gọi mỗi khi có dữ liệu mới từ WebSocket
     */
    update(processedData) {
        // console.log('[SystemStatusDashboard] Updating UI with data');
        
        // 1. Update device info (online status, last_seen, ip)
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        // 2. System info details
        if (processedData.system_info) {
            this.updateText('sysname', processedData.system_info.sysname || 'N/A');
            this.updateText('sys-location', processedData.system_info.sys_location || 'N/A');
            this.updateText('sys-uptime', this.dataProcessor.formatUptime(processedData.system_info.sys_uptime));
        }

        // 3. CPU Cores (Vẽ từng core)
        if (processedData.cpu_percent && Array.isArray(processedData.cpu_percent)) {
            this.updateCPUCores(processedData.cpu_percent);
        }

        // 4. Memory Updates
        if (processedData.memory) {
            const memPercent = processedData.memory.percent || 0;
            // Update Gauges: value + unit now inside the gauge
            this.updateGauge('memory', memPercent);
            this.updateText('memory-used', this.dataProcessor.formatBytes(processedData.memory.used));
            this.updateText('memory-total', this.dataProcessor.formatBytes(processedData.memory.total));
            this.updateText('memory-total-detail', this.dataProcessor.formatBytes(processedData.memory.total));
            this.updateText('memory-free', this.dataProcessor.formatBytes(processedData.memory.free));

            // Update Realtime Charts
            if (processedData.memory.time) {
                // Chart vùng (Stacked Area)
                this.memoryChart.appendData(processedData.memory);
                
                // Chart đường (Percent)
                this.memoryPercentChart.appendData({
                    time: processedData.memory.time,
                    percent: processedData.memory.percent
                });
            }
        }

        // 5. Memory History (Chỉ chạy khi load lần đầu để fill biểu đồ)
        if (processedData.memory_history && processedData.memory_history.length > 0) {
            this.memoryChart.updateHistory(processedData.memory_history);
        }
        if (processedData.memory_percent_history && processedData.memory_percent_history.length > 0) {
            this.memoryPercentChart.updateHistory(processedData.memory_percent_history);
        }

        // 6. Swap Updates
        if (processedData.swap) {
            const swapPercent = processedData.swap.percent || 0;
            this.updateGauge('swap', swapPercent);
            this.updateText('swap-used', this.dataProcessor.formatBytes(processedData.swap.used));
            this.updateText('swap-total', this.dataProcessor.formatBytes(processedData.swap.total));
            this.updateText('swap-total-detail', this.dataProcessor.formatBytes(processedData.swap.total));
            this.updateText('swap-free', this.dataProcessor.formatBytes(processedData.swap.free));
        }

        // 7. Load Averages
        if (processedData.load_avg) {
            // Normalize loads to percentage: use cpu count to scale
            const cpuCount = processedData.cpu_percent ? processedData.cpu_percent.length : 1;
            const load1 = (processedData.load_avg.load_1m || 0) / cpuCount * 100;
            const load5 = (processedData.load_avg.load_5m || 0) / cpuCount * 100;
            const load15 = (processedData.load_avg.load_15m || 0) / cpuCount * 100;

            this.updateGauge('load-1m', load1);
            this.updateGauge('load-5m', load5);
            this.updateGauge('load-15m', load15);
        }

        // 8. Temperature (show value inside gauge and unit °C)
        if (processedData.temperature && processedData.temperature.cpu_temp !== undefined) {
            const temp = processedData.temperature.cpu_temp;
            this.updateGauge('temperature', temp !== null ? temp : 0);
        }
    }

    /**
     * Logic vẽ các gauge nhỏ cho từng Core CPU
     */
    updateCPUCores(cpuData) {
        const container = document.getElementById('cpu-cores-container');
        if (!container) return;

        // Nếu số lượng core thay đổi hoặc chưa init, vẽ lại khung HTML
        if (!this.cpuCoresInitialized || container.children.length !== cpuData.length) {
            container.innerHTML = '';
            cpuData.forEach((cpu, index) => {
                container.appendChild(this.createCPUCoreGauge(index));
            });
            this.cpuCoresInitialized = true;
        }

        // Update giá trị từng core
        cpuData.forEach((cpu, index) => {
            const percent = cpu.percent || 0;
            const gaugeId = `cpu-core-${index}`;
            const gaugeElement = document.getElementById(`${gaugeId}-gauge`);
                const valueElement = document.getElementById(`${gaugeId}-value`);
            
            if (gaugeElement && valueElement) {
                const progressCircle = gaugeElement.querySelector('.gauge-progress');
                if (progressCircle) {
                    const circumference = 2 * Math.PI * 45;
                    const offset = circumference - (percent / 100) * circumference;
                    progressCircle.style.strokeDashoffset = offset;
                }
                    // Show one decimal and put unit in gauge-unit if exists
                    valueElement.textContent = percent.toFixed(1);
                    const unitEl = document.getElementById(`${gaugeId}-unit`);
                    if (unitEl) unitEl.textContent = '%';
            }
        });
    }

    createCPUCoreGauge(coreIndex) {
        const div = document.createElement('div');
        // Use the same markup as Memory/Swap gauges so CPU core cards look identical
        const gaugeId = `cpu-core-${coreIndex}`;
        div.className = 'gauge-card';
        div.innerHTML = `
            <h3>Core ${coreIndex + 1}</h3>
            <div class="gauge-wrapper">
                <svg id="${gaugeId}-gauge" class="gauge" viewBox="0 0 120 120">
                    <circle class="gauge-background" cx="60" cy="60" r="45"></circle>
                    <circle class="gauge-progress" cx="60" cy="60" r="45"></circle>
                </svg>
                <div class="gauge-content">
                    <span id="${gaugeId}-value" class="gauge-value">0.0</span>
                    <span id="${gaugeId}-unit" class="gauge-unit">%</span>
                </div>
            </div>
        `;
        return div;
    }
}

/**
 * Hàm Factory quan trọng mà dashboard.js gọi tới.
 * Hàm này khởi tạo Dashboard, đăng ký DOM, và lắng nghe WebSocket.
 */
export function initTopicDashboard(sysname, topic, wsManager, dataProcessor) {
    console.log(`[SystemStatus] Init for ${sysname}, topic: ${topic}`);
    
    // 1. Khởi tạo UI Class
    const dashboard = new SystemStatusDashboard(dataProcessor);
    
    // 2. Đăng ký các phần tử DOM (tìm ID trong HTML)
    dashboard.registerElements();
    
    // 3. Khởi tạo Chart (nếu cần thiết phải gọi init manual, nhưng constructor đã làm rồi)
    // dashboard.memoryChart.init(); 
    // dashboard.memoryPercentChart.init();

    // 4. Định nghĩa hàm xử lý sự kiện message từ WebSocket
    const handleMessage = (message) => {
        // Kiểm tra đúng loại dữ liệu
        if (message.type === 'data') {
            // Xử lý dữ liệu thô thành dữ liệu sạch
            const processedData = dataProcessor.process(topic, message.data);
            
            // Cập nhật lên giao diện
            if (processedData) {
                dashboard.update(processedData);
            }
        }
    };

    // 5. Đăng ký lắng nghe sự kiện
    wsManager.on('message', handleMessage);

    // 6. Trả về object có hàm destroy để dọn dẹp khi chuyển trang
    return {
        destroy: () => {
            console.log('[SystemStatus] Destroying...');
            wsManager.off('message', handleMessage); // Gỡ bỏ lắng nghe socket
            if (dashboard.memoryChart) dashboard.memoryChart.destroy();
            if (dashboard.memoryPercentChart) dashboard.memoryPercentChart.destroy();
        }
    };
}