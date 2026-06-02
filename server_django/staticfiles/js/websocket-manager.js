/**
 * WebSocket Manager Module (Native API)
 * Handles WebSocket connection, subscription, and message routing
 * Replaces Socket.IO implementation
 */
export class WebSocketManager {
    constructor(sysname, topic) {
        this.sysname = sysname;
        this.topic = topic || 'systemstatus';
        this.socket = null;
        this.isConnected = false;
        this.listeners = new Map();
        this.reconnectInterval = 3000;
        this.reconnectTimer = null;
        this.isExplicitDisconnect = false;
    }

    /**
     * Helper to send JSON data
     */
    _send(data) {
        if (this.socket && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            console.warn('[WebSocketManager] Cannot send message - socket not open');
        }
    }

    /**
     * Emit a historical range query to server
     * data: { sysname, topic, start_time, end_time, page?, per_page? }
     */
    queryRange(data) {
        const payload = {
            action: 'query_range',
            sysname: data.sysname || this.sysname,
            topic: data.topic || this.topic,
            start_time: data.start_time,
            end_time: data.end_time,
            page: data.page,
            per_page: data.per_page
        };
        console.log('[WebSocketManager] Sending query_range via WebSocket', payload);
        this._send(payload);
    }

    /**
     * Connect to WebSocket server using native API
     */
    connect() {
        if (this.socket) {
            console.log('[WebSocketManager] Existing connection found, closing before reconnect...');
            const tempSocket = this.socket;
            this.socket = null; 
            tempSocket.close();
        }

        this.isExplicitDisconnect = false;

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/metrics/`;
        
        console.log(`[WebSocketManager] Connecting to ${wsUrl}...`);

        try {
            this.socket = new WebSocket(wsUrl);

            this.socket.onopen = () => {
                this.isConnected = true;
                console.log('[WebSocketManager] WebSocket connected');

                if (this.reconnectTimer) {
                    clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = null;
                }

                // Subscribe immediately upon connection
                const payload = {
                    action: 'subscribe',
                    sysname: this.sysname,
                    topic: this.topic
                };
                console.log('[WebSocketManager] sending subscribe payload:', payload);
                this._send(payload);

                this.emit('connected');
            };

            this.socket.onclose = (event) => {
                this.isConnected = false;
                console.log(`[WebSocketManager] WebSocket disconnected (code: ${event.code}, reason: ${event.reason})`);
                this.emit('disconnected');

                if (!this.isExplicitDisconnect) {
                    console.log(`[WebSocketManager] Reconnecting in ${this.reconnectInterval/1000}s...`);
                    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = setTimeout(() => {
                        this.connect();
                    }, this.reconnectInterval);
                }
            };

            this.socket.onerror = (error) => {
                console.error('[WebSocketManager] WebSocket error:', error);
                this.emit('error', error);
            };

            this.socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    
                    if (message.type === 'data') {
                        this.emit('message', message);
                    } else if (message.type === 'pong') {
                        // Received pong
                    } else {
                        // Forward generic messages too
                        this.emit('message', message);
                    }
                } catch (e) {
                    console.error('[WebSocketManager] Error parsing message:', e);
                }
            };

        } catch (error) {
            console.error('[WebSocketManager] Connection setup error:', error);
            this.emit('error', error);
        }
    }

    /**
     * Subscribe to a topic
     */
    subscribe(topic, page = 1, perPage = 10) {
        this.topic = topic;
        const payload = {
            action: 'subscribe',
            sysname: this.sysname,
            topic: topic
        };
        console.log('[WebSocketManager] Subscribing to topic ' + topic);
        this._send(payload);
    }

    /**
     * Unsubscribe from a topic
     */
    unsubscribe(topic) {
        const payload = {
            action: 'unsubscribe',
            sysname: this.sysname,
            topic: topic
        };
        console.log('[WebSocketManager] Unsubscribing from topic ' + topic);
        this._send(payload);
    }

    /**
     * Send pagination request
     */
    paginate(topic, page, perPage = 10) {
        const payload = {
            action: 'paginate',
            sysname: this.sysname,
            topic: topic,
            page: page,
            per_page: perPage
        };
        console.log('[WebSocketManager] Paginating topic ' + topic + ' to page ' + page, payload);
        this._send(payload);
    }

    /**
     * Register event listener
     */
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }

    /**
     * Remove event listener
     */
    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }

    /**
     * Emit event to listeners
     */
    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`[WebSocketManager] Error in event listener:`, error);
                }
            });
        }
    }

    /**
     * Disconnect WebSocket
     */
    disconnect() {
        this.isExplicitDisconnect = true;
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
        if (this.socket) {
            console.log('[WebSocketManager] Disconnecting WebSocket...');
            this.socket.close();
            this.socket = null;
        }
        this.isConnected = false;
        this.listeners.clear();
        console.log('[WebSocketManager] Disconnected');
    }
}

