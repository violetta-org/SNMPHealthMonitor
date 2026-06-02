/**
 * History Dashboard Module (Chart.js version)
 * Handles history page logic (charts, date range, PDF export)
 */
import { BaseDashboardUI } from './base.js';

export class HistoryDashboard extends BaseDashboardUI {
    constructor(dataProcessor) {
        super(dataProcessor);
        this.charts = {};
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
    }

    /**
     * Set preset time range
     */
    setPresetRange(range) {
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
            const queryParams = new URLSearchParams({
                start_time: start.toISOString(),
                end_time: end.toISOString(),
                metrics: metrics.join(',')
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

        const metricsContainer = document.getElementById('metrics-container');
        if (metricsContainer) metricsContainer.style.display = 'block';

        document.querySelectorAll('.metric-panel').forEach(panel => {
            panel.style.display = 'none';
        });

        if (data.error) {
            this.showError(data.error);
            return;
        }

        if (data.cpu) this.renderChart('cpu', 'CPU Usage (%)', data.cpu, '#FF4560');
        if (data.memory) this.renderChart('memory', 'Memory Usage (GB)', data.memory, '#00E396');
        if (data.disk_usage) this.renderChart('disk', 'Disk Usage (%)', data.disk_usage, '#FEB019');
        else if (data.disk) this.renderChart('disk', 'Disk Usage (%)', data.disk, '#FEB019');

        if (data.network) this.renderChart('network', 'Throughput', data.network, '#775DD0');
        if (data.temperature) this.renderChart('temp', 'Temperature (°C)', data.temperature, '#FF8A00');
        else if (data.temp) this.renderChart('temp', 'Temperature (°C)', data.temp, '#FF8A00');
    }

    /**
     * Render or update a chart
     */
    renderChart(metric, title, dataPoints, color) {
        const chartId = `chart-${metric}`;
        const panelId = `panel-${metric}`;

        const panel = document.getElementById(panelId);
        if (panel) panel.style.display = 'block';

        const container = document.getElementById(chartId);
        if (!container) return;

        let canvas = container.querySelector('canvas');
        if (!canvas) {
            canvas = document.createElement('canvas');
            container.appendChild(canvas);
        }

        let datasets = [];
        let yAxisFormatter = (val) => val.toFixed(0);
        let labels = [];

        try {
            if (metric === 'network') {
                labels = dataPoints.map(p => {
                    const d = new Date(p.time);
                    return isNaN(d.getTime()) ? '' : d.toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
                });

                const uploadData = dataPoints.map(p => Number(p.send_bytes_s || p.send_rate) || 0);
                const downloadData = dataPoints.map(p => Number(p.recv_bytes_s || p.recv_rate) || 0);

                datasets = [
                    {
                        label: 'Upload',
                        data: uploadData,
                        borderColor: '#FF6B6B',
                        backgroundColor: 'rgba(255, 107, 107, 0.15)',
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    },
                    {
                        label: 'Download',
                        data: downloadData,
                        borderColor: '#1DD1A1',
                        backgroundColor: 'rgba(29, 209, 161, 0.15)',
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    }
                ];

                yAxisFormatter = (val) => {
                    if (val === 0) return '0 B/s';
                    const k = 1024;
                    const sizes = ['B/s', 'KB/s', 'MB/s', 'GB/s'];
                    const i = Math.floor(Math.log(val) / Math.log(k));
                    return parseFloat((val / Math.pow(k, i)).toFixed(2)) + ' ' + (sizes[i] || 'B/s');
                };

            } else if (metric === 'disk') {
                const mounts = {};
                dataPoints.forEach(p => {
                    const mount = p.mount || 'root';
                    if (!mounts[mount]) mounts[mount] = [];
                    mounts[mount].push({
                        time: p.time,
                        val: Number(p.percent) || 0
                    });
                });

                const firstMount = Object.keys(mounts)[0];
                if (firstMount) {
                    labels = mounts[firstMount].map(p => {
                        const d = new Date(p.time);
                        return isNaN(d.getTime()) ? '' : d.toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
                    });
                }

                const colors = ['#FEB019', '#008FFB', '#00E396', '#775DD0'];
                datasets = Object.keys(mounts).map((mount, index) => {
                    const col = colors[index % colors.length];
                    return {
                        label: mount,
                        data: mounts[mount].map(p => p.val),
                        borderColor: col,
                        backgroundColor: col + '26',
                        fill: true,
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3
                    };
                });

                yAxisFormatter = (val) => val.toFixed(0) + '%';

            } else {
                labels = dataPoints.map(p => {
                    const dateVal = p.time || p.timestamp;
                    const d = new Date(dateVal);
                    return isNaN(d.getTime()) ? '' : d.toLocaleString('en-US', { month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false });
                });

                const seriesData = dataPoints.map(p => {
                    let val = 0;
                    if (metric === 'cpu') {
                        val = p.percent;
                    } else if (metric === 'memory') {
                        const total = Number(p.total) || 0;
                        const free = Number(p.free) || 0;
                        const buffers = Number(p.buffers) || 0;
                        const cached = Number(p.cached) || 0;

                        if (p.buffers !== undefined && p.cached !== undefined) {
                            val = (total - free - buffers - cached);
                        } else {
                            val = Number(p.used) || 0;
                        }
                        val = val / 1024 / 1024 / 1024;
                    } else if (metric === 'temp') {
                        val = p.cpu_temp;
                    }
                    return Number(val) || 0;
                });

                datasets = [{
                    label: title,
                    data: seriesData,
                    borderColor: color,
                    backgroundColor: color + '26',
                    fill: true,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.3
                }];

                if (metric === 'memory') yAxisFormatter = (val) => val.toFixed(2) + ' GB';
                if (metric === 'cpu' || metric === 'temp') yAxisFormatter = (val) => val.toFixed(1) + (metric === 'cpu' ? '%' : '°C');
            }
        } catch (e) {
            console.warn(`[HistoryDashboard] Error parsing data for ${metric}`, e);
            return;
        }

        let minY = undefined;
        let maxY = undefined;
        if (metric === 'cpu' || metric === 'disk') {
            minY = 0;
            maxY = 100;
        } else if (metric === 'memory' && dataPoints && dataPoints.length > 0) {
            minY = 0;
            const sample = dataPoints[0];
            const totalBytes = Number(sample.total) || 0;
            if (totalBytes > 0) {
                const totalGB = totalBytes / 1024 / 1024 / 1024;
                maxY = Math.ceil(totalGB * 2) / 2;
            }
        }

        if (this.charts[metric]) {
            this.charts[metric].data.labels = labels;
            this.charts[metric].data.datasets = datasets;
            this.charts[metric].options.scales.y.min = minY;
            this.charts[metric].options.scales.y.max = maxY;
            this.charts[metric].options.scales.y.ticks.callback = yAxisFormatter;
            this.charts[metric].options.scales.y.title.text = title;
            this.charts[metric].update('none');
        } else {
            const ctx = canvas.getContext('2d');
            this.charts[metric] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: labels,
                    datasets: datasets
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    animation: false,
                    plugins: {
                        legend: {
                            display: metric === 'network' || metric === 'disk',
                            position: 'top',
                            align: 'end',
                            labels: { color: '#ccc', font: { family: 'Inter, sans-serif', size: 11 } }
                        },
                        tooltip: {
                            mode: 'index',
                            intersect: false,
                            backgroundColor: '#1a1a1a',
                            titleColor: '#fff',
                            bodyColor: '#e0e0e0',
                            borderWidth: 1,
                            callbacks: {
                                label: (context) => {
                                    const val = context.parsed.y;
                                    return `${context.dataset.label}: ${yAxisFormatter(val)}`;
                                }
                            }
                        }
                    },
                    scales: {
                        x: {
                            grid: { color: '#333' },
                            ticks: { color: '#aaa', font: { size: 10 } }
                        },
                        y: {
                            min: minY,
                            max: maxY,
                            grid: { color: '#333' },
                            ticks: {
                                color: color,
                                font: { size: 10 },
                                callback: yAxisFormatter
                            },
                            title: {
                                display: true,
                                text: title,
                                color: color,
                                font: { size: 12, weight: 600 }
                            }
                        }
                    }
                }
            });
        }
    }

    /**
     * Handle Export PDF
     */
    handleExportPDF() {
        this.showToast('Exporting PDF...', 'info');
    }

    /**
     * Clean up Chart.js instances on destroy
     */
    destroy() {
        Object.values(this.charts).forEach(chart => {
            if (chart && typeof chart.destroy === 'function') {
                chart.destroy();
            }
        });
        this.charts = {};
    }
}
