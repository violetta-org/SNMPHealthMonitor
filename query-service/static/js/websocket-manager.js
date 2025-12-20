/**
 * WebSocket (Socket.IO) Manager Module
 * Handles Socket.IO connection, subscription, and message routing
 * Separated from UI logic and data processing
 */
export class WebSocketManager {
    constructor(sysname, topic) {
        this.sysname = sysname;
        this.topic = topic || 'systemstatus';
        this.socket = null;
        this.isConnected = false;
        this.listeners = new Map();
    }

    /**
     * Emit a historical range query to server
     * data: { sysname, topic, start_time, end_time, page?, per_page? }
     */
    queryRange(data) {
        if (!this.socket || !this.isConnected) {
            console.warn('[WebSocketManager] Cannot query range - socket not connected');
            return;
        }
        const payload = {
            sysname: data.sysname || this.sysname,
            topic: data.topic || this.topic,
            start_time: data.start_time,
            end_time: data.end_time,
            page: data.page,
            per_page: data.per_page
        };
        console.log('[WebSocketManager] Emitting query_range', payload);
        this.socket.emit('query_range', payload);
    }

    /**
     * Connect to Socket.IO server và subscribe sysname/topic
     */
    connect() {
        if (!window.io) {
            console.error('[WebSocketManager] Socket.IO client (io) is not available on window');
            return;
        }

        if (this.socket) {
            console.log('[WebSocketManager] Existing Socket.IO connection found, disconnecting before reconnect...');
            this.socket.disconnect();
            this.socket = null;
        }

        console.log('[WebSocketManager] Connecting to Socket.IO on same origin...');

        try {
            // Kết nối đến cùng host/port với custom path /query-socket.io
            this.socket = window.io({
                path: "/query-socket.io",
            });

            this.socket.on('connect', () => {
                this.isConnected = true;
                console.log('[WebSocketManager] Socket.IO connected, sid=' + this.socket.id);

                // Đăng ký subscribe ngay khi connect
                const payload = {
                    sysname: this.sysname,
                    topic: this.topic
                };
                console.log('[WebSocketManager] Subscribing with payload:', payload);
                this.socket.emit('subscribe', payload);

                this.emit('connected');
            });

            this.socket.on('disconnect', (reason) => {
                this.isConnected = false;
                console.log('[WebSocketManager] Socket.IO disconnected, reason=' + reason);
                this.emit('disconnected');
            });

            this.socket.on('connect_error', (error) => {
                console.error('[WebSocketManager] Socket.IO connect_error:', error);
                this.emit('error', error);
            });

            if (this.socket.io && this.socket.io.on) {
                this.socket.io.on('reconnect_failed', () => {
                    console.error('[WebSocketManager] Socket.IO reconnect_failed');
                    this.emit('reconnect_failed');
                });
            }

            // Lắng nghe dữ liệu metrics từ server
            this.socket.on('data', (message) => {
                console.log('[WebSocketManager] Received data event, type=' + message.type + ', topic=' + message.topic);
                this.emit('message', message);
            });

            // Lắng nghe pong từ server (giữ kết nối)
            this.socket.on('pong', (data) => {
                console.log('[WebSocketManager] Received pong:', data);
            });
        } catch (error) {
            console.error('[WebSocketManager] Connection error:', error);
            this.emit('error', error);
        }
    }

    /**
     * Topic đã được subscribe khi connect, không cần subscribe thêm
     * Giữ lại để tương thích nhưng không làm gì
     */
    subscribe(topic, page = 1, perPage = 10) {
        console.log('[WebSocketManager] Already subscribed to topic ' + this.topic + ' on connect');
    }

    /**
     * Unsubscribe không cần thiết vì topic được xác định khi connect
     * Giữ lại để tương thích
     */
    unsubscribe(topic) {
        console.log('[WebSocketManager] Cannot unsubscribe - topic is bound to connection');
    }

    /**
     * Send pagination request qua Socket.IO
     */
    paginate(topic, page, perPage = 10) {
        if (!this.socket || !this.isConnected) {
            console.warn('[WebSocketManager] Cannot paginate - socket not connected');
            return;
        }
        const payload = {
            sysname: this.sysname,
            topic: topic,
            page: page,
            per_page: perPage
        };
        console.log('[WebSocketManager] Paginating topic ' + topic + ' to page ' + page, payload);
        this.socket.emit('paginate', payload);
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
        if (this.socket) {
            console.log('[WebSocketManager] Disconnecting Socket.IO...');
            this.socket.disconnect();
            this.socket = null;
        }
        this.isConnected = false;
        this.listeners.clear();
        console.log('[WebSocketManager] Disconnected');
    }
}

