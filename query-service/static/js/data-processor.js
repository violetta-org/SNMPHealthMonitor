/**
 * Data Processor Module
 * Processes raw metric data from WebSocket
 * Separated from WebSocket and UI logic
 */
export class DataProcessor {
    constructor() {
        this.processors = new Map();
        this.registerDefaultProcessors();
    }

    /**
     * Register default data processors
     */
    registerDefaultProcessors() {
        // System status processor (default) - pass through vì structure đã đúng
        this.processors.set('systemstatus', (data) => {
            console.log('[DataProcessor] Processing systemstatus data');
            // Pass through vì server đã trả về đúng format: {system_info, load_avg, memory, swap, cpu_percent}
            return data;
        });

        // System metrics processor - pass through vì structure đã đúng
        this.processors.set('system', (data) => {
            console.log('[DataProcessor] Processing system data', data);
            // Ensure structure is correct, include device_info
            return {
                device_info: data.device_info || {},
                system_info: data.system_info || {},
                load_avg: data.load_avg || {}
            };
        });

        // CPU metrics processor
        this.processors.set('cpu', (data) => {
            console.log('[DataProcessor] Processing cpu data', data);
            // Include device_info
            return {
                device_info: data.device_info || {},
                cpu_percent: data.cpu_percent || []
            };
        });

        // Memory metrics processor
        this.processors.set('memory', (data) => {
            console.log('[DataProcessor] Processing memory data', data);
            // Include device_info
            return {
                device_info: data.device_info || {},
                memory: data.memory || {},
                swap: data.swap || {}
            };
        });

        // Network metrics processor
        this.processors.set('network', (data) => {
            console.log('[DataProcessor] Processing network data', data);
            // Include device_info
            return {
                device_info: data.device_info || {},
                net_io: data.net_io || []
            };
        });

        // Disk metrics processor
        this.processors.set('disk', (data) => {
            console.log('[DataProcessor] Processing disk data', data);
            // Include device_info
            return {
                device_info: data.device_info || {},
                disk_usage: data.disk_usage || []
            };
        });

        // Disk IO metrics processor
        this.processors.set('diskio', (data) => {
            console.log('[DataProcessor] Processing diskio data', data);
            // Include device_info
            return {
                device_info: data.device_info || {},
                disk_io: data.disk_io || {}
            };
        });


    }

    /**
     * Register custom processor for a topic
     */
    registerProcessor(topic, processor) {
        console.log(`[DataProcessor] Registering processor for topic: ${topic}`);
        this.processors.set(topic, processor);
    }

    /**
     * Process data for a specific topic
     */
    process(topic, rawData) {
        const processor = this.processors.get(topic);
        if (processor) {
            try {
                return processor(rawData);
            } catch (error) {
                console.error(`[DataProcessor] Error processing ${topic}:`, error);
                return null;
            }
        } else {
            console.warn(`[DataProcessor] No processor found for topic: ${topic}`);
            return rawData;
        }
    }

    /**
     * Format bytes to human readable
     */
    formatBytes(bytes) {
        if (!bytes || bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
    }

    /**
     * Format uptime from seconds to human readable
     */
    formatUptime(seconds) {
        if (!seconds) return 'N/A';
        const days = Math.floor(seconds / 86400);
        const hours = Math.floor((seconds % 86400) / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${days}d ${hours}h ${minutes}m`;
    }
}

