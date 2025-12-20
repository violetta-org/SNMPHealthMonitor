/**
 * SystemStatus Dashboard Module
 * Handles system status page (aggregated metrics)
 */
import { BaseDashboardUI } from './base.js';
import { initializeSystemCharts } from '../system-chart.js';

export class SystemStatusDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.cpuCoresInitialized = false;

        // Initialize charts ONCE on page load (total RAM line will be set later when available)
        if (!this.isInitialized) {
            this.charts = initializeSystemCharts(undefined); // { ramUsageChart, ramPercentChart, swapChart, dataManager }
            this.isInitialized = true;
        }

        // Local data buffers mapped by series index
        this.ramAppUsedData = [];
        this.ramPercentData = [];
        this.swapData = [];

        // Flags
        this.totalRamMarkSet = false;
        this._ramHistoryLoaded = false;
        this._percentHistoryLoaded = false;

        // Update throttling (max 1 per 500ms)
        this._throttleInterval = 500;
        this._lastFlush = 0;
        this._pendingFrame = false;
        this._latestData = null;

        // Live-only mode (history disabled)
    }

    /**
     * Register UI elements for systemstatus page
     */
    registerElements() {
        // Header elements
        this.registerElement('connection-status', '#connection-status');
        this.registerElement('last-update-time', '#last-update-time');
        
        // System info
        this.registerElement('sysname', '#sysname');
        this.registerElement('sys-location', '#sys-location');
        this.registerElement('sys-uptime', '#sys-uptime');
        
        // CPU
        // Focus on CPU cores only (no overall gauge)
        
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
     */
    update(processedData) {
        // Throttle incoming UI updates to avoid render flood
        this._latestData = processedData;
        const now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        const delta = now - this._lastFlush;
        if (delta < this._throttleInterval) {
            if (!this._pendingFrame) {
                this._pendingFrame = true;
                const delay = Math.max(0, this._throttleInterval - delta);
                setTimeout(() => {
                    this._pendingFrame = false;
                    this.update(this._latestData);
                }, delay);
            }
            return;
        }
        this._lastFlush = now;

        console.log('[SystemStatusDashboard] Updating system status UI', processedData);
        
        // Update device info (online status, last_seen, ip_address)
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }
        
        // System info
        if (processedData.system_info) {
            this.updateText('sysname', processedData.system_info.sysname || 'N/A');
            this.updateText('sys-location', processedData.system_info.sys_location || 'N/A');
            this.updateText('sys-uptime', this.dataProcessor.formatUptime(processedData.system_info.sys_uptime));
        }

        // CPU cores individually
        if (processedData.cpu_percent && processedData.cpu_percent.length > 0) {
            this.updateCPUCores(processedData.cpu_percent);
        }

        // Memory
        if (processedData.memory) {
            // Set fixed RAM scale once when total becomes available
            if (!this.totalRamMarkSet && processedData.memory.total) {
                this.totalRamBytes = processedData.memory.total;
                this.totalRamGB = this.totalRamBytes / (1024 * 1024 * 1024);
                this.charts.ramUsageChart.setOption({ yAxis: { min: 0, max: this.totalRamGB } });
                this.totalRamMarkSet = true;
            }
            
            // Live-only streaming update
            const timeLabel = processedData.memory.time ? new Date(processedData.memory.time).toISOString() : new Date().toISOString();
            const mem = processedData.memory;
            const total = Number(mem.total || 0);
            const free = Number(mem.free || 0);
            const buffers = Number(mem.buffers || 0);
            const cached = Number(mem.cached || 0);
            const appUsedBytes = Math.max(0, total - free - buffers - cached);
            const formatted = this.charts.dataManager.addDataPoint(
                timeLabel,
                appUsedBytes,
                0,
                mem.percent !== undefined ? mem.percent : 0,
                processedData.swap ? (processedData.swap.used || 0) : 0
            );

            this.ramAppUsedData.push(formatted.ramUsed);
            this.ramPercentData.push(formatted.ramPercent);
            this.swapData.push(formatted.swapUsed);

            // Update RAM metrics legend row
            const fmt = (v) => this.dataProcessor.formatBytes(v);
            const bufEl = document.getElementById('ram-buffers');
            const cacheEl = document.getElementById('ram-cached');
            const freeEl = document.getElementById('ram-free');
            if (bufEl) bufEl.textContent = fmt(buffers);
            if (cacheEl) cacheEl.textContent = fmt(cached);
            if (freeEl) freeEl.textContent = fmt(free);

            // One-time debug: prove numeric types after casting
            if (!this._debugLogged) {
                console.log('DEBUG DATA TYPE:', typeof formatted.ramUsed, formatted.ramUsed, typeof formatted.ramPercent, formatted.ramPercent);
                this._debugLogged = true;
            }

            this.charts.dataManager.updateChart(this.charts.ramUsageChart, { 0: this.ramAppUsedData });
            this.charts.dataManager.updateChart(this.charts.ramPercentChart, { 0: this.ramPercentData });
            this.charts.dataManager.updateChart(this.charts.swapChart, { 0: this.swapData });
        }
        // Swap handled together with memory via dataManager

        // Load Averages
        if (processedData.load_avg) {
            const cpuCount = processedData.cpu_percent ? processedData.cpu_percent.length : 1;
            
            this.updateGauge('load-1m', (processedData.load_avg.load_1m || 0) / cpuCount * 100);
            this.updateGauge('load-5m', (processedData.load_avg.load_5m || 0) / cpuCount * 100);
            this.updateGauge('load-15m', (processedData.load_avg.load_15m || 0) / cpuCount * 100);
        }

        // Temperature
        if (processedData.temperature && processedData.temperature.cpu_temp !== null && processedData.temperature.cpu_temp !== undefined) {
            const temp = processedData.temperature.cpu_temp;
            // Temperature gauge: 0-100°C scale (0% = 0°C, 100% = 100°C)
            const tempPercent = Math.min(Math.max((temp / 100) * 100, 0), 100);
            this.updateGauge('temperature', tempPercent);
            this.updateText('temperature-value', temp.toFixed(1) + '°C');
        } else {
            this.updateText('temperature-value', 'N/A');
        }
    }

    // Charts are synchronized via echarts.connect in initializeSystemCharts

    attachWebSocketManager(wsManager, sysname, topic) {
        this.wsManager = wsManager;
        this.sysname = sysname;
        this.topic = topic;
    }

    clearCharts() {
        // Reset buffers and time axis
        this.ramUsedData = [];
        this.ramCachedData = [];
        this.ramPercentData = [];
        this.swapData = [];
        if (this.charts && this.charts.dataManager) {
            this.charts.dataManager.timeData = [];
        }
        if (this.charts) {
            this.charts.ramUsageChart.setOption({ xAxis: { data: [] }, series: [{ data: [] }, { data: [] }, {}] });
            this.charts.ramPercentChart.setOption({ xAxis: { data: [] }, series: [{ data: [] }] });
            this.charts.swapChart.setOption({ xAxis: { data: [] }, series: [{ data: [] }] });
        }
        this._ramHistoryLoaded = false;
        this._percentHistoryLoaded = false;
    }

    setTimeRange(rangeType, customStart = null, customEnd = null) {
        this.currentRange = rangeType;
        const now = new Date();
        let start, end;
        if (rangeType === 'live') {
            // last 15 minutes history + resume streaming
            start = new Date(now.getTime() - 15 * 60 * 1000);
            end = now;
            this.acceptStreaming = true;
        } else if (rangeType === '1h') {
            start = new Date(now.getTime() - 60 * 60 * 1000);
            end = now;
            this.acceptStreaming = false;
        } else if (rangeType === '6h') {
            start = new Date(now.getTime() - 6 * 60 * 60 * 1000);
            end = now;
            this.acceptStreaming = false;
        } else if (rangeType === '24h') {
            start = new Date(now.getTime() - 24 * 60 * 60 * 1000);
            end = now;
            this.acceptStreaming = false;
        } else if (rangeType === '7d') {
            start = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            end = now;
            this.acceptStreaming = false;
        } else if (rangeType === 'custom' && customStart && customEnd) {
            start = new Date(customStart);
            end = new Date(customEnd);
            this.acceptStreaming = false;
        } else {
            return;
        }

        if (!this.wsManager || !this.sysname) return;
        this.clearCharts();
        this.wsManager.queryRange({
            sysname: this.sysname,
            topic: this.topic || 'systemstatus',
            start_time: start.toISOString(),
            end_time: end.toISOString()
        });
    }

    /**
     * Update CPU cores display
     */
    updateCPUCores(cpuData) {
        const container = document.getElementById('cpu-cores-container');
        if (!container) {
            console.warn('[SystemStatusDashboard] CPU cores container not found');
            return;
        }

        // Check if we need to re-initialize (first time or core count changed)
        const currentCoreCount = container.children.length;
        const newCoreCount = cpuData.length;
        
        if (!this.cpuCoresInitialized || currentCoreCount !== newCoreCount) {
            container.innerHTML = '';
            
            cpuData.forEach((cpu, index) => {
                const coreCard = this.createCPUCoreGauge(index);
                container.appendChild(coreCard);
            });
            
            this.cpuCoresInitialized = true;
            console.log(`[SystemStatusDashboard] Initialized ${cpuData.length} CPU core gauges`);
        }

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
                
                valueElement.textContent = Math.round(percent) + '%';
            }
        });
    }

    /**
     * Create a single CPU core gauge element
     */
    createCPUCoreGauge(coreIndex) {
        const card = document.createElement('div');
        card.className = 'cpu-core-card';
        
        const gaugeId = `cpu-core-${coreIndex}`;
        
        card.innerHTML = `
            <svg id="${gaugeId}-gauge" class="cpu-core-gauge" viewBox="0 0 120 120">
                <circle class="gauge-background" cx="60" cy="60" r="45" fill="none" stroke="#3a4d5f" stroke-width="8"/>
                <circle class="gauge-progress" cx="60" cy="60" r="45" fill="none" stroke="#00bcd4" stroke-width="8" 
                        stroke-dasharray="283" stroke-dashoffset="283" transform="rotate(-90 60 60)" stroke-linecap="round"/>
                <text x="60" y="55" text-anchor="middle" class="gauge-value" id="${gaugeId}-value">0%</text>
                <text x="60" y="70" text-anchor="middle" class="gauge-sublabel">Core ${coreIndex}</text>
            </svg>
            <div class="gauge-info">CPU ${coreIndex}</div>
        `;
        
        return card;
    }
}

