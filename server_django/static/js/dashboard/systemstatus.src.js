/**
 * SystemStatus Dashboard Module
 * Handles system status page (aggregated metrics)
 */
import { BaseDashboardUI } from './base.js';
import { initializeSystemCharts, createCpuNetworkChart, updateCpuNetworkChart, appendCpuNetworkData } from '../system-chart.js';

export class SystemStatusDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.cpuCoresInitialized = false;

        // Track if chart has initial series rendered
        this.chartSeriesInitialized = false;

        // Initialize charts ONCE on page load (total RAM line will be set later when available)
        if (!this.isInitialized) {
            this.charts = initializeSystemCharts(undefined);
            // Initialize CPU+Network chart
            const cpuNetContainer = document.getElementById('cpu-network-chart');
            if (cpuNetContainer) {
                this.cpuNetworkChart = createCpuNetworkChart(cpuNetContainer);
            }
            this.isInitialized = true;
        }

        this.cpuCoreElementsCache = [];

        // Local data buffers mapped by series index
        this.ramAppUsedData = [];

        // CPU+Network data buffers
        this.cpuNetworkData = { cpu: [], network: [] };

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

    formatBytesIEC(bytes, decimals = 1) {
        const n = Number(bytes || 0);
        if (!Number.isFinite(n) || n <= 0) return '0 bytes';
        const k = 1024;
        const units = ['bytes', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.min(units.length - 1, Math.floor(Math.log(n) / Math.log(k)));
        if (i === 0) return `${Math.round(n)} bytes`;
        const v = n / Math.pow(k, i);
        return `${v.toFixed(decimals)} ${units[i]}`;
    }

    /**
     * Format memory total - round UP to nearest GB like Linux free command
     */
    formatMemoryTotal(bytes) {
        const n = Number(bytes || 0);
        if (!Number.isFinite(n) || n <= 0) return '0 GB';
        const gb = n / (1024 * 1024 * 1024);
        // Round UP to nearest integer GB (e.g., 3.8 GB -> 4 GB)
        return `${Math.ceil(gb)} GB`;
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

        // ==========================================
        // 1. DATA PREPARATION (No DOM Reads/Writes)
        // ==========================================
        let appUsedBytes = 0, buffers = 0, cached = 0, free = 0, memTotal = 0, memPct = '0.0', swapTotal = 0, swapUsed = 0, swapPct = '0.0';

        if (processedData.memory) {
            const mem = processedData.memory;
            memTotal = Number(mem.total || 0);
            appUsedBytes = Number(mem.used || 0);
            buffers = Number(mem.buffers || 0);
            cached = Number(mem.cached || 0);
            free = Number(mem.free || 0);

            if (!this.totalRamMarkSet && memTotal) {
                this.totalRamBytes = memTotal;
                this.totalRamGB = Math.ceil(this.totalRamBytes / (1024 * 1024 * 1024));
                this.totalRamMarkSet = true;
            }

            const timeLabel = mem.time ? new Date(mem.time).toISOString() : new Date().toISOString();
            const formatted = this.charts.dataManager.addDataPoint(timeLabel, appUsedBytes, buffers, cached, free);
            this.ramAppUsedData.push(formatted.ramAppUsed);
            
            memPct = mem.percent !== undefined && mem.percent !== null
                ? Number(mem.percent).toFixed(1)
                : (memTotal > 0 ? ((appUsedBytes / memTotal) * 100).toFixed(1) : '0.0');

            const swap = processedData.swap || {};
            swapTotal = Number(swap.total || 0);
            swapUsed = Number(swap.used || 0);
            swapPct = swapTotal > 0 ? ((swapUsed / swapTotal) * 100).toFixed(1) : '0.0';
        }

        if (this.cpuNetworkChart && processedData.cpu_percent && processedData.network) {
            this.updateCpuNetworkHistory(processedData.cpu_percent, processedData.network);
        }

        // ==========================================
        // 2. DOM WRITES (Text, Gauges, UI)
        // ==========================================
        if (processedData.device_info) {
            this.updateDeviceStatus(processedData.device_info);
            this.updateLastUpdateTime(processedData.device_info);
            this.updateServerIP(processedData.device_info);
        }

        if (processedData.system_info) {
            this.updateText('sysname', processedData.system_info.sysname || 'N/A');
            this.updateText('sys-location', processedData.system_info.sys_location || 'N/A');
            this.updateText('sys-uptime', this.dataProcessor.formatUptime(processedData.system_info.sys_uptime));
        }

        if (processedData.cpu_percent && processedData.cpu_percent.length > 0) {
            this.updateCPUCores(processedData.cpu_percent);
        }

        if (processedData.memory) {
            const fmt = (v) => this.formatBytesIEC(v, 1);
            const appEl = document.getElementById('val-app-used');
            const bufEl = document.getElementById('val-buffers');
            const cacheEl = document.getElementById('val-cached');
            const freeEl = document.getElementById('val-free');
            if (appEl) appEl.textContent = fmt(appUsedBytes);
            if (bufEl) bufEl.textContent = fmt(buffers);
            if (cacheEl) cacheEl.textContent = fmt(cached);
            if (freeEl) freeEl.textContent = fmt(free);

            const memSummaryEl = document.getElementById('mem-summary-text');
            if (memSummaryEl) memSummaryEl.textContent = `Memory: ${memPct}% (${this.formatBytesIEC(appUsedBytes, 1)} / ${this.formatMemoryTotal(memTotal)})`;

            const swapSummaryEl = document.getElementById('swap-summary-text');
            if (swapSummaryEl) swapSummaryEl.textContent = `Swap: ${swapPct}% (${this.formatBytesIEC(swapUsed, 0)} / ${this.formatMemoryTotal(swapTotal)})`;
        }

        if (processedData.load_avg) {
            const load1 = Number(processedData.load_avg.load_1m) || 0;
            const load5 = Number(processedData.load_avg.load_5m) || 0;
            const load15 = Number(processedData.load_avg.load_15m) || 0;

            this.updateGauge('load-1m', load1);
            this.updateGauge('load-5m', load5);
            this.updateGauge('load-15m', load15);

            const load1El = document.getElementById('load-1m-value');
            const load5El = document.getElementById('load-5m-value');
            const load15El = document.getElementById('load-15m-value');
            if (load1El) load1El.textContent = load1;
            if (load5El) load5El.textContent = load5;
            if (load15El) load15El.textContent = load15;

            const val1 = document.querySelector('#load-1m-gauge .gauge-value');
            const val5 = document.querySelector('#load-5m-gauge .gauge-value');
            const val15 = document.querySelector('#load-15m-gauge .gauge-value');
            if (val1) val1.textContent = load1;
            if (val5) val5.textContent = load5;
            if (val15) val15.textContent = load15;
        }

        if (processedData.temperature && processedData.temperature.cpu_temp !== null && processedData.temperature.cpu_temp !== undefined) {
            const temp = processedData.temperature.cpu_temp;
            const tempPercent = Math.min(Math.max((temp / 100) * 100, 0), 100);
            this.updateGauge('temperature', tempPercent);
            this.updateText('temperature-value', temp.toFixed(1) + '°C');
        } else {
            this.updateText('temperature-value', 'N/A');
        }

        if (this.cpuNetworkChart && processedData.cpu_percent && processedData.network) {
            this.updateCpuNetworkSummary(processedData.cpu_percent, processedData.network);
        }

        // ==========================================
        // 3. CHART UPDATES (Triggers Style Recalcs)
        // ==========================================
        if (processedData.memory && this.charts?.ramUsageChart) {
            // Update RAM total Y-axis max if set
            if (this.totalRamMarkSet && this.totalRamGB && typeof this.charts.ramUsageChart.options?.scales?.y?.max === 'undefined') {
                this.charts.ramUsageChart.options.scales.y.max = this.totalRamGB;
            }
            this.charts.dataManager.updateChart(this.charts.ramUsageChart, {
                0: this.ramAppUsedData
            });
        }

        if (this.cpuNetworkChart && processedData.cpu_percent && processedData.network) {
            updateCpuNetworkChart(this.cpuNetworkChart, this.cpuNetworkHistory.cpu, this.cpuNetworkHistory.network);
        }
    }

    /**
     * Accumulate Live Data into History Buffer for Chart
     * Handles both Live Snapshot (Array) and History Dump (Object)
     */
    updateCpuNetworkHistory(cpuData, networkData) {
        // Initialize if not exists
        if (!this.cpuNetworkHistory) {
            this.cpuNetworkHistory = { cpu: [], network: {} };
        }

        // --- HANDLE CPU ---
        // Case A: Live Snapshot (Array of Cores) -> Calculate Avg and Append
        // Case B: History (Array of Time Points) -> Replace/Merge
        if (Array.isArray(cpuData) && cpuData.length > 0) {
            // Heuristic: Check first element keys to distinguish Live Core vs History Point
            const first = cpuData[0];
            if (first.cpu !== undefined) {
                // Live Snapshot: [{cpu:'cpu0', percent:..., time:...}]
                let ts = first.time || new Date().toISOString();
                const sum = cpuData.reduce((acc, c) => acc + (Number(c.percent) || 0), 0);
                const avgPercent = sum / cpuData.length;
                this.cpuNetworkHistory.cpu.push({ time: ts, percent: avgPercent });
            } else if (first.percent !== undefined) {
                // History: [{time:..., percent:...}]
                // Replace buffer with history
                this.cpuNetworkHistory.cpu = cpuData.slice(); // Copy
            }
        }

        // Trim CPU Buffer
        if (this.cpuNetworkHistory.cpu.length > 300) {
            this.cpuNetworkHistory.cpu = this.cpuNetworkHistory.cpu.slice(-100);
        }


        // --- HANDLE NETWORK ---
        // Case A: Live Snapshot (Array of Objects) -> Append
        // Case B: History (Object of Arrays) -> Replace
        if (Array.isArray(networkData)) {
            // LIVE SNAPSHOT
            const ts = new Date().toISOString();
            networkData.forEach(net => {
                const iface = net.interface;
                if (!iface) return;

                if (!this.cpuNetworkHistory.network[iface]) {
                    this.cpuNetworkHistory.network[iface] = [];
                }

                this.cpuNetworkHistory.network[iface].push({
                    time: net.time || ts,
                    send_rate: Number(net.send_bytes_s) || 0,
                    recv_rate: Number(net.recv_bytes_s) || 0
                });

                // Trim per interface
                if (this.cpuNetworkHistory.network[iface].length > 100) {
                    this.cpuNetworkHistory.network[iface].shift();
                }
            });
        } else if (networkData && typeof networkData === 'object') {
            // HISTORY DUMP: {'eth0': [{time..., send_rate...}], ...}
            this.cpuNetworkHistory.network = {}; // Reset or Merge? Reset is safer for range query result
            for (const [iface, points] of Object.entries(networkData)) {
                if (Array.isArray(points)) {
                    this.cpuNetworkHistory.network[iface] = points.slice();
                }
            }
        }
    }

    /**
     * Update CPU/Network summary text values
     */
    updateCpuNetworkSummary(cpuData, networkData) {
        const cpuAvgEl = document.getElementById('cpu-avg-value');
        const uploadEl = document.getElementById('net-upload-value');
        const downloadEl = document.getElementById('net-download-value');

        if (cpuAvgEl && cpuData && cpuData.length > 0) {
            const lastCpu = cpuData[cpuData.length - 1];
            cpuAvgEl.textContent = `${Number(lastCpu.percent || 0).toFixed(1)}%`;
        }

        // Sum all network interfaces
        // Sum all network interfaces
        let totalSend = 0, totalRecv = 0;

        if (Array.isArray(networkData)) {
            // Live Update: Array of objects [{interface:..., send_bytes_s:..., recv_bytes_s:...}]
            networkData.forEach(net => {
                totalSend += Number(net.send_bytes_s || 0);
                totalRecv += Number(net.recv_bytes_s || 0);
            });
        } else if (networkData && typeof networkData === 'object') {
            // History: Object of arrays {'eth0': [{send_rate:..., recv_rate:...}]}
            for (const [iface, data] of Object.entries(networkData)) {
                if (Array.isArray(data) && data.length > 0) {
                    const last = data[data.length - 1];
                    totalSend += Number(last.send_rate || 0);
                    totalRecv += Number(last.recv_rate || 0);
                }
            }
        }

        if (uploadEl) uploadEl.textContent = this.formatNetworkRate(totalSend);
        if (downloadEl) downloadEl.textContent = this.formatNetworkRate(totalRecv);
    }

    /**
     * Format network rate to human-readable string
     */
    formatNetworkRate(bytesPerSec) {
        if (!Number.isFinite(bytesPerSec) || bytesPerSec < 0) return '0 B/s';
        if (bytesPerSec < 1024) return `${bytesPerSec.toFixed(0)} B/s`;
        if (bytesPerSec < 1024 * 1024) return `${(bytesPerSec / 1024).toFixed(1)} KB/s`;
        if (bytesPerSec < 1024 * 1024 * 1024) return `${(bytesPerSec / (1024 * 1024)).toFixed(2)} MB/s`;
        return `${(bytesPerSec / (1024 * 1024 * 1024)).toFixed(2)} GB/s`;
    }

    attachWebSocketManager(wsManager, sysname, topic) {
        this.wsManager = wsManager;
        this.sysname = sysname;
        this.topic = topic;
    }

    clearCharts() {
        // Reset buffers and time axis
        this.ramAppUsedData = [];
        if (this.charts && this.charts.dataManager) {
            this.charts.dataManager.timeData = [];
        }
        if (this.charts && this.charts.ramUsageChart) {
            // ApexCharts: clear series data
            this.charts.ramUsageChart.updateSeries([{ name: 'Used', data: [] }], true);
        }
        if (this.cpuNetworkChart) {
            this.cpuNetworkChart.updateSeries([
                { name: 'CPU %', data: [] },
                { name: 'Throughput', data: [] }
            ], true);
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
            this.cpuCoreElementsCache = [];

            cpuData.forEach((cpu, index) => {
                const coreCard = this.createCPUCoreGauge(index);
                container.appendChild(coreCard);
                
                this.cpuCoreElementsCache[index] = {
                    progressCircle: coreCard.querySelector('.gauge-progress'),
                    valueElement: coreCard.querySelector('.gauge-value')
                };
            });

            this.cpuCoresInitialized = true;
            console.log(`[SystemStatusDashboard] Initialized ${cpuData.length} CPU core gauges`);
        }

        cpuData.forEach((cpu, index) => {
            const percent = cpu.percent || 0;
            const cache = this.cpuCoreElementsCache[index];
            
            if (cache && cache.progressCircle && cache.valueElement) {
                const circumference = 2 * Math.PI * 45;
                const offset = circumference - (percent / 100) * circumference;
                cache.progressCircle.style.strokeDashoffset = offset;
                cache.valueElement.textContent = Math.round(percent) + '%';
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
