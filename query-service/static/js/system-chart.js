/**
 * SYSTEM MONITOR CHARTS
 */

export function createRAMUsageChart(container, totalRAMBytes) {
    if (!container) return null;
    if (typeof ApexCharts === 'undefined') return null;

    // 1. Xử lý Total RAM: Làm tròn lên số nguyên gần nhất (ví dụ 3.8GB -> 4GB) để chia vạch cho đẹp
    let maxRAM = 4; // Default an toàn
    if (Number.isFinite(totalRAMBytes) && totalRAMBytes > 0) {
        const exactGB = totalRAMBytes / (1024 * 1024 * 1024);
        maxRAM = Math.ceil(exactGB); // 3.8 -> 4.0
    }

    const options = {
        chart: {
            type: 'area',
            height: 300,
            animations: { enabled: true, easing: 'linear', speed: 300 },
            toolbar: { show: false },
            zoom: { enabled: false },
            background: 'transparent',
            fontFamily: 'Consolas, monospace'
        },
        series: [{ name: 'Used', data: [] }],
        colors: ['#4dbd74'], // Màu xanh lá đặc trưng cho RAM

        stroke: {
            curve: 'smooth',
            width: 2
        },

        fill: {
            type: 'gradient',
            gradient: {
                shade: 'dark',
                type: 'vertical',
                opacityFrom: 0.6,
                opacityTo: 0.1,
                stops: [0, 100]
            }
        },

        dataLabels: { enabled: false },

        grid: {
            show: true,
            borderColor: '#333',
            strokeDashArray: 3,
            padding: { left: 10, right: 10, top: 10, bottom: 0 } // Sát sàn
        },

        xaxis: {
            type: 'datetime',
            labels: {
                datetimeUTC: false,
                style: { colors: '#aaa', fontSize: '11px' },
                datetimeFormatter: { hour: 'HH:mm:ss', minute: 'HH:mm:ss', second: 'HH:mm:ss' }
            },
            axisBorder: { show: false },
            axisTicks: { color: '#444' },
            tooltip: { enabled: false }
        },

        yaxis: {
            min: 0,
            max: maxRAM,
            forceNiceScale: false, // Tắt auto-rounding để ép chính xác 0
            tickAmount: 4,
            labels: {
                show: true,
                style: {
                    colors: '#4dbd74',
                    fontSize: '11px',
                    fontFamily: 'Consolas, monospace'
                },
                formatter: (v) => `${v.toFixed(1)} GB`,
                offsetX: 0
            },
            axisBorder: { show: false },  // Bỏ vạch border
            axisTicks: { show: false }    // Bỏ vạch ticks, chỉ giữ số
        },

        tooltip: {
            theme: 'dark',
            x: { format: 'HH:mm:ss' },
            y: {
                formatter: (v) => `${v.toFixed(2)} GB` // Tooltip vẫn hiện chi tiết số lẻ
            }
        },
        legend: { show: false }
    };

    if (container.__apexChart) {
        try { container.__apexChart.destroy(); } catch (e) { }
    }

    const chart = new ApexCharts(container, options);
    container.__apexChart = chart;
    chart.render();
    return chart;
}

// --- DATA MANAGER CLASS ---

export class ChartDataManager {
    constructor(maxDataPoints = 3000, sampleThreshold = 2000) {
        this.maxPoints = maxDataPoints; // window size
        this.sampleThreshold = sampleThreshold; // threshold to downsample incoming bulk data
        this.timeData = [];
        this.updateCount = 0;

        // Lightweight FPS + update counter monitor (logs every 5s)
        if (typeof window !== 'undefined' && window.requestAnimationFrame) {
            this.__perf = { frames: 0, last: performance.now(), rafId: null };
            this.__perfRunning = true;
            const loop = () => {
                if (!this.__perfRunning) return;
                this.__perf.frames++;
                this.__perf.rafId = window.requestAnimationFrame(loop);
            };
            this.__perf.rafId = window.requestAnimationFrame(loop);
            this.perfInterval = setInterval(() => {
                const now = performance.now();
                const elapsed = (now - this.__perf.last) / 1000;
                const fps = this.__perf.frames / (elapsed || 1);
                // console.log(`[Charts][Perf] updates=${this.updateCount} fps=${fps.toFixed(1)} points=${this.timeData.length}`);
                this.__perf.frames = 0;
                this.__perf.last = now
                this.updateCount = 0;
            }, 5000);
        }
    }

