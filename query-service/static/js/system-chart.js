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
    axisLabel: { color: '#aaa', fontSize: 11, formatter: `{value} ${unit}` },
    axisLine: { show: false }
});

// --- CHART CREATION ---

export function createRAMUsageChart(container) {
    const chart = echarts.init(container);
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
        toolbox: getCommonToolbox(),
        xAxis: getTimeAxisConfig(),
        yAxis: {
            ...getValueAxisConfig(true, '', 'GB'),
            min: (value) => Math.max(0, value.min - 0.5) 
        },
        series: [
            // Series 0: Used
            {
                name: 'Used', type: 'line', smooth: true, showSymbol: false,
                itemStyle: { color: '#00f2ff' },
                areaStyle: {
                    color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                        { offset: 0, color: 'rgba(0, 242, 255, 0.5)' },
                        { offset: 1, color: 'rgba(0, 242, 255, 0.0)' }
                    ])
                },
                data: []
            },
            // Series 1: Cached
            {
                name: 'Cached', type: 'line', smooth: true, showSymbol: false,
                itemStyle: { color: '#00ff9d' },
                data: []
            },
            // Series 2: MarkLine Total
            {
                name: 'Total Limit', type: 'line',
                markLine: {
                    symbol: 'none',
                    label: { show: true, position: 'insideEndTop', formatter: 'Total: {c}GB' },
                    lineStyle: { color: '#ff2a6d', type: 'dashed', opacity: 0.6 },
                    data: [] 
                },
                data: [] 
            }
        ]
    };
    chart.setOption(option);
    return chart;
}

export function createRAMPercentChart(container) {
    const chart = echarts.init(container);
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(22, 33, 62, 0.9)',
            borderColor: '#ff2a6d',
            textStyle: { color: '#fff' },
            formatter: '{b}<br/>{a}: {c}%'
        },
        grid: getCommonGrid(),
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
    const chart = echarts.init(container);
    const option = {
        backgroundColor: 'transparent',
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(22, 33, 62, 0.9)',
            borderColor: '#bd00ff',
            textStyle: { color: '#fff' }
        },
        grid: getCommonGrid(),
        xAxis: getTimeAxisConfig(),
        yAxis: getValueAxisConfig(true, '', 'GB'),
        series: [{
            name: 'Swap Used', type: 'line', step: 'start', showSymbol: false,
            itemStyle: { color: '#bd00ff' },
            areaStyle: { opacity: 0.2 },
            data: []
        }]
    };
    chart.setOption(option);
    return chart;
}

// --- DATA MANAGER CLASS ---

export class ChartDataManager {
    constructor(maxDataPoints = 60) {
        this.maxPoints = maxDataPoints;
        this.timeData = [];
    }

    toGB(bytes) {
        return (bytes / (1024 * 1024 * 1024)).toFixed(2);
    }

    addDataPoint(timestamp, ramUsed, ramCached, ramPercent, swapUsed) {
        this.timeData.push(timestamp);
        if (this.timeData.length > this.maxPoints) this.timeData.shift();

        return {
            ramUsed: this.toGB(ramUsed),
            ramCached: this.toGB(ramCached),
            ramPercent: ramPercent.toFixed(1),
            swapUsed: this.toGB(swapUsed)
        };
    }

    // Explicitly update series by Index using strict mapping
    updateChart(chart, dataArrays) {
        if (!chart) return;

        const updateOption = {
            xAxis: { data: this.timeData }
        };

        // dataArrays format: { 0: [data...], 1: [data...] }
        Object.entries(dataArrays).forEach(([index, data]) => {
            updateOption[`series[${index}]`] = { 
                data: data.slice(-this.maxPoints) 
            };
        });

        chart.setOption(updateOption);
    }
}

export function initializeSystemCharts(totalRAMBytes) {
    const totalRAMGB = (totalRAMBytes / (1024 * 1024 * 1024)).toFixed(2);

    const ramUsageChart = createRAMUsageChart(document.getElementById('memory-usage-chart'));
    
    // Set MarkLine Total for RAM Chart (Series index 2)
    ramUsageChart.setOption({
        series: [{}, {}, { markLine: { data: [{ yAxis: totalRAMGB }] } }] 
    });

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
    });

    return {
        ramUsageChart,
        ramPercentChart,
        swapChart,
        dataManager: new ChartDataManager(60)
    };
}
