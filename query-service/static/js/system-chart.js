/**
 * SYSTEM MONITOR CHARTS
 */

export function createRAMUsageChart(container, totalRAMBytes) {
    if (!container) return null;
    if (typeof ApexCharts === 'undefined') {
        console.error('[SystemCharts] ApexCharts is not loaded. Make sure the CDN script is included.');
        return null;
    }
    //[X]
    const totalRAMGB = Number.isFinite(totalRAMBytes) && totalRAMBytes > 0
        ? totalRAMBytes / (1024 * 1024 * 1024)
        : undefined;

    const options = {
        chart: {
            type: 'area',
            height: 300,
            animations: {
                enabled: true,
                easing: 'easeinout',
                speed: 350
            },
            toolbar: { show: false },
            zoom: { enabled: false },
            background: 'transparent',
            fontFamily: 'Consolas, monospace'
        },
        series: [
            {
                name: 'Used',
                data: []
            }
        ],
        colors: ['#4dbd74'],
        stroke: {
            curve: 'smooth',
            width: 2
        },
        fill: {
            type: 'gradient',
            gradient: {
                shade: 'dark',
                type: 'vertical',
                opacityFrom: 0.7,
                opacityTo: 0.15,
                stops: [0, 80, 100]
            }
        },
        dataLabels: { enabled: false },
        grid: {
            show: true,
            borderColor: '#333',
            strokeDashArray: 3,
            padding: { left: 70, right: 20, top: 10, bottom: 0 }
        },
        xaxis: {
            type: 'datetime',
            labels: {
                datetimeUTC: false,
                style: { colors: '#aaa', fontSize: '11px' },
                datetimeFormatter: {
                    hour: 'HH:mm:ss',
                    minute: 'HH:mm:ss',
                    second: 'HH:mm:ss'
                }
            },
            axisBorder: { color: '#444' },
            axisTicks: { color: '#444' },
            tooltip: { enabled: false }
        },
        yaxis: {
            min: 0,
            max: Number.isFinite(totalRAMGB) ? totalRAMGB : undefined,
            labels: {
                show: true,
                style: { colors: '#aaa', fontSize: '12px' },
                formatter: (v) => Number.isFinite(v) ? `${v.toFixed(1)} GB` : '',
                minWidth: 60,
                offsetX: 0
            },
            forceNiceScale: true,
            tickAmount: 5,
            axisBorder: { show: true, color: '#444' },
            axisTicks: { show: true, color: '#444' }
        },
        tooltip: {
            theme: 'dark',
            x: { format: 'HH:mm:ss' },
            y: {
                formatter: (v) => `${v.toFixed(2)} GB`
            }
        },
        legend: { show: false }
    };

    // Clean any previous instance attached to this container
    if (container.__apexChart && typeof container.__apexChart.destroy === 'function') {
        try { container.__apexChart.destroy(); } catch (e) { /* ignore */ }
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
                console.log(`[Charts][Perf] updates=${this.updateCount} fps=${fps.toFixed(1)} points=${this.timeData.length}`);
                this.__perf.frames = 0;
                this.__perf.last = now;
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
 * Create CPU + Network dual Y-axis chart
 */
export function createCpuNetworkChart(container) {
    if (!container) return null;
    if (typeof ApexCharts === 'undefined') {
        return null;
    }

    const options = {
        chart: {
            type: 'line', // Quan trọng: Toàn bộ biểu đồ là dạng đường kẻ
            height: 350,
            animations: { enabled: true, easing: 'linear', speed: 300 },
            toolbar: { show: false },
            zoom: { enabled: false },
            background: 'transparent',
            fontFamily: 'Consolas, monospace'
        },
        series: [
            // SỬA Ở ĐÂY: Đổi type từ 'area' thành 'line'
            { name: 'CPU %', type: 'line', data: [] }, 
            { name: 'Throughput', type: 'line', data: [] }
        ],
        colors: ['#FF0000', '#29b6f6'], // Đỏ tươi và Xanh dương
        
        stroke: {
            curve: 'smooth',
            width: [3, 2], // CPU dày 3px cho rõ, Network 2px
        },
        
        // SỬA Ở ĐÂY: Loại bỏ hoàn toàn opacity, để Solid 100%
        fill: {
            type: 'solid',
            opacity: 1 
        },

        dataLabels: { enabled: false },
        grid: {
            show: true,
            borderColor: '#333',
            strokeDashArray: 3,
        },
        xaxis: {
            type: 'datetime',
            labels: {
                style: { colors: '#aaa', fontSize: '11px' },
                datetimeFormatter: { hour: 'HH:mm:ss', minute: 'HH:mm:ss', second: 'HH:mm:ss' }
            },
            axisBorder: { show: false },
            axisTicks: { color: '#444' },
            tooltip: { enabled: false }
        },
        yaxis: [
            {
                seriesName: 'CPU %',
                min: 0,
                max: 100, // LƯU Ý: Nếu muốn đường đỏ "nhảy múa" mạnh như đường xanh, hãy xóa dòng này đi!
                labels: {
                    style: { colors: '#FF0000', fontSize: '11px' },
                    formatter: (v) => `${v.toFixed(0)}%`
                },
                title: { text: 'CPU %', style: { color: '#FF0000' } }
            },
            {
                seriesName: 'Throughput',
                opposite: true,
                min: 0, // Để tự động max, giúp đường xanh dao động rõ
                labels: {
                    style: { colors: '#29b6f6', fontSize: '11px' },
                    formatter: (v) => formatNetworkRate(v)
                },
                title: { text: 'Throughput', style: { color: '#29b6f6' } }
            }
        ],
        tooltip: {
            theme: 'dark',
            shared: true,
            x: { format: 'HH:mm:ss' },
            y: {
                formatter: (v, { seriesIndex }) => {
                    if (seriesIndex === 0) return `${v.toFixed(1)}%`;
                    return formatNetworkRate(v);
                }
            }
        },
        legend: {
            show: true,
            position: 'top',
            labels: { colors: '#ccc' }
        }
    };

    if (container.__apexChart) {
        try { container.__apexChart.destroy(); } catch (e) {}
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
 * - Network is shown as a single Throughput line (send + recv)
 * - Optional autoZoomCpu toggles dynamic CPU Y-axis range
 */
export function updateCpuNetworkChart(chart, cpuData, networkData, autoZoomCpu = false) {
    if (!chart) return;

    // CPU points (0-100%)
    const cpuPoints = (cpuData || []).map(d => ({
        x: new Date(d.time).getTime(),
        y: Number(d.percent) || 0
    }));

    // Throughput = send_rate + recv_rate
    let maxRate = 0;
    const throughputPoints = (networkData || []).map(d => {
        const send = Number(d.send_rate) || 0;
        const recv = Number(d.recv_rate) || 0;
        const total = send + recv;
        if (total > maxRate) maxRate = total;
        return {
            x: new Date(d.time).getTime(),
            y: total
        };
    });
    determineNetworkUnit(maxRate);

    // CPU Y-axis range: default 0-100, optionally auto-zoom
    let cpuMin = 0;
    let cpuMax = 100;
    if (autoZoomCpu && cpuPoints.length > 0) {
        const values = cpuPoints.map(p => p.y);
        let localMin = Math.min(...values);
        let localMax = Math.max(...values);

        if (localMin === localMax) {
            const pad = Math.max(5, localMax * 0.2);
            localMin = Math.max(0, localMin - pad);
            localMax = Math.min(100, localMax + pad);
        } else {
            const span = localMax - localMin;
            const pad = Math.max(5, span * 0.2);
            localMin = Math.max(0, localMin - pad);
            localMax = Math.min(100, localMax + pad);
        }

        cpuMin = localMin;
        cpuMax = localMax;
    }

    const currentYaxes = chart.w.config.yaxis || [];

    // Update Y-axes: CPU % and Throughput (with unit)
    chart.updateOptions({
        yaxis: [
            {
                ...(currentYaxes[0] || {}),
                min: cpuMin,
                max: cpuMax
            },
            {
                ...(currentYaxes[1] || {}),
                title: {
                    text: `Throughput (${_networkUnit})`,
                    style: { color: '#29b6f6', fontSize: '12px' }
                }
            }
        ]
    }, false, false);

    chart.updateSeries([
        { name: 'CPU %', data: cpuPoints },
        { name: 'Throughput', data: throughputPoints }
    ], true);
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