    setMaxPoints(n) { this.maxPoints = n; }
    setSampleThreshold(n) { this.sampleThreshold = n; }

    toGB(bytes) {
        const v = bytes / (1024 * 1024 * 1024);
        return Number(v.toFixed(2));
    }

    // Uniform downsampling helper (keeps the last point)
    _downsample(array, target) {
        if (!Array.isArray(array)) return array;
        const len = array.length;
        if (len <= target) return array.slice();
        const step = Math.ceil(len / target);
        const sampled = [];
        for (let i = 0; i < len; i += step) sampled.push(array[i]);
        if (sampled[sampled.length - 1] !== array[len - 1]) sampled.push(array[len - 1]);
        return sampled;
    }

    // Bulk load initial history safely with optional downsampling
    // timeLabels: ["2025-01-01T00:00:00Z", ...]
    // dataMap: { 0: [y0,...], 1: [y1,...] }
    bulkLoad(timeLabels, dataMap) {
        if (!Array.isArray(timeLabels) || !dataMap) return { timeData: [], series: {} };
        let t = timeLabels.slice();
        if (t.length > this.sampleThreshold) {
            t = this._downsample(t, this.sampleThreshold);
        }
        // Enforce max window
        if (t.length > this.maxPoints) {
            t = t.slice(t.length - this.maxPoints);
        }
        // Align each series to downsampled + windowed time size
        const aligned = {};
        Object.entries(dataMap).forEach(([idx, arr]) => {
            let seriesArr = arr.slice();
            if (arr.length !== timeLabels.length) {
                // Best-effort: if mismatch, attempt to downsample independently
                if (arr.length > this.sampleThreshold) seriesArr = this._downsample(arr, this.sampleThreshold);
            } else if (arr.length > this.sampleThreshold) {
                seriesArr = this._downsample(arr, this.sampleThreshold);
            }
            // After downsample, enforce same tail length as t
            if (seriesArr.length > t.length) {
                seriesArr = seriesArr.slice(seriesArr.length - t.length);
            } else if (seriesArr.length < t.length) {
                // pad with first value to match length
                const padCount = t.length - seriesArr.length;
                const padVal = seriesArr.length ? seriesArr[0] : 0;
                seriesArr = new Array(padCount).fill(padVal).concat(seriesArr);
            }
            aligned[idx] = seriesArr;
        });

        this.timeData = t;
        return { timeData: this.timeData, series: aligned };
    }

    addDataPoint(timestamp, ramAppUsed, ramBuffers, ramCached, ramFree) {
        // Normalize timestamp to ISO string when possible
        let timeLabel = timestamp;
        try {
            const d = new Date(timestamp);
            timeLabel = isNaN(d.getTime()) ? String(timestamp) : d.toISOString();
        } catch (e) {
            timeLabel = String(timestamp);
        }
        this.timeData.push(timeLabel);
        if (this.timeData.length > this.maxPoints) this.timeData.shift();

        // Strict numeric casting and NaN guards
        const appUsedNum = Number.parseFloat(ramAppUsed);
        const buffersNum = Number.parseFloat(ramBuffers);
        const cachedNum = Number.parseFloat(ramCached);
        const freeNum = Number.parseFloat(ramFree);

        return {
            ramAppUsed: this.toGB(Number.isFinite(appUsedNum) ? appUsedNum : 0),
            ramBuffers: this.toGB(Number.isFinite(buffersNum) ? buffersNum : 0),
            ramCached: this.toGB(Number.isFinite(cachedNum) ? cachedNum : 0),
            ramFree: this.toGB(Number.isFinite(freeNum) ? freeNum : 0)
        };
    }

