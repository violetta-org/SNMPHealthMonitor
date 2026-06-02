/**
 * Memory Percent Chart Module
 * Line Chart using ApexCharts to display Memory Usage Percentage over time
 */

export class MemoryPercentChart {
    constructor() {
        this.chart = null;
        this.color = '#008FFB'; // Màu xanh dương đậm
        this.initialized = false;
        this.lastTimestamp = null; // Track last appended timestamp to avoid duplicates
    }

    /**
     * Initialize the memory percent chart
     */
    init() {
        if (this.initialized) {
            console.warn('[MemoryPercentChart] Chart already initialized');
            return;
        }

        const chartElement = document.getElementById('memory-percent-chart');
        if (!chartElement) {
            console.error('[MemoryPercentChart] Chart container not found');
            return;
        }

        const options = {
            series: [{
                name: "Memory Usage",
                data: [] // Dữ liệu sẽ được append vào đây
            }],
            chart: {
                id: 'memory-percent-chart',
                type: 'line', // Biểu đồ đường
                height: 350,
                animations: {
                    enabled: true,
                    easing: 'linear',
                    dynamicAnimation: { speed: 1000 }
                },
                toolbar: { show: false },
                zoom: { enabled: false },
                background: 'transparent',
                foreColor: '#e0e0e0',
                fontFamily: 'Inter, sans-serif'
            },
            colors: [this.color], // Màu xanh dương đậm
            dataLabels: { enabled: false },
            stroke: {
                curve: 'smooth', // Đường cong mượt mà
                width: 2
            },
            // Cấu hình Markers (Các chấm tròn trên đường)
            markers: {
                size: 4, // Kích thước chấm
                colors: [this.color],
                strokeColors: '#fff',
                strokeWidth: 2,
                hover: { size: 7 }
            },
            grid: {
                show: true,
                borderColor: '#3a4d5f',
                strokeDashArray: 4,
                xaxis: {
                    lines: { show: true }
                },
                yaxis: {
                    lines: { show: true }
                },
                padding: {
                    top: 10,
                    right: 10,
                    bottom: 10,
                    left: 10
                }
            },
            xaxis: {
                type: 'datetime',
                range: 200000, // Cửa sổ 100 giây
                labels: {
                    style: {
                        colors: '#a0aec0',
                        fontSize: '11px'
                    },
                    datetimeFormatter: {
                        hour: 'HH:mm',
                        minute: 'HH:mm:ss',
                        second: 'HH:mm:ss'
                    },
                    rotate: -45,
                    rotateAlways: false
                },
                axisBorder: {
                    color: '#3a4d5f'
                },
                axisTicks: {
                    color: '#3a4d5f'
                }
            },
            yaxis: {
                min: 0,
                max: 100, // Cố định thang đo từ 0-100%
                forceNiceScale: true,
                labels: {
                    style: {
                        colors: '#a0aec0',
                        fontSize: '11px'
                    },
                    formatter: (value) => {
                        return value.toFixed(1) + "%";
                    }
                },
                axisBorder: {
                    color: '#3a4d5f'
                },
                axisTicks: {
                    color: '#3a4d5f'
                },
                title: {
                    text: 'Phần trăm (%)',
                    style: {
                        color: '#a0aec0',
                        fontSize: '12px',
                        fontWeight: 600
                    }
                }
            },
            tooltip: {
                theme: 'dark',
                x: { format: 'HH:mm:ss' },
                y: {
                    formatter: (value) => {
                        return value.toFixed(2) + " %";
                    }
                },
                style: {
                    fontSize: '12px',
                    fontFamily: 'Inter, sans-serif'
                }
            },
            legend: {
                show: false // Không hiển thị legend cho single series
            },
            theme: {
                mode: 'dark',
                palette: 'palette1'
            }
        };

        this.chart = new ApexCharts(chartElement, options);
        this.chart.render();
        this.initialized = true;
        console.log('[MemoryPercentChart] Chart initialized');
    }

    /**
     * Update chart with initial history data (60 points)
     * @param {Array} historyData - Array of {time, percent}
     */
    updateHistory(historyData) {
        if (!this.initialized) {
            this.init();
        }

        if (!historyData || historyData.length === 0) {
            console.warn('[MemoryPercentChart] No history data provided');
            return;
        }

        console.log(`[MemoryPercentChart] Updating with ${historyData.length} history points`);

        // Prepare data array
        const data = [];
        historyData.forEach(point => {
            const timestamp = new Date(point.time).getTime();
            const percent = point.percent || 0;
            data.push([timestamp, percent]);
        });

        // Update chart series
        this.chart.updateSeries([{
            name: "Memory Usage",
            data: data
        }]);

        // Update last timestamp from history data
        if (data.length > 0) {
            this.lastTimestamp = data[data.length - 1][0]; // Last data point's timestamp
        }
    }

    /**
     * Append new data point (real-time update)
     * @param {Object} memoryData - {time, percent}
     */
    appendData(memoryData) {
        if (!this.initialized) {
            console.warn('[MemoryPercentChart] Chart not initialized, cannot append data');
            return;
        }

        if (!memoryData || !memoryData.time || memoryData.percent === undefined) {
            console.warn('[MemoryPercentChart] Invalid memory data provided');
            return;
        }

        const timestamp = new Date(memoryData.time).getTime();
        const percent = memoryData.percent || 0;

        // Filter duplicate: chỉ append nếu timestamp mới hơn timestamp cuối cùng
        if (this.lastTimestamp !== null && timestamp <= this.lastTimestamp) {
            console.log(`[MemoryPercentChart] Skipping duplicate data point: time=${memoryData.time} (last=${this.lastTimestamp})`);
            return;
        }

        console.log(`[MemoryPercentChart] Appending data point: time=${memoryData.time}, percent=${percent}%`);

        // Append new data point
        this.chart.appendData([{
            seriesIndex: 0,
            data: [[timestamp, percent]]
        }]);

        // Update last timestamp
        this.lastTimestamp = timestamp;
    }

    /**
     * Destroy chart instance
     */
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
            this.initialized = false;
            console.log('[MemoryPercentChart] Chart destroyed');
        }
    }
}

