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

        // Charts will be lazily initialized once total memory is known
        this.charts = null; // { ramUsageChart, ramPercentChart, swapChart, dataManager }

        // Local data buffers mapped by series index
        this.ramUsedData = [];
        this.ramCachedData = [];
        this.ramPercentData = [];
        this.swapData = [];
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
        this.registerElement('cpu-gauge', '#cpu-gauge');
        this.registerElement('cpu-value', '#cpu-value');
        this.registerElement('cpu-count', '#cpu-count');
        
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
            
            // Also update average CPU gauge
            const avgCpu = processedData.cpu_percent.reduce((sum, cpu) => sum + (cpu.percent || 0), 0) / processedData.cpu_percent.length;
            this.updateGauge('cpu', avgCpu);
            this.updateText('cpu-count', processedData.cpu_percent.length + ' cores');
        }

        // Memory
        if (processedData.memory) {
            // Initialize charts when total memory is available
            if (!this.charts && processedData.memory.total) {
                this.charts = initializeSystemCharts(processedData.memory.total);
            }

            if (this.charts) {
                const timeLabel = processedData.memory.time || new Date().toISOString();
                const formatted = this.charts.dataManager.addDataPoint(
                    timeLabel,
                    processedData.memory.used || 0,
                    processedData.memory.cached || 0,
                    processedData.memory.percent !== undefined ? processedData.memory.percent : 0,
                    processedData.swap ? (processedData.swap.used || 0) : 0
                );

                // Push into local buffers
                this.ramUsedData.push(formatted.ramUsed);
                this.ramCachedData.push(formatted.ramCached);
                this.ramPercentData.push(formatted.ramPercent);
                this.swapData.push(formatted.swapUsed);

                // Apply updates via explicit index mapping
                this.charts.dataManager.updateChart(this.charts.ramUsageChart, {
                    0: this.ramUsedData,
                    1: this.ramCachedData
                });
                this.charts.dataManager.updateChart(this.charts.ramPercentChart, {
                    0: this.ramPercentData
                });
                this.charts.dataManager.updateChart(this.charts.swapChart, {
                    0: this.swapData
                });
            }
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