    // ApexCharts adapter
    updateChart(chart, dataArrays) {
        if (!chart) return;

        // Normalize arrays to current window length
        const len = this.timeData.length;
        let out = Array.isArray(dataArrays?.[0]) ? dataArrays[0].slice() : [];
        if (out.length > len) out = out.slice(out.length - len);
        else if (out.length < len) {
            const padVal = out.length ? out[0] : 0;
            out = new Array(len - out.length).fill(padVal).concat(out);
        }

        const points = this.timeData.map((t, i) => {
            const ts = new Date(t).getTime();
            return { x: Number.isFinite(ts) ? ts : Date.now(), y: out[i] };
        });
        chart.updateSeries([{ name: 'Used', data: points }], true);
        this.updateCount++;
    }

    destroy() {
        // Stop performance monitor timers/raf to avoid leaks and duplicate logs
        if (this.perfInterval) {
            clearInterval(this.perfInterval);
            this.perfInterval = null;
        }
        if (this.__perf && this.__perf.rafId && typeof window !== 'undefined' && window.cancelAnimationFrame) {
            window.cancelAnimationFrame(this.__perf.rafId);
        }
        this.__perfRunning = false;
    }
}

/**
 * Create CPU + Network dual Y-axis chart with stacked areas
 */
export function createCpuNetworkChart(container) {
    if (!container) return null;
    if (typeof ApexCharts === 'undefined') return null;

    const options = {
        chart: {
            type: 'line',
            height: 350,
            stacked: false,  // Disabled - we manually stack network areas
            animations: { enabled: true, easing: 'linear', speed: 1000, dynamicAnimation: { speed: 1000 } },
            toolbar: { show: false },
            zoom: { enabled: false },
            background: 'transparent',
            zoom: { enabled: false },
            background: 'transparent',
            fontFamily: 'Consolas, monospace'
        },
        series: [], // Initialize empty series to prevent updateOptions crash

        // Explicit colors: CPU (Red), Network interfaces (Teal, Blue, Orange, Purple)
        colors: ['#FF4560', '#00E396', '#008FFB', '#FEB019', '#775DD0'],

        stroke: {
            curve: 'smooth',
            width: 2
        },

        fill: {
            type: 'solid',
            // Index 0 (CPU line) = 1.0 solid, others (network areas) = 0.6 semi-transparent
            opacity: [1, 0.6, 0.6, 0.6, 0.6]
        },

        dataLabels: { enabled: false },

        grid: {
            show: true,
            borderColor: '#333',
            strokeDashArray: 3,
            padding: { bottom: 0 }  // Fix floating line at bottom
        },

        xaxis: {
            type: 'datetime',
            labels: {
                datetimeUTC: false,
                style: { colors: '#aaa', fontSize: '11px' },
                datetimeFormatter: { hour: 'HH:mm:ss', minute: 'HH:mm:ss', second: 'HH:mm:ss' }
            },
            axisBorder: { show: false },
            axisTicks: { color: '#444' },
            tooltip: { enabled: false }
        },

        yaxis: [
            {
                // RIGHT Y-axis: CPU (Fixed 0-100%)
                seriesName: 'CPU',
                opposite: true,
                min: 0,
                max: 100,
                labels: {
                    style: { colors: '#FF4560', fontSize: '11px' },
                    formatter: (v) => `${v.toFixed(0)}%`
                },
                title: { text: 'CPU %', style: { color: '#FF4560' } }
            },
            {
                // LEFT Y-axis: Network (Auto-scale)
                seriesName: 'Network',
                min: 0,
                labels: {
                    style: { colors: '#00E396', fontSize: '11px' },
                    formatter: (v) => formatNetworkRate(v)
                },
                title: { text: 'Throughput', style: { color: '#00E396' } }
            }
        ],

        legend: {
            show: true,
            position: 'top',
            horizontalAlign: 'left',
            labels: { colors: '#ccc' }
        },

        tooltip: {
            theme: 'dark',
            shared: true,
            intersect: false,
            x: { format: 'HH:mm:ss' },
            y: {
                formatter: (v, { seriesIndex, w }) => {
                    const seriesName = w.config.series[seriesIndex]?.name || '';
                    if (seriesName === 'CPU') return `${v.toFixed(1)}%`;
                    return formatNetworkRate(v);
                }
            }
        }
    };

    if (container.__apexChart) {
        try { container.__apexChart.destroy(); } catch (e) { }
    }

    const chart = new ApexCharts(container, options);
    container.__apexChart = chart;
    chart.render();
    return chart;
}

