/**
 * History Dashboard Module
 * Handles history page logic (charts, date range, PDF export)
 */
import { BaseDashboardUI } from './base.js';

export class HistoryDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.charts = {};
        this.chartOptions = {
            chart: {
                type: 'area', // Use area charts for history
                height: 300,
                animations: { enabled: false }, // Disable animations for large datasets
                toolbar: { show: false },
                background: 'transparent',
                fontFamily: 'Inter, sans-serif'
            },
            stroke: { curve: 'straight', width: 2 },
            markers: {
                size: 0,
                colors: ['#fff'],
                strokeColors: ['#FF4560', '#00E396', '#775DD0', '#FEB019'],
                strokeWidth: 0,
                hover: { size: 6 }
            },
            dataLabels: { enabled: false },
            grid: {
                borderColor: '#333',
                strokeDashArray: 3,
                padding: { top: 0, right: 0, bottom: 0, left: 10 }
            },
            xaxis: {
                type: 'datetime',
                labels: { style: { colors: '#aaa', fontSize: '11px' } },
                axisBorder: { show: false },
                axisTicks: { color: '#444' }
            },
            theme: { mode: 'dark' }
        };
    }

    /**
     * Register UI elements for history page
     */
    registerElements() {
        this.registerElement('start-time', '#start-time');
        this.registerElement('end-time', '#end-time');
        this.registerElement('hist-generate', '#hist-generate');
        this.registerElement('hist-export-pdf', '#hist-export-pdf');

        // Buttons
        const generateBtn = this.elements.get('hist-generate');
        if (generateBtn) {
            generateBtn.addEventListener('click', () => this.handleGenerate());
        }

        const exportBtn = this.elements.get('hist-export-pdf');
        if (exportBtn) {
            exportBtn.addEventListener('click', () => this.handleExportPDF());
        }

        // Preset buttons
        const presetBtns = document.querySelectorAll('.preset-buttons button');
        presetBtns.forEach(btn => {
            btn.addEventListener('click', (e) => {
                const range = e.target.getAttribute('data-range');
                this.setPresetRange(range);
            });
        });

        // Clear preset active state when manually changing inputs
        const startInput = this.elements.get('start-time');
        const endInput = this.elements.get('end-time');

        const clearActivePresets = () => {
            presetBtns.forEach(btn => btn.classList.remove('active'));
        };

        if (startInput) startInput.addEventListener('change', clearActivePresets);
        if (endInput) endInput.addEventListener('change', clearActivePresets);

        // Initialize default time range (last 24h)
        this.setPresetRange('24h');
    }

    /**
     * Attach WebSocket Manager
     */
    attachWebSocketManager(wsManager, sysname, topic) {
        this.wsManager = wsManager;
        this.sysname = sysname;
        this.topic = topic;

        // Server metadata is now injected server-side.
        // this.fetchServerMetadata();
    }

    // Server metadata fetch logic removed.
    // fetchServerMetadata() { ... }

    /**
     * Set preset time range
     */
    setPresetRange(range) {
        // Update active state on buttons
        document.querySelectorAll('.preset-buttons button').forEach(btn => {
            if (btn.getAttribute('data-range') === range) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        });

        const end = new Date();
        let start = new Date();

        switch (range) {
            case '1h': start.setHours(end.getHours() - 1); break;
            case '6h': start.setHours(end.getHours() - 6); break;
            case '24h': start.setHours(end.getHours() - 24); break;
            case '7d': start.setDate(end.getDate() - 7); break;
            default: return; // Custom or invalid
        }

        // Format for datetime-local input: YYYY-MM-DDTHH:mm
        const fmt = d => d.getFullYear() + '-' +
            String(d.getMonth() + 1).padStart(2, '0') + '-' +
            String(d.getDate()).padStart(2, '0') + 'T' +
            String(d.getHours()).padStart(2, '0') + ':' +
            String(d.getMinutes()).padStart(2, '0');

        const startEl = this.elements.get('start-time');
        const endEl = this.elements.get('end-time');

        if (startEl) startEl.value = fmt(start);
        if (endEl) endEl.value = fmt(end);
    }

    /**
     * Handle "Generate" button click
     */
    async handleGenerate() {
        const startEl = this.elements.get('start-time');
        const endEl = this.elements.get('end-time');

        if (!startEl || !endEl) return;

        const start = new Date(startEl.value);
        const end = new Date(endEl.value);

        if (isNaN(start.getTime()) || isNaN(end.getTime())) {
            this.showWarning('Invalid date format');
            return;
        }

        if (start >= end) {
            this.showWarning('Start time must be before end time');
            return;
        }

        // Gather selected metrics
        const metrics = [];
        document.querySelectorAll('.metric-toggles input:checked').forEach(cb => {
            metrics.push(cb.value);
        });

        if (metrics.length === 0) {
            this.showWarning('Please select at least one metric');
            return;
        }

        this.showToast('Fetching data...', 'info');

        try {
            // Use HTTP API instead of WebSocket for complex queries
            const queryParams = new URLSearchParams({
                start_time: start.toISOString(),
                end_time: end.toISOString(),
                metrics: metrics.join(',') // Pass metrics as a comma-separated string
            });

            const response = await fetch(`/api/history/metrics/${this.sysname}?${queryParams.toString()}`);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(errorText || 'Failed to fetch data');
            }

            const data = await response.json();
            this.update(data);
            this.showToast('Data loaded successfully', 'success');

        } catch (error) {
            console.error('[HistoryDashboard] Error fetching history:', error);
            this.showError('Error loading history: ' + error.message);
        }
    }

    /**
     * Handle incoming data
     */
    update(data) {
        console.log('[HistoryDashboard] Received data:', data);

        // Hide spinner/loading state if applicable
        const metricsContainer = document.getElementById('metrics-container');
        if (metricsContainer) metricsContainer.style.display = 'block';

        // Reset visibility of ALL panels before showing valid ones
        // This fixes the bug where unselected metrics' empty containers persist
        document.querySelectorAll('.metric-panel').forEach(panel => {
            panel.style.display = 'none';
        });

        if (data.error) {
            this.showError(data.error);
            return;
        }

        // Process and display data for each requested metric
        if (data.cpu) this.renderChart('cpu', 'CPU Usage (%)', data.cpu, '#FF0000');
        if (data.memory) this.renderChart('memory', 'Memory Usage (GB)', data.memory, '#00E396');
        if (data.disk_usage) this.renderChart('disk', 'Disk Usage (%)', data.disk_usage, '#FEB019');
        else if (data.disk) this.renderChart('disk', 'Disk Usage (%)', data.disk, '#FEB019'); // Fallback

        if (data.network) this.renderChart('network', 'Throughput', data.network, '#775DD0'); // Title without fixed unit
        if (data.temperature) this.renderChart('temp', 'Temperature (°C)', data.temperature, '#FF4560');
        else if (data.temp) this.renderChart('temp', 'Temperature (°C)', data.temp, '#FF4560');
    }

    /**
     * Render or update a chart
     */
    renderChart(metric, title, dataPoints, color) {
        const chartId = `chart-${metric}`;
        const panelId = `panel-${metric}`;

        // Ensure panel is visible
        const panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'block';

        const container = document.getElementById(chartId);
        if (!container) return;

        // Map data fields based on metric type
        let series = [];
        let yAxisFormatter = (val) => val.toFixed(0);

        try {
            if (metric === 'network') {
                // Network has two series: Upload (send_bytes_s) and Download (recv_bytes_s) in Bytes/s
                const uploadData = dataPoints.map(p => ({
                    x: new Date(p.time).getTime(),
                    y: Number(p.send_bytes_s || p.send_rate) || 0
                }));
                const downloadData = dataPoints.map(p => ({
                    x: new Date(p.time).getTime(),
                    y: Number(p.recv_bytes_s || p.recv_rate) || 0
                }));

                series = [
                    { name: 'Upload', data: uploadData, color: '#FF6B6B' },
                    { name: 'Download', data: downloadData, color: '#1DD1A1' }
                ];

                // Dynamic formatter for Network
                yAxisFormatter = (val) => {
                    if (val === 0) return '0 B/s';
                    const k = 1024;
                    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
                    const i = Math.floor(Math.log(val) / Math.log(k));
                    return parseFloat((val / Math.pow(k, i)).toFixed(2)) + ' ' + (sizes[i] || 'B/s');
                };

            } else if (metric === 'disk') {
                // Disk might have multiple mount points (multiple series)
                // Group by mount point
                const mounts = {};
                dataPoints.forEach(p => {
                    const mount = p.mount || 'root';
                    if (!mounts[mount]) mounts[mount] = [];
                    mounts[mount].push({
                        x: new Date(p.time).getTime(),
                        y: (Number(p.percent) || 0).toFixed(1)
                    });
                });

                series = Object.keys(mounts).map((mount, index) => ({
                    name: mount,
                    data: mounts[mount],
                    // Generate varied colors if needed, or let ApexCharts handle it
                }));

                yAxisFormatter = (val) => val.toFixed(0) + '%';

            } else {
                // Single series metrics (CPU, Memory, Temp)
                const seriesData = dataPoints.map(p => {
                    let val = 0;
                    if (metric === 'cpu') {
                        val = p.percent;
                    }
                    else if (metric === 'memory') {
                        // Calculate used as Total - Free - Buffers - Cached
                        // Note: Backend might return 'used' which is total - free, 
                        // but 'available' is often a better metric for application perspective.
                        // User specifically asked for: Total - Free - Buffers - Cached.
                        // Depending on data availability (snapshot vs range):

                        const total = Number(p.total) || 0;
                        const free = Number(p.free) || 0;
                        const buffers = Number(p.buffers) || 0;
                        const cached = Number(p.cached) || 0;

                        // If buffers/cached are missing (e.g. range query might not aggregate them all depending on query), callback to 'used'
                        if (p.buffers !== undefined && p.cached !== undefined) {
                            val = (total - free - buffers - cached);
                        } else {
                            val = (Number(p.used) || 0);
                        }

                        val = val / 1024 / 1024 / 1024; // Convert to GB
                    }
                    else if (metric === 'temp') {
                        val = p.cpu_temp;
                    }

                    return {
                        x: new Date(p.time || p.timestamp).getTime(),
                        y: (Number(val) || 0)
                    };
                });
                series = [{ name: title, data: seriesData }];

                if (metric === 'memory') yAxisFormatter = (val) => val.toFixed(2) + ' GB';
                if (metric === 'cpu' || metric === 'temp') yAxisFormatter = (val) => val.toFixed(1) + (metric === 'cpu' ? '%' : '°C');
            }
        } catch (e) {
            console.warn(`[HistoryDashboard] Error parsing data for ${metric}`, e);
            return;
        }

        if (this.charts[metric]) {
            this.charts[metric].updateOptions({
                yaxis: {
                    labels: { formatter: yAxisFormatter },
                    title: { text: title, style: { color: color } } // Update title potentially
                },
                tooltip: { y: { formatter: yAxisFormatter } }
            });
            this.charts[metric].updateSeries(series);
        } else {
            const options = {
                ...this.chartOptions,
                colors: metric === 'network' ? ['#FF6B6B', '#1DD1A1'] : [color], // Override color for network
                series: series,
                yaxis: {
                    labels: {
                        style: { colors: color },
                        formatter: yAxisFormatter
                    },
                    title: { text: title, style: { color: color } }
                },
                tooltip: {
                    theme: 'dark',
                    x: { format: 'dd MMM HH:mm' },
                    y: { formatter: yAxisFormatter }
                }
            };

            // Fix Y-axis scaling
            if (metric === 'cpu' || metric === 'disk') {
                options.yaxis.min = 0;
                options.yaxis.max = 100;
            } else if (metric === 'memory') {
                options.yaxis.min = 0;
                // Find total memory from data to set Max (convert to GB)
                if (dataPoints && dataPoints.length > 0) {
                    const sample = dataPoints[0];
                    const totalBytes = Number(sample.total) || 0;
                    if (totalBytes > 0) {
                        // Round up to nearest 0.5 GB for a clean ceiling (e.g. 3.8GB -> 4.0GB)
                        const totalGB = totalBytes / 1024 / 1024 / 1024;
                        const ceiling = Math.ceil(totalGB * 2) / 2;
                        options.yaxis.max = ceiling;
                    }
                }
            }

            this.charts[metric] = new ApexCharts(container, options);
            this.charts[metric].render();
        }
    }

    /**
     * Handle Export PDF
     */
    handleExportPDF() {
        this.showToast('Exporting PDF...', 'info');
        // Implement PDF export logic here, potentially calling an API endpoint
        // window.open(`/api/export/pdf?sysname=${this.sysname}&...`);
    }
}
