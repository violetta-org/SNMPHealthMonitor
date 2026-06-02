
/**
 * Base Dashboard UI Module
 * Common functionality for all dashboard pages
 */
import { DataProcessor } from '../data-processor.js';

export class BaseDashboardUI {
    constructor(dataProcessor) {
        this.elements = new Map();
        this.dataProcessor = dataProcessor || new DataProcessor();
        this.lastUpdateTime = null;

        // Auto-initialize text formatting if DOM is ready, or wait
        // Defer to next tick to prevent layout invalidation prior to Chart.js instantiation (forced reflow mitigation)
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', () => {
                setTimeout(() => this.init(), 0);
            });
        } else {
            setTimeout(() => this.init(), 0);
        }
    }

    init() {
        console.log('[BaseDashboardUI] init() called');
        // Initial format of timestamp from server (raw ISO -> Readable)
        const lastUpdateEl = document.getElementById('last-update-time');
        console.log('[BaseDashboardUI] Found element:', lastUpdateEl ? 'Yes' : 'No', 'Content:', lastUpdateEl ? lastUpdateEl.textContent : 'null');

        if (lastUpdateEl) {
            const rawText = lastUpdateEl.textContent.trim();
            if (rawText && rawText !== '-' && rawText !== 'N/A') {
                console.log('[BaseDashboardUI] Formatting raw timestamp:', rawText);
                // Treat content as partial ISO or full ISO
                this.updateLastUpdateTime({ last_seen: rawText });
            }
        }
    }

    /**
     * Update server IP address
     */
    updateServerIP(deviceInfo) {
        const ipElement = document.getElementById('server-ip');
        if (ipElement && deviceInfo && deviceInfo.ip_address) {
            ipElement.textContent = `(${deviceInfo.ip_address})`;
            ipElement.style.display = 'inline';
        }
    }

    /**
     * Register DOM element
     */
    registerElement(key, selector) {
        const element = document.querySelector(selector);
        if (element) {
            this.elements.set(key, element);
            // Pre-cache progress circle to avoid querySelector in rapid update loops
            const progress = element.querySelector('.gauge-progress');
            if (progress) {
                this.elements.set(key + '-progress', progress);
            }
            console.log(`[BaseDashboardUI] Registered element: ${key} -> ${selector}`);
        } else {
            console.warn(`[BaseDashboardUI] Element not found: ${selector}`);
        }
    }

    /**
     * Update circular gauge
     */
    updateGauge(id, percent) {
        const gaugeElement = this.elements.get(id + '-gauge');
        const valueElement = this.elements.get(id + '-value');

        if (!gaugeElement) {
            console.warn(`[BaseDashboardUI] Gauge not found: ${id}-gauge`);
            return;
        }

        const clampedPercent = Math.min(Math.max(percent, 0), 100);

        // Find the progress circle from cache to avoid Layout Thrashing
        const progressCircle = this.elements.get(id + '-gauge-progress') || gaugeElement.querySelector('.gauge-progress');
        if (progressCircle) {
            const circumference = 2 * Math.PI * 45; // radius = 45
            const offset = circumference - (clampedPercent / 100) * circumference;
            progressCircle.style.strokeDashoffset = offset;
        }

        // Update value text
        if (valueElement) {
            valueElement.textContent = Math.round(clampedPercent) + '%';
        }

        console.log(`[BaseDashboardUI] Updated gauge ${id}: ${clampedPercent.toFixed(1)}%`);
    }

    /**
     * Update text content
     */
    updateText(id, text) {
        const element = this.elements.get(id);
        if (element) {
            element.textContent = text;
        }
    }

    /**
     * Update last update timestamp from device last_seen
     */
    updateLastUpdateTime(deviceInfo) {
        const lastUpdateElement = this.elements.get('last-update-time') || document.getElementById('last-update-time');
        if (lastUpdateElement) {
            if (deviceInfo && deviceInfo.last_seen) {
                try {
                    const lastSeenDate = new Date(deviceInfo.last_seen);

                    // Manual formatting to match server-side YYYY-MM-DD HH:MM:SS
                    const pad = (n) => n.toString().padStart(2, '0');
                    const timeString = `${lastSeenDate.getFullYear()}-${pad(lastSeenDate.getMonth() + 1)}-${pad(lastSeenDate.getDate())} ` +
                        `${pad(lastSeenDate.getHours())}:${pad(lastSeenDate.getMinutes())}:${pad(lastSeenDate.getSeconds())}`;

                    lastUpdateElement.textContent = timeString;
                    this.lastUpdateTime = lastSeenDate;
                } catch (e) {
                    console.warn('[BaseDashboardUI] Error parsing last_seen:', e);
                    lastUpdateElement.textContent = 'N/A';
                }
            } else {
                lastUpdateElement.textContent = 'N/A';
            }
        }
    }

    /**
     * Update device online status badge (from database, not WebSocket)
     */
    updateDeviceStatus(deviceInfo) {
        const statusElement = this.elements.get('connection-status');
        if (statusElement && deviceInfo) {
            const isOnline = deviceInfo.online === true;
            statusElement.textContent = isOnline ? 'Online' : 'Offline';
            statusElement.className = isOnline ? 'status-badge status-connected' : 'status-badge status-disconnected';
        }
    }

    /**
     * Update connection status badge (WebSocket - tạm thời không dùng)
     */
    updateConnectionStatus(isConnected) {
        // Tạm thời không update WebSocket status
        // const statusElement = this.elements.get('connection-status');
        // if (statusElement) {
        //     statusElement.textContent = isConnected ? 'Connected' : 'Disconnected';
        //     statusElement.className = isConnected ? 'status-badge status-connected' : 'status-badge status-disconnected';
        // }
    }

    /**
     * Show toast notification
     */
    showToast(message, type = 'error', options = {}) {
        const container = document.getElementById('toast-container');
        if (!container) {
            console.warn('[BaseDashboardUI] Toast container not found');
            return;
        }

        const toast = document.createElement('div');
        toast.className = 'toast ' + type;

        const icons = {
            error: '❌',
            success: '✅',
            warning: '⚠️',
            info: 'ℹ️'
        };

        const titles = {
            error: 'Error',
            success: 'Success',
            warning: 'Warning',
            info: 'Information'
        };

        let toastHTML = `
            <div class="toast-icon">${icons[type] || icons.info}</div>
            <div class="toast-content">
                <div class="toast-title">${titles[type] || titles.info}</div>
                <div class="toast-message">${message}</div>
            </div>
        `;

        if (options.actions && options.actions.length > 0) {
            toastHTML += '<div class="toast-actions">';
            options.actions.forEach(action => {
                toastHTML += `<button class="toast-btn toast-btn-${action.type || 'secondary'}" data-action="${action.id}">${action.label}</button>`;
            });
            toastHTML += '</div>';
        }

        toast.innerHTML = toastHTML;
        container.appendChild(toast);

        if (options.actions) {
            options.actions.forEach(action => {
                const btn = toast.querySelector(`[data-action="${action.id}"]`);
                if (btn && action.callback) {
                    btn.addEventListener('click', () => {
                        action.callback();
                        this.closeToast(toast);
                    });
                }
            });
        }

        const duration = options.duration || (type === 'error' ? 3000 : 5000);
        if (duration > 0) {
            setTimeout(() => {
                this.closeToast(toast);
            }, duration);
        }

        console.log(`[BaseDashboardUI] Toast shown: ${type} - ${message}`);
    }

    /**
     * Close toast notification
     */
    closeToast(toast) {
        toast.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => {
            toast.remove();
        }, 300);
    }

    /**
     * Show error with retry button
     */
    showError(message, retryCallback) {
        this.showToast(message, 'error', {
            duration: 0,
            actions: [
                {
                    id: 'retry',
                    label: 'Retry',
                    type: 'primary',
                    callback: retryCallback
                },
                {
                    id: 'close',
                    label: 'Close',
                    type: 'secondary',
                    callback: () => { }
                }
            ]
        });
    }

    /**
     * Hide all toasts
     */
    hideError() {
        const container = document.getElementById('toast-container');
        if (container) {
            container.innerHTML = '';
        }
    }

    /**
     * Show success notification
     */
    showSuccess(message) {
        this.showToast(message, 'success', { duration: 3000 });
    }

    /**
     * Show warning notification
     */
    showWarning(message) {
        this.showToast(message, 'warning', { duration: 4000 });
    }
}