/**
 * Determine the best unit for network rate display based on max value
 */
let _networkUnit = 'KB/s';
let _networkDivisor = 1024;

function determineNetworkUnit(maxBytesPerSec) {
    if (!Number.isFinite(maxBytesPerSec) || maxBytesPerSec <= 0) {
        _networkUnit = 'KB/s';
        _networkDivisor = 1024;
    } else if (maxBytesPerSec >= 1024 * 1024 * 1024) {
        _networkUnit = 'GB/s';
        _networkDivisor = 1024 * 1024 * 1024;
    } else if (maxBytesPerSec >= 1024 * 1024) {
        _networkUnit = 'MB/s';
        _networkDivisor = 1024 * 1024;
    } else {
        _networkUnit = 'KB/s';
        _networkDivisor = 1024;
    }
}

/**
 * Format network rate using the determined unit
 */
function formatNetworkRate(bytesPerSec) {
    if (!Number.isFinite(bytesPerSec) || bytesPerSec < 0) return `0 ${_networkUnit}`;
    return `${(bytesPerSec / _networkDivisor).toFixed(1)} ${_networkUnit}`;
}

/**
 * Update CPU + Network chart with new data
 * - CPU is a line overlay (0-100% fixed)
 * - Network interfaces are stacked areas (auto-scale)
 */
export function updateCpuNetworkChart(chart, cpuData, networkData) {
    if (!chart) return;

    const series = [];
    let maxRate = 0;

    // 1. Add CPU Series FIRST (gets color index 0 = Red #FF4560)
    // CPU is completely independent - uses right Y-axis (0-100%)
    const cpuPoints = (cpuData || []).map(d => ({
        x: new Date(d.time).getTime(),
        y: Number(d.percent) || 0
    }));

    series.push({
        name: 'CPU',
        type: 'line',
        data: cpuPoints
        // No group needed - stacked: false at chart level
    });

    // 2. Build Network Interface data and MANUALLY STACK them
    // Since stacked: false at chart level, we calculate cumulative Y values ourselves
    const networkInterfaces = [];

    if (networkData && typeof networkData === 'object') {
        for (const [iface, data] of Object.entries(networkData)) {
            if (!Array.isArray(data)) continue;

            const points = data.map(d => {
                const send = Number(d.send_rate) || 0;
                const recv = Number(d.recv_rate) || 0;
                return {
                    x: new Date(d.time).getTime(),
                    y: send + recv
                };
            });

            networkInterfaces.push({ name: iface, data: points });
        }
    }

    // Stack network interfaces manually: each layer = previous cumulative + current
    // First interface stays as-is, second interface Y = first.Y + second.Y, etc.
    const cumulativeByTime = new Map();  // timestamp -> cumulative total

    for (const iface of networkInterfaces) {
        const stackedPoints = iface.data.map(point => {
            const prev = cumulativeByTime.get(point.x) || 0;
            const newY = prev + point.y;
            cumulativeByTime.set(point.x, newY);
            if (newY > maxRate) maxRate = newY;
            return { x: point.x, y: newY };
        });

        series.push({
            name: iface.name,
            type: 'area',
            data: stackedPoints
        });
    }

    // Determine unit (B/s, KB/s, MB/s)
    determineNetworkUnit(maxRate);

    // 1. Update series data FIRST to ensure chart has correct state
    chart.updateSeries(series, true);

    // 2. Update Y-axes with new unit label
    chart.updateOptions({
        yaxis: [
            {
                // CPU Axis (Right) - Fixed 0-100%
                seriesName: 'CPU',
                opposite: true,
                min: 0,
                max: 100,
                labels: {
                    style: { colors: '#FF4560', fontSize: '11px' },
                    formatter: (v) => `${Math.round(v)}%`
                },
                title: { text: 'CPU %', style: { color: '#FF4560' } }
            },
            {
                // Network Axis (Left) - Auto scale with dynamic unit
                seriesName: 'Network',
                min: 0,
                labels: {
                    style: { colors: '#00E396', fontSize: '11px' },
                    formatter: (v) => formatNetworkRate(v)
                },
                title: { text: `Throughput (${_networkUnit})`, style: { color: '#00E396' } }
            }
        ]
    }, false, false);
}

