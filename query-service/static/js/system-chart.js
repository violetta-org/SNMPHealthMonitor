/**
 * SYSTEM MONITOR CHARTS - FINAL STABLE VERSION
 */

// --- CONFIGURATION ---

const getCommonGrid = () => ({
    left: '50px',
    right: '20px',
    top: '40px',
    bottom: '30px',
    containLabel: true
});

const getCommonLegend = () => ({
    top: 5,
    right: 50,
    textStyle: { color: '#ccc', fontSize: 11 },
    icon: 'roundRect'
});

const getCommonToolbox = () => ({
    feature: {
        dataZoom: { yAxisIndex: 'none' },
        restore: {},
        saveAsImage: { title: 'Save', pixelRatio: 2 }
    },
    iconStyle: { borderColor: '#aaa' },
    right: 10,
    top: 5
});

// X-Axis Config: Uses Category + hideOverlap for stability
const getTimeAxisConfig = () => ({
    type: 'category', 
    boundaryGap: false,
    axisLabel: {
        color: '#aaa',
        fontSize: 10,
        fontFamily: 'Consolas, monospace',
        formatter: (value) => {
            if (!value) return '';
            try {
                const date = new Date(value);
                return `${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}:${date.getSeconds().toString().padStart(2,'0')}`;
            } catch (e) { return value; }
        },
        hideOverlap: true, // Critical fix for label overlap
        interval: 'auto'
    },
    axisLine: { lineStyle: { color: '#444' } },
    splitLine: { 
        show: true, 
        lineStyle: { color: 'rgba(255, 255, 255, 0.05)', type: 'dashed' } 
    }
});

const getValueAxisConfig = (scale = true, name = '', unit = '') => ({
    type: 'value',
    name: name,
    nameTextStyle: { color: '#888', padding: [0, 0, 0, -20] },
    scale: scale,
    splitLine: { show: true, lineStyle: { color: 'rgba(255, 255, 255, 0.08)' } },
    axisLabel: { color: '#aaa', fontSize: 11, fontFamily: 'Consolas, monospace', formatter: `{value} ${unit}` },
    axisLine: { show: false }
});

// --- CHART CREATION ---

export function createRAMUsageChart(container) {
    const existing = echarts.getInstanceByDom(container);
    const chart = existing || echarts.init(container);
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(22, 33, 62, 0.95)',
            borderColor: '#00f2ff',
            textStyle: { color: '#fff', fontFamily: 'Consolas' },
            axisPointer: { type: 'cross', label: { backgroundColor: '#283b56' } }
        },
        grid: getCommonGrid(),
        legend: getCommonLegend(),
        // Minimalist: remove toolbox buttons
        dataZoom: [
            { type: 'slider', xAxisIndex: 0, bottom: 0, height: 18 },
            { type: 'inside', xAxisIndex: 0 }
        ],
        xAxis: getTimeAxisConfig(),
        yAxis: { 
            ...getValueAxisConfig(true, '', 'GB'),
            min: 0,
            splitLine: { show: true, lineStyle: { opacity: 0.1 } }
        },
        series: [
            {
                name: 'App Used', type: 'line', smooth: true,
                showSymbol: false,
                lineStyle: { color: '#26a69a', width: 2 },
                itemStyle: { color: '#26a69a' },
                areaStyle: { opacity: 0.2, color: 'rgba(38,166,154,0.2)' },
                data: []
            }
        ]
    };
    chart.setOption(option);
    return chart;
}

export function createRAMPercentChart(container) {
    const existing = echarts.getInstanceByDom(container);
    const chart = existing || echarts.init(container);
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(22, 33, 62, 0.9)',
            borderColor: '#ff2a6d',
            textStyle: { color: '#fff', fontFamily: 'Consolas, monospace' },
            formatter: '{b}<br/>{a}: {c}%'
        },
        grid: getCommonGrid(),
        dataZoom: [
            { type: 'slider', xAxisIndex: 0, bottom: 0, height: 18 },
            { type: 'inside', xAxisIndex: 0 }
        ],
        xAxis: getTimeAxisConfig(),
        yAxis: { ...getValueAxisConfig(false, '', '%'), max: 100 },
        series: [{
            name: 'RAM %', type: 'line', smooth: true, showSymbol: false,
            itemStyle: { color: '#ff2a6d' },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(255, 42, 109, 0.5)' },
                    { offset: 1, color: 'rgba(255, 42, 109, 0.0)' }
                ])
            },
            data: []
        }]
    };
    chart.setOption(option);
    return chart;
}

