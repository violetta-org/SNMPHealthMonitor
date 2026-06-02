/**
 * ═══════════════════════════════════════════════════════════════════════════
 * Predictive AIOps — Dashboard Prediction Widget
 * ═══════════════════════════════════════════════════════════════════════════
 *
 * Fetches ML predictions from /api/ml/predict/{sysname} and renders:
 * - Prediction cards with status badges
 * - Mini ApexCharts with forecast dashed lines + historical trendlines
 * - Overall health banner
 * - Toggle switch to enable/disable prediction mode
 */

(function () {
    'use strict';

    const ML_API_URL = '/api/ml/predict';

    // ── State ───────────────────────────────────────────────────────────
    let predictionEnabled = false;
    let predictionData = null;
    let miniCharts = {};

    // ── Icons for each metric ───────────────────────────────────────────
    const METRIC_ICONS = {
        disk: '💿',
        memory: '🧠',
        cpu: '🔥',
        temperature: '🌡️',
    };

    const METRIC_UNITS = {
        disk: '%',
        memory: '%',
        cpu: '%',
        temperature: '°C',
    };

    // ── Get sysname from page ───────────────────────────────────────────
    function getSysname() {
        const body = document.body;
        if (body.dataset.sysname) return body.dataset.sysname;
        const match = window.location.pathname.match(/\/dashboard\/([^/]+)/);
        if (match) return match[1];
        return null;
    }

    // ── Create prediction panel DOM ─────────────────────────────────────
    function createPredictionPanel() {
        // Only show on dashboard pages
        const sysname = getSysname();
        if (!sysname) return;

        // Find the dashboard grid to insert after it
        const dashGrid = document.querySelector('.dashboard-grid');
        if (!dashGrid) return;

        const panel = document.createElement('div');
        panel.className = 'prediction-panel';
        panel.id = 'prediction-panel';
        panel.innerHTML = `
            <!-- Header with Toggle -->
            <div class="prediction-header">
                <div class="prediction-header-left">
                    <span class="pred-icon">🚀</span>
                    <h3>Predictive AIOps — Dự đoán Tài nguyên (ML)</h3>
                </div>
                <div class="prediction-header-right">
                    <div class="pred-lookback">
                        <label for="pred-lookback-select">Dữ liệu:</label>
                        <select id="pred-lookback-select">
                            <option value="6">6 giờ</option>
                            <option value="12">12 giờ</option>
                            <option value="24" selected>24 giờ</option>
                            <option value="48">48 giờ</option>
                            <option value="168">7 ngày</option>
                        </select>
                    </div>
                    <div class="pred-toggle-wrapper">
                        <span class="pred-toggle-label">Bật dự đoán</span>
                        <div class="pred-toggle" id="pred-toggle" title="Bật/Tắt AI Prediction"></div>
                    </div>
                </div>
            </div>

            <!-- Content (hidden until toggled on) -->
            <div id="pred-content" style="display: none;">
                <!-- Overall Banner -->
                <div id="pred-overall-banner" class="pred-overall-banner healthy" style="display:none;"></div>
                
                <!-- Cards Grid -->
                <div id="pred-cards-grid" class="pred-cards-grid"></div>
            </div>
        `;

        dashGrid.parentNode.insertBefore(panel, dashGrid.nextSibling);

        // Bind events
        const toggle = document.getElementById('pred-toggle');
        toggle.addEventListener('click', () => {
            predictionEnabled = !predictionEnabled;
            toggle.classList.toggle('active', predictionEnabled);

            const content = document.getElementById('pred-content');
            if (predictionEnabled) {
                content.style.display = 'block';
                fetchPredictions();
            } else {
                content.style.display = 'none';
                destroyMiniCharts();
            }
        });

        // Lookback change
        const lookbackSelect = document.getElementById('pred-lookback-select');
        lookbackSelect.addEventListener('change', () => {
            if (predictionEnabled) {
                fetchPredictions();
            }
        });
    }

    let apexChartsLoaded = false;
    let apexChartsLoadingPromise = null;

    function loadApexCharts() {
        if (apexChartsLoaded) return Promise.resolve();
        if (apexChartsLoadingPromise) return apexChartsLoadingPromise;
        
        apexChartsLoadingPromise = new Promise((resolve, reject) => {
            if (window.ApexCharts) {
                apexChartsLoaded = true;
                return resolve();
            }
            const script = document.createElement('script');
            script.src = 'https://cdn.jsdelivr.net/npm/apexcharts';
            script.onload = () => {
                apexChartsLoaded = true;
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
        return apexChartsLoadingPromise;
    }

    // ── Fetch Predictions from API ──────────────────────────────────────
    async function fetchPredictions() {
        await loadApexCharts();
        const sysname = getSysname();
        if (!sysname) return;

        const lookback = document.getElementById('pred-lookback-select')?.value || 24;
        const cardsGrid = document.getElementById('pred-cards-grid');
        const banner = document.getElementById('pred-overall-banner');

        // Show loading
        cardsGrid.innerHTML = `
            <div class="pred-loading" style="grid-column: 1 / -1;">
                <div class="pred-spinner"></div>
                <span>AI đang phân tích xu hướng tài nguyên...</span>
            </div>
        `;
        banner.style.display = 'none';

        try {
            const response = await fetch(`${ML_API_URL}/${sysname}?hours_back=${lookback}`);

            if (!response.ok) {
                cardsGrid.innerHTML = `<div class="pred-loading" style="grid-column:1/-1;color:#f85149;">❌ Lỗi server (HTTP ${response.status})</div>`;
                return;
            }

            const data = await response.json();

            if (!data.ok) {
                cardsGrid.innerHTML = `<div class="pred-loading" style="grid-column:1/-1;color:#f85149;">❌ ${data.error || 'Lỗi phân tích'}</div>`;
                return;
            }

            predictionData = data;
            renderPredictions(data);

        } catch (err) {
            console.error('Prediction fetch error:', err);
            cardsGrid.innerHTML = `<div class="pred-loading" style="grid-column:1/-1;color:#f85149;">❌ Không thể kết nối. Kiểm tra server.</div>`;
        }
    }

    // ── Render Prediction Results ───────────────────────────────────────
    function renderPredictions(data) {
        const cardsGrid = document.getElementById('pred-cards-grid');
        const banner = document.getElementById('pred-overall-banner');

        // ── Overall Banner ──────────────────────────────────────────────
        banner.className = `pred-overall-banner ${data.overall_status}`;
        banner.textContent = data.overall_message;
        banner.style.display = 'flex';

        // ── Destroy old charts ──────────────────────────────────────────
        destroyMiniCharts();

        // ── Render Cards ────────────────────────────────────────────────
        const predictions = data.predictions || {};
        const metricOrder = ['disk', 'memory', 'cpu', 'temperature'];

        let cardsHTML = '';
        for (const key of metricOrder) {
            const pred = predictions[key];
            if (!pred) continue;

            const status = pred.status || 'unknown';
            const icon = METRIC_ICONS[key] || '📊';
            const unit = METRIC_UNITS[key] || '%';

            // Stats row
            let statsHTML = '';
            if (pred.current_value !== undefined) {
                statsHTML += `
                    <div class="pred-stat">
                        <span class="pred-stat-label">Hiện tại</span>
                        <span class="pred-stat-value">${pred.current_value}${unit}</span>
                    </div>`;
            }
            if (pred.slope_per_hour !== undefined) {
                const sign = pred.slope_per_hour >= 0 ? '+' : '';
                statsHTML += `
                    <div class="pred-stat">
                        <span class="pred-stat-label">Xu hướng/giờ</span>
                        <span class="pred-stat-value">${sign}${pred.slope_per_hour}${unit}</span>
                    </div>`;
            }
            if (pred.r_squared !== undefined) {
                statsHTML += `
                    <div class="pred-stat">
                        <span class="pred-stat-label">Độ tin cậy (R²)</span>
                        <span class="pred-stat-value">${(pred.r_squared * 100).toFixed(1)}%</span>
                    </div>`;
            }

            // TTF badge
            let ttfHTML = '';
            if (pred.time_to_failure) {
                const ttfClass = status === 'critical' ? 'danger' : status === 'warning' ? 'warning' : 'safe';
                ttfHTML = `<span class="pred-ttf ${ttfClass}">⏱ TTF: ${pred.time_to_failure}</span>`;
            }

            cardsHTML += `
                <div class="pred-card status-${status}">
                    <div class="pred-card-header">
                        <span class="pred-card-title">${icon} ${pred.metric || key}</span>
                        <span class="pred-card-badge ${status}">${status.replace('_', ' ')}</span>
                    </div>
                    <div class="pred-card-message">${pred.message || ''}</div>
                    <div class="pred-stats-row">${statsHTML}</div>
                    ${ttfHTML}
                    <div class="pred-chart-container" id="pred-chart-${key}"></div>
                </div>
            `;
        }

        cardsGrid.innerHTML = cardsHTML;

        // ── Render mini charts (after DOM insert) ────────────────────────
        requestAnimationFrame(() => {
            for (const key of metricOrder) {
                const pred = predictions[key];
                if (pred && (pred.trendline?.length > 0 || pred.forecast?.length > 0)) {
                    renderMiniChart(key, pred);
                }
            }
        });
    }

    // ── Render Mini ApexChart ────────────────────────────────────────────
    function renderMiniChart(metricKey, pred) {
        const containerId = `pred-chart-${metricKey}`;
        const container = document.getElementById(containerId);
        if (!container) return;

        // Check if ApexCharts is available
        if (typeof ApexCharts === 'undefined') {
            container.innerHTML = '<span style="color:#6e7681;font-size:11px;">Chart library not loaded</span>';
            return;
        }

        const unit = METRIC_UNITS[metricKey] || '%';
        const series = [];

        // Trendline (solid line)
        if (pred.trendline && pred.trendline.length > 0) {
            series.push({
                name: 'Xu hướng (Trendline)',
                data: pred.trendline, // [[ms, value], ...]
                type: 'line',
            });
        }

        // Forecast (dashed line)
        if (pred.forecast && pred.forecast.length > 0) {
            series.push({
                name: 'Dự đoán (Forecast)',
                data: pred.forecast,
                type: 'line',
            });
        }

        if (series.length === 0) return;

        const options = {
            chart: {
                type: 'line',
                height: 140,
                sparkline: { enabled: false },
                toolbar: { show: false },
                zoom: { enabled: false },
                background: 'transparent',
                fontFamily: 'Inter, system-ui, sans-serif',
                animations: {
                    enabled: true,
                    easing: 'easeinout',
                    speed: 600,
                },
            },
            series: series,
            stroke: {
                width: [2, 2],
                curve: 'smooth',
                dashArray: [0, 6], // solid for trendline, dashed for forecast
            },
            colors: ['#6c63ff', '#f85149'],
            fill: {
                type: 'solid',
                opacity: 1,
            },
            xaxis: {
                type: 'datetime',
                labels: {
                    show: true,
                    style: { colors: '#6e7681', fontSize: '9px' },
                    datetimeUTC: false,
                },
                axisBorder: { show: false },
                axisTicks: { show: false },
            },
            yaxis: {
                labels: {
                    show: true,
                    style: { colors: '#6e7681', fontSize: '9px' },
                    formatter: (val) => `${val.toFixed(0)}${unit}`,
                },
                min: metricKey === 'temperature' ? undefined : 0,
                max: metricKey === 'temperature' ? undefined : 100,
            },
            grid: {
                borderColor: 'rgba(255,255,255,0.04)',
                strokeDashArray: 3,
                padding: { left: 5, right: 5, top: 0, bottom: 0 },
            },
            tooltip: {
                theme: 'dark',
                x: { format: 'dd MMM HH:mm' },
                y: { formatter: (val) => `${val.toFixed(1)}${unit}` },
            },
            legend: {
                show: true,
                position: 'top',
                horizontalAlign: 'left',
                fontSize: '10px',
                labels: { colors: '#8b949e' },
                markers: { width: 8, height: 8 },
            },
            annotations: metricKey !== 'temperature' ? {
                yaxis: [{
                    y: metricKey === 'disk' ? 95 : metricKey === 'memory' ? 90 : 90,
                    borderColor: '#f85149',
                    strokeDashArray: 4,
                    label: {
                        text: 'Ngưỡng nguy hiểm',
                        position: 'front',
                        style: {
                            color: '#f85149',
                            background: 'rgba(248,81,73,0.1)',
                            fontSize: '9px',
                            padding: { left: 4, right: 4, top: 2, bottom: 2 },
                        },
                    },
                }],
            } : {},
        };

        try {
            const chart = new ApexCharts(container, options);
            chart.render();
            miniCharts[metricKey] = chart;
        } catch (e) {
            console.error(`Error rendering chart for ${metricKey}:`, e);
        }
    }

    // ── Destroy all mini charts ─────────────────────────────────────────
    function destroyMiniCharts() {
        for (const key of Object.keys(miniCharts)) {
            try {
                miniCharts[key].destroy();
            } catch (e) { /* ignore */ }
        }
        miniCharts = {};
    }

    // ── Initialize ──────────────────────────────────────────────────────
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', createPredictionPanel);
    } else {
        createPredictionPanel();
    }

})();
