/**
 * Memory Chart Module
 * Stacked Area Chart using ApexCharts to display Used, Cached, and Free memory
 */

export class MemoryChart {
    constructor() {
        this.chart = null;
        this.colors = ['#008FFB', '#00E396', '#FEB019']; // Used (Blue), Cached (Green), Free (Orange)
        this.initialized = false;
    }

    /**
     * Initialize the memory chart
     */
    init() {
        if (this.initialized) {
            console.warn('[MemoryChart] Chart already initialized');
            return;
        }

        const chartElement = document.getElementById('memory-chart');
        if (!chartElement) {
            console.error('[MemoryChart] Chart container not found');
            return;
        }

        const options = {
            series: [
                { name: 'Used', data: [] },   // Index 0: Dưới cùng
                { name: 'Cached', data: [] }, // Index 1: Ở giữa
                { name: 'Free', data: [] }    // Index 2: Trên cùng
            ],
            chart: {
                id: 'memory-chart',
                type: 'area',
                height: 400,
                stacked: true, // QUAN TRỌNG: Kích hoạt chế độ xếp chồng
                animations: {
                    enabled: true,
                    easing: 'linear',
                    dynamicAnimation: { speed: 1000 } // Hiệu ứng trượt mượt mà
                },
                toolbar: { show: false },
                zoom: { enabled: false },
                background: 'transparent',
                foreColor: '#e0e0e0',
                fontFamily: 'Inter, sans-serif'
            },
            colors: this.colors,
            dataLabels: { enabled: false },
            stroke: { 
                curve: 'smooth', 
                width: 2,
                colors: this.colors
            },
            fill: {
                type: 'gradient',
                gradient: { 
                    opacityFrom: 0.7, 
                    opacityTo: 0.2,
                    shadeIntensity: 0.5
                }
            },
            grid: {
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
                range: 60000, // Cửa sổ hiển thị 60 giây
                labels: { 
                    style: {
                        colors: '#a0aec0',
                        fontSize: '11px'
                    },
                    datetimeFormatter: { 
                        hour: 'HH:mm', 
                        minute: 'HH:mm:ss', 
                        second: 'HH:mm:ss' // Hiển thị đầy đủ giờ:phút:giây thay vì chỉ giây
                    },
                    rotate: -45, // Xoay labels để dễ đọc hơn
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
                min: 0, // Bắt đầu từ 0
                forceNiceScale: true, // Tự động chia tỉ lệ đẹp
                labels: {
                    style: {
                        colors: '#a0aec0',
                        fontSize: '11px'
                    },
                    formatter: (value) => {
                        // Hàm đổi Bytes sang GB
                        const gb = value / (1024 * 1024 * 1024);
                        // Hiển thị 1 chữ số thập phân nếu cần, không hiển thị .0
                        if (gb % 1 === 0) {
                            return gb.toFixed(0) + " GB";
                        } else {
                            return gb.toFixed(1) + " GB";
                        }
                    }
                },
                axisBorder: {
                    color: '#3a4d5f'
                },
                axisTicks: {
                    color: '#3a4d5f'
                },
                title: {
                    text: 'Dung lượng',
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
                        return (value / (1024 * 1024 * 1024)).toFixed(2) + " GB";
                    }
                },
                style: {
                    fontSize: '12px',
                    fontFamily: 'Inter, sans-serif'
                }
            },
            legend: { 
                position: 'top', 
                horizontalAlign: 'right',
                fontSize: '12px',
                fontFamily: 'Inter, sans-serif',
                labels: {
                    colors: '#e0e0e0'
                },
                markers: {
                    width: 12,
                    height: 12,
                    radius: 6
                }
            },
            theme: {
                mode: 'dark',
                palette: 'palette1'
            }
        };

        this.chart = new ApexCharts(chartElement, options);
        this.chart.render();
        this.initialized = true;
        console.log('[MemoryChart] Chart initialized');
    }

    /**
     * Update chart with initial history data (60 points)
     * @param {Array} historyData - Array of {time, used, cached, free, total}
     */
    updateHistory(historyData) {
        if (!this.initialized) {
            this.init();
        }

        if (!historyData || historyData.length === 0) {
            console.warn('[MemoryChart] No history data provided');
            return;
        }

        console.log(`[MemoryChart] Updating with ${historyData.length} history points`);

        // Prepare data arrays
        const usedData = [];
        const cachedData = [];
        const freeData = [];

        historyData.forEach(point => {
            const timestamp = new Date(point.time).getTime();
            usedData.push([timestamp, point.used || 0]);
            cachedData.push([timestamp, point.cached || 0]);
            freeData.push([timestamp, point.free || 0]);
        });

        // Update chart series
        this.chart.updateSeries([
            { name: 'Used', data: usedData },
            { name: 'Cached', data: cachedData },
            { name: 'Free', data: freeData }
        ]);
    }

    /**
     * Append new data point (real-time update)
     * @param {Object} memoryData - {time, used, cached, free, total}
     */
    appendData(memoryData) {
        if (!this.initialized) {
            console.warn('[MemoryChart] Chart not initialized, cannot append data');
            return;
        }

        if (!memoryData || !memoryData.time) {
            console.warn('[MemoryChart] Invalid memory data provided');
            return;
        }

        const timestamp = new Date(memoryData.time).getTime();
        const used = memoryData.used || 0;
        const cached = memoryData.cached || 0;
        const free = memoryData.free || 0;

        console.log(`[MemoryChart] Appending data point: time=${memoryData.time}, used=${used}, cached=${cached}, free=${free}`);

        // Append new data point to each series
        this.chart.appendData([{
            seriesIndex: 0, // Used
            data: [[timestamp, used]]
        }, {
            seriesIndex: 1, // Cached
            data: [[timestamp, cached]]
        }, {
            seriesIndex: 2, // Free
            data: [[timestamp, free]]
        }]);
    }

    /**
     * Destroy chart instance
     */
    destroy() {
        if (this.chart) {
            this.chart.destroy();
            this.chart = null;
            this.initialized = false;
            console.log('[MemoryChart] Chart destroyed');
        }
    }
}