export function createSwapChart(container) {
    const existing = echarts.getInstanceByDom(container);
    const chart = existing || echarts.init(container);
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(22, 33, 62, 0.9)',
            borderColor: '#bd00ff',
            textStyle: { color: '#fff', fontFamily: 'Consolas, monospace' }
        },
        grid: getCommonGrid(),
        dataZoom: [
            { type: 'slider', xAxisIndex: 0, bottom: 0, height: 18 },
            { type: 'inside', xAxisIndex: 0 }
        ],
        xAxis: getTimeAxisConfig(),
        yAxis: getValueAxisConfig(true, '', 'GB'),
        series: [{
            name: 'Swap Used', type: 'bar',
            itemStyle: { color: '#bd00ff' },
            barWidth: '60%',
            data: []
        }]
    };
    chart.setOption(option);
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

    addDataPoint(timestamp, ramUsed, ramCached, ramPercent, swapUsed) {
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
        const usedNum = Number.parseFloat(ramUsed);
        const cachedNum = Number.parseFloat(ramCached);
        const percentNum = Number.parseFloat(ramPercent);
        const swapNum = Number.parseFloat(swapUsed);

        return {
            ramUsed: this.toGB(Number.isFinite(usedNum) ? usedNum : 0),
            ramCached: this.toGB(Number.isFinite(cachedNum) ? cachedNum : 0),
            ramPercent: Number.isFinite(percentNum) ? Number(percentNum.toFixed(1)) : 0,
            swapUsed: this.toGB(Number.isFinite(swapNum) ? swapNum : 0)
        };
    }

    // Explicit mapping by chart DOM id to avoid dynamic keys
    updateChart(chart, dataArrays) {
        if (!chart) return;
        const chartId = chart.getDom().id;

        // Normalize arrays to current window length
        const len = this.timeData.length;
        const norm = (arr) => {
            let out = Array.isArray(arr) ? arr.slice() : [];
            if (out.length > len) out = out.slice(out.length - len);
            else if (out.length < len) {
                const padVal = out.length ? out[0] : 0;
                out = new Array(len - out.length).fill(padVal).concat(out);
            }
            return out;
        };

        // Base option with timeline
        const option = {
            xAxis: { data: this.timeData },
            series: []
        };

        // Explicit per-chart mapping
        if (chartId === 'memory-usage-chart') {
            option.series = [ { data: norm(dataArrays[0]) } ];
        } else if (chartId === 'memory-percent-chart') {
            option.series = [ { data: norm(dataArrays[0]) } ];
        } else if (chartId === 'swap-usage-chart') {
            option.series = [ { data: norm(dataArrays[0]) } ];
        }

        chart.setOption(option);
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

export function initializeSystemCharts(totalRAMBytes) {
    const ramUsageChart = createRAMUsageChart(document.getElementById('memory-usage-chart'));
    // Set MarkLine Total only when a valid positive total is provided
    if (Number.isFinite(totalRAMBytes) && totalRAMBytes > 0) {
        const totalRAMGB = (totalRAMBytes / (1024 * 1024 * 1024)).toFixed(2);
        ramUsageChart.setOption({ yAxis: { min: 0, max: Number(totalRAMGB) } });
    }

    const ramPercentChart = createRAMPercentChart(document.getElementById('memory-percent-chart'));
    const swapChart = createSwapChart(document.getElementById('swap-usage-chart'));

    // Sync Crosshairs
    ramUsageChart.group = 'sys_monitor';
    ramPercentChart.group = 'sys_monitor';
    swapChart.group = 'sys_monitor';
    echarts.connect('sys_monitor');

    window.addEventListener('resize', () => {
        ramUsageChart.resize();
        ramPercentChart.resize();
        swapChart.resize();
    }, { passive: true });

    return {
        ramUsageChart,
        ramPercentChart,
        swapChart,
        dataManager: new ChartDataManager(3000, 2000)
    };
}