/**
 * Append single data point to CPU + Network chart (Efficient Real-time Update)
 * Uses chart.appendData() instead of full redraw
 */
export function appendCpuNetworkData(chart, cpuPoint, networkSnapshot) {
    if (!chart) return;

    const timestamp = new Date().getTime();
    const newPoints = [];

    // 1. CPU Point
    const cpuVal = Number(cpuPoint?.percent || 0);
    newPoints.push({
        name: 'CPU',
        data: [{ x: timestamp, y: cpuVal }]
    });

    // 2. Network Points (Stacked)
    // We must manually stack them just like in updateCpuNetworkChart
    // because logical stacking is disabled in config.
    let cumulativeY = 0;
    let maxRate = 0;

    // We must iterate through EXISTING series in the chart to ensure order match
    // or use 'name' to target. appendData takes array of objects { name: '...', data: [...] }

    // Convert snapshot list to map for easy lookup
    const netMap = {};
    if (Array.isArray(networkSnapshot)) {
        networkSnapshot.forEach(n => {
            if (n.interface) {
                netMap[n.interface] = (Number(n.send_bytes_s) || 0) + (Number(n.recv_bytes_s) || 0);
            }
        });
    }

    // Get current series names from chart context to ensure we provide data for all known interfaces
    // Note: If a new interface appears, appendData might not handle adding a NEW series dynamically well without full update.
    // So we only append to existing series.
    const currentSeries = chart.w.config.series;

    currentSeries.forEach(s => {
        if (s.name === 'CPU') return; // Handled above

        const val = netMap[s.name] || 0;
        cumulativeY += val;

        newPoints.push({
            name: s.name,
            data: [{ x: timestamp, y: cumulativeY }]
        });

        if (cumulativeY > maxRate) maxRate = cumulativeY;
    });

    // Dynamic Unit Scaling Check
    // If unit changes (KB->MB), we technically need to update Y-axis labels.
    const oldUnit = _networkUnit;
    determineNetworkUnit(maxRate);
    if (_networkUnit !== oldUnit) {
        // If unit changed, full redraw is safer/required to update axis labels
        // But for optimization, we might skip this often or force updateOptions
        // updatesOptions + appendData might be heavy. 
        // Let's just update axis if needed.
        chart.updateOptions({
            yaxis: [
                { seriesName: 'CPU', opposite: true, min: 0, max: 100, labels: { formatter: (v) => `${Math.round(v)}%` } },
                { seriesName: 'Network', labels: { formatter: (v) => formatNetworkRate(v) }, title: { text: `Throughput (${_networkUnit})` } }
            ]
        }, false, false);
    }

    chart.appendData(newPoints);
}

export function initializeSystemCharts(totalRAMBytes) {
    const ramUsageChart = createRAMUsageChart(document.getElementById('memory-usage-chart'), totalRAMBytes);

    window.addEventListener('resize', () => {
        if (ramUsageChart && typeof ramUsageChart.resize === 'function') {
            try { ramUsageChart.resize(); } catch (e) { /* ignore */ }
        }
    }, { passive: true });

    return {
        ramUsageChart,
        dataManager: new ChartDataManager(3000, 2000)
    };
}
