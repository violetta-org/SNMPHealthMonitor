/**
 * Dashboard Controller Module
 * Main controller that orchestrates WebSocket, DataProcessor, and Topic-specific Dashboard
 * Uses ES6 modules for clean separation of concerns
 */
import { WebSocketManager } from './websocket-manager.js';
import { DataProcessor } from './data-processor.js';

// Import topic-specific dashboard modules
import { SystemStatusDashboard } from './dashboard/systemstatus.js';
import { NetworkDashboard } from './dashboard/network.js';
import { DiskDashboard } from './dashboard/disk.js';
import { DiskIODashboard } from './dashboard/diskio.js';

// Dashboard factory - maps topic to dashboard class
const DASHBOARD_CLASSES = {
    'systemstatus': SystemStatusDashboard,
    'network': NetworkDashboard,
    'disk': DiskDashboard,
    'diskio': DiskIODashboard
};

export class Dashboard {
    constructor(sysname, topic) {
        console.log(`[Dashboard] Initializing dashboard for ${sysname}, topic: ${topic}`);
        this.sysname = sysname;
        this.topic = topic || 'systemstatus';
        
        // Initialize modules
        this.wsManager = new WebSocketManager(sysname, this.topic);
        this.dataProcessor = new DataProcessor();
        
        // Get appropriate dashboard UI class for this topic
        const DashboardClass = DASHBOARD_CLASSES[this.topic];
        if (!DashboardClass) {
            console.warn(`[Dashboard] Unknown topic: ${this.topic}, using SystemStatusDashboard`);
            this.uiUpdater = new SystemStatusDashboard(this.dataProcessor);
        } else {
            this.uiUpdater = new DashboardClass(this.dataProcessor);
        }
        
        // Register UI elements (topic-specific)
        this.uiUpdater.registerElements();
        
        // Setup WebSocket event handlers
        this.setupWebSocketHandlers();
        
        // Connect WebSocket
        this.wsManager.connect();
    }

    /**
     * Setup WebSocket event handlers
     */
    setupWebSocketHandlers() {
        console.log('[Dashboard] Setting up WebSocket handlers');
        
        // Handle connection
        this.wsManager.on('connected', () => {
            console.log(`[Dashboard] WebSocket connected to ${this.sysname}/${this.topic}`);
            // Tạm thời không update WebSocket status
            // this.uiUpdater.updateConnectionStatus(true);
            this.uiUpdater.hideError();
        });
        
        // Handle disconnection
        this.wsManager.on('disconnected', () => {
            console.log('[Dashboard] WebSocket disconnected');
            // Tạm thời không update WebSocket status
            // this.uiUpdater.updateConnectionStatus(false);
        });
        
        // Handle errors
        this.wsManager.on('error', (error) => {
            console.error('[Dashboard] WebSocket error:', error);
            this.uiUpdater.showError('Connection error. Attempting to reconnect...', () => {
                console.log('[Dashboard] Retry button clicked, reconnecting...');
                this.wsManager.connect();
            });
        });
        
        // Handle reconnect failed
        this.wsManager.on('reconnect_failed', () => {
            console.error('[Dashboard] Reconnection failed');
            this.uiUpdater.showError('Server is unreachable. Please check your connection.', () => {
                console.log('[Dashboard] Retry button clicked, reconnecting...');
                this.wsManager.connect();
            });
        });
        
        // Handle incoming messages
        this.wsManager.on('message', (message) => {
            this.handleMessage(message);
        });
    }

    /**
     * Handle incoming WebSocket message
     */
    handleMessage(message) {
        console.log('[Dashboard] Handling message:', message.type, 'topic:', message.topic, 'expected:', this.topic);
        console.log('[Dashboard] Message data:', message.data);
        
        if (message.type === 'data' && message.topic === this.topic) {
            try {
                // Process data
                console.log(`[Dashboard] Processing ${this.topic} data...`);
                const processedData = this.dataProcessor.process(this.topic, message.data);
                console.log(`[Dashboard] Processed data:`, processedData);
                
                if (processedData) {
                    // Update UI using topic-specific dashboard's update method
                    console.log(`[Dashboard] Updating UI for topic: ${this.topic}`);
                    this.uiUpdater.update(processedData);
                    
                    this.uiUpdater.hideError();
                } else {
                    console.warn('[Dashboard] Failed to process data');
                    this.uiUpdater.showWarning('Failed to process data');
                }
            } catch (error) {
                console.error('[Dashboard] Error handling message:', error);
                this.uiUpdater.showWarning('Error processing data: ' + error.message);
            }
        }
    }

    /**
     * Cleanup on destroy
     */
    destroy() {
        console.log('[Dashboard] Destroying dashboard');
        this.wsManager.disconnect();
        // Clean up chart performance monitors if present
        try {
            if (this.uiUpdater && this.uiUpdater.charts && this.uiUpdater.charts.dataManager && typeof this.uiUpdater.charts.dataManager.destroy === 'function') {
                this.uiUpdater.charts.dataManager.destroy();
                console.log('[Dashboard] ChartDataManager destroyed');
            }
        } catch (e) {
            console.warn('[Dashboard] Error during ChartDataManager destroy', e);
        }
    }
}

// Initialize dashboard when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    console.log('[Dashboard] DOM loaded, initializing dashboard');
    
    // Get sysname and topic from data attributes (injected by server)
    let sysname = document.body.dataset.sysname;
    let topic = document.body.dataset.topic;
    
    if (!sysname || !topic) {
        // Fallback: Parse from URL path
        const pathParts = window.location.pathname.split('/').filter(p => p);
        const dashboardIndex = pathParts.indexOf('dashboard');
        if (dashboardIndex !== -1 && dashboardIndex + 1 < pathParts.length) {
            sysname = sysname || pathParts[dashboardIndex + 1];
            if (dashboardIndex + 2 < pathParts.length) {
                topic = topic || pathParts[dashboardIndex + 2];
            }
        }
        sysname = sysname || 'default';
        topic = topic || 'systemstatus';
    }
    
    console.log(`[Dashboard] Initializing: sysname=${sysname}, topic=${topic}`);
    
    // Update server name in header
    const serverNameElement = document.getElementById('server-name');
    if (serverNameElement) {
        serverNameElement.textContent = sysname;
    }
    
    // Initialize dashboard
    window.dashboard = new Dashboard(sysname, topic);
    
    // Cleanup on page unload - đảm bảo WebSocket được đóng đúng cách
    window.addEventListener('beforeunload', () => {
        console.log('[Dashboard] Page unloading, cleaning up...');
        if (window.dashboard) {
            window.dashboard.destroy();
        }
    });
});
