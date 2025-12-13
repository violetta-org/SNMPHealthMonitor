# Phân tích App Flow - Query Service

## 1. App Initialization (Flask + Socket.IO)

### Flask app & Socket.IO setup (input, process, output)
- **Input**: None
- **Process**: 
  - Tạo Flask app với `static_folder="static"` và `template_folder="template"`.
  - Khởi tạo Flask-SocketIO với custom path `query-socket.io`.
  - Gán instance SocketIO vào `ws_manager.sio` để WebSocketManager có thể emit dữ liệu.
  - Đăng ký HTTP Blueprint `api_bp` tại prefix `/api`.
- **Output**: Flask app + Socket.IO server đã cấu hình.

### Main Entry Point (if __name__ == "__main__")
- **Input**: None
- **Process**: 
  - Khởi tạo `UDPNotificationListener` với callback `on_new_data` và start listener (daemon thread).
  - Chạy `socketio.run(app, host=API_HOST, port=API_PORT)`.
  - Khi shutdown: dừng UDP listener và log trạng thái shutdown.
- **Output**: Query-service chạy trên host:port được cấu hình, sẵn sàng nhận HTTP + Socket.IO + UDP.

---

## 2. API Routes (api/router.py - Flask Blueprint)

### subscribe_dashboard_default() (input, process, output)
- **Input**: `sysname: str`
- **Process**: Render `dashboard.html` với topic mặc định `"systemstatus"` cho server `sysname`.
- **Output**: HTML dashboard mặc định.

### subscribe_dashboard() (input, process, output)
- **Input**: `sysname: str, topic: str`
- **Process**: 
  - Map topic đến template tương ứng qua `TOPIC_TEMPLATES`.
  - Fallback về `dashboard.html` nếu topic không hợp lệ.
  - Render template với `sysname` và `topic`.
- **Output**: HTML dashboard cho topic tương ứng.

---

## 4. Real-time Layer (Socket.IO + WebSocketManager)

### Socket.IO events (input, process, output)

#### connect (Socket.IO)
- **Input**: `sid, environ, auth`
- **Process**: Log client connect, chuẩn bị cho subscribe.
- **Output**: Client được kết nối, nhưng chưa join topic nào.

#### disconnect (Socket.IO)
- **Input**: `sid`
- **Process**: Gọi `ws_manager.disconnect(sid)` để rời room và cleanup mapping.
- **Output**: Client rời khỏi tất cả topics và rooms liên quan.

#### subscribe (Socket.IO)
- **Input**: `sid, data: { sysname: str, topic: str }`
- **Process**: 
  - Lấy `sysname` và `topic` (default `systemstatus` nếu thiếu).
  - Gọi `ws_manager.connect(sid, sysname, topic)` để join room `sysname:topic`.
  - Gọi `get_topic_data()` để lấy dữ liệu ban đầu (với `page`, `per_page` mặc định nếu cần).
  - Emit event `"data"` về riêng client (`to=sid`).
- **Output**: Client nhận JSON metrics ban đầu cho topic đã subscribe.

#### ping (Socket.IO)
- **Input**: `sid, data`
- **Process**: Log ping, emit `"pong"` với timestamp về cho client.
- **Output**: Event `"pong"` cho client để giữ kết nối.

#### paginate (Socket.IO)
- **Input**: `sid, data: { sysname: str, topic: 'diskio', page: int, per_page: int }`
- **Process**: 
  - Validate `sysname` và đảm bảo `topic == 'diskio'`.
  - Gọi `get_topic_data()` với `page` và `per_page` truyền rõ ràng.
  - Emit `"data"` chỉ về client request (`to=sid`).
- **Output**: Client nhận trang `diskio` metrics tương ứng.

---

## 5. Data Fetching Functions (services/topic_service.py)

### get_topic_data() (input, process, output)
- **Input**: `sysname: str, topic: str, notify_timestamp: Optional[float] = None, page: int = 1, per_page: int = 10`
- **Process**: 
  - Route đến hàm query tương ứng dựa trên topic (`system`, `cpu`, `memory`, `network`, `disk`, `diskio`, ...).
  - Hỗ trợ pagination cho `diskio` topic thông qua `page` và `per_page`.
- **Output**: `dict` chứa dữ liệu metrics.

### stream_topic_data() (input, process, output)
- **Input**: `sysname: str, topic: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Gọi `get_topic_data()` để lấy dữ liệu mới nhất cho topic.
  - Gọi `ws_manager.stream_data(sysname, topic, data)` để gửi đến tất cả clients đã subscribe.
- **Output**: None (stream data qua WebSocket manager).

---

## 6. UDP Notification Handler (app.py)

### on_new_data() (input, process, output)
- **Input**: `message: dict` (chứa event, sysname, metric_count, timestamp)
- **Process**: 
  - Validate event = "new_data"
  - Lấy active topics có subscribers
  - Schedule streaming tasks cho mỗi active topic
- **Output**: None (trigger streaming tasks)

---

## 7. Database Connection (db/connection.py)

### create_connection() (input, process, output)
- **Input**: None
- **Process**: Tạo PyMySQL connection với DictCursor
- **Output**: `pymysql.Connection`

### get_db() (input, process, output)
- **Input**: None
- **Process**: Context manager tạo connection, yield connection, đóng khi xong
- **Output**: Context manager cho database connection

---

## 8. Database Query Functions (db/queries.py)

### get_device_info() (input, process, output)
- **Input**: `sysname: str`
- **Process**: Query devices table để lấy online, last_seen, ip_address
- **Output**: `Dict[str, Any]` chứa device info

### get_system_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Tính cutoff time (notify_timestamp - 30s hoặc current time)
  - Query device_info, system_info, load_avg
- **Output**: `Dict[str, Any]` chứa device_info, system_info, load_avg

### get_status_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: Aggregate system, memory, cpu metrics (không có disk usage)
- **Output**: `Dict[str, Any]` chứa merged metrics

### get_cpu_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Tính cutoff time
  - Query latest CPU percent per core với ROW_NUMBER window function
- **Output**: `Dict[str, Any]` chứa device_info, cpu_percent

### get_memory_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Tính cutoff time
  - Query latest memory và swap metrics
- **Output**: `Dict[str, Any]` chứa device_info, memory, swap

### get_network_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Tính cutoff time
  - Query network I/O với calculated rates (send_bytes_s, recv_bytes_s) dùng window function
- **Output**: `Dict[str, Any]` chứa device_info, net_io

### get_disk_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None`
- **Process**: 
  - Tính cutoff time
  - Query latest disk usage per mount
- **Output**: `Dict[str, Any]` chứa device_info, disk_usage

### get_disk_io_metrics() (input, process, output)
- **Input**: `sysname: str, notify_timestamp: Optional[float] = None, page: int = 1, per_page: int = 10`
- **Process**: 
  - Tính cutoff time và offset
  - Query disk I/O với calculated speeds (read_bytes_s, write_bytes_s)
  - Filter loopback, RAM disks, optical drives
  - Pagination và sort by total I/O speed
- **Output**: `Dict[str, Any]` chứa device_info, disk_io (data + pagination info)

---

## 9. Serialization Utilities (utils/serialize.py)

### serialize_row() (input, process, output)
- **Input**: `row: Dict[str, Any] | None`
- **Process**: Convert datetime objects thành ISO format strings
- **Output**: `Dict[str, Any] | None` với datetime đã serialize

### serialize_rows() (input, process, output)
- **Input**: `rows: List[Dict[str, Any]]`
- **Process**: Serialize tất cả rows trong list
- **Output**: `List[Dict[str, Any]]` với tất cả datetime đã serialize

---

## 10. UDP Listener (notifications/udp_listener.py)

### UDPNotificationListener.__init__() (input, process, output)
- **Input**: `port: int = NOTIFY_PORT, callback: Callable = None`
- **Process**: Khởi tạo listener với port và callback function
- **Output**: UDPNotificationListener instance

### UDPNotificationListener.start() (input, process, output)
- **Input**: None
- **Process**: Start daemon thread để listen UDP messages
- **Output**: None (thread chạy background)

### UDPNotificationListener.stop() (input, process, output)
- **Input**: None
- **Process**: Set running=False, close socket, wait thread finish
- **Output**: None

### UDPNotificationListener._listen() (input, process, output)
- **Input**: None
- **Process**: 
  - Bind UDP socket, set timeout 1s
  - Loop: nhận UDP messages, parse JSON, gọi callback nếu event="new_data"
- **Output**: None (chạy trong thread)

---

## 11. WebSocket Manager (notifications/websocket_manager.py)

### WebSocketManager.__init__() (input, process, output)
- **Input**: None
- **Process**: Khởi tạo topic_websockets mapping và websocket_topic reverse mapping
- **Output**: WebSocketManager instance

### WebSocketManager.connect() (input, process, output)
- **Input**: `websocket: WebSocket, sysname: str, topic: str`
- **Process**: 
  - Accept WebSocket
  - Thêm websocket vào topic_websockets[sysname:topic]
  - Lưu reverse mapping
- **Output**: None

### WebSocketManager.disconnect() (input, process, output)
- **Input**: `websocket: WebSocket`
- **Process**: 
  - Xóa websocket khỏi topic mapping
  - Xóa reverse mapping
  - Cleanup empty topics
- **Output**: None

### WebSocketManager.close_websocket() (input, process, output)
- **Input**: `websocket: WebSocket`
- **Process**: Đóng WebSocket connection, gọi disconnect()
- **Output**: None

### WebSocketManager.stream_data() (input, process, output)
- **Input**: `sysname: str, topic: str, data: dict`
- **Process**: 
  - Lấy tất cả websockets subscribe vào sysname:topic
  - Gửi JSON message đến tất cả websockets
  - Cleanup disconnected websockets
- **Output**: None

### WebSocketManager.get_active_topics() (input, process, output)
- **Input**: `sysname: str`
- **Process**: Lấy danh sách topics có websockets cho sysname
- **Output**: `List[str]` active topics

### WebSocketManager.has_subscribers() (input, process, output)
- **Input**: `sysname: str, topic: str`
- **Process**: Kiểm tra có websockets nào subscribe vào sysname:topic không
- **Output**: `bool`

---

## 12. Configuration (config.py)

### load_dotenv() và các biến config
- **Input**: Environment variables từ .env file
- **Process**: Load và parse environment variables với default values
- **Output**: Config variables (DB_HOST, DB_PORT, API_HOST, API_PORT, NOTIFY_PORT, etc.)

---

## App Flow Summary

### Startup Flow:
1. `app.py` tạo Flask app + Socket.IO (`SocketIO(app, path="query-socket.io")`).
2. Gắn `ws_manager.sio` và đăng ký HTTP Blueprint `api_bp` ở `/api`.
3. Trong `__main__`, khởi động `UDPNotificationListener` với callback `on_new_data`.
4. Chạy `socketio.run(app, host=API_HOST, port=API_PORT)`.

### Request Flow (HTTP):
1. Client gửi HTTP request tới `/api/dashboard/<sysname>` hoặc `/api/dashboard/<sysname>/<topic>`.
2. Blueprint `api_bp` render template tương ứng (`dashboard.html`, `cpu.html`, ...).
3. Template load xong, frontend JS (`dashboard.js`) khởi tạo `WebSocketManager` và kết nối Socket.IO.

### WebSocket / Socket.IO Flow:
1. Frontend gọi `io({ path: "/query-socket.io" })` → Socket.IO connect tới backend.
2. Server nhận event `connect` → log sid.
3. Frontend emit `subscribe { sysname, topic }` → server gọi `ws_manager.connect(sid, sysname, topic)` và gửi dữ liệu ban đầu bằng `get_topic_data()`.
4. Frontend có thể emit `paginate` (cho `diskio`) → server gọi lại `get_topic_data()` với `page`, `per_page` và gửi event `"data"`.
5. Khi client disconnect, event `disconnect` gọi `ws_manager.disconnect(sid)` để cleanup.

### Real-time Data Flow (UDP → Socket.IO):
1. Raspberry Pi (collector) gửi UDP `{"event": "new_data", "sysname": ..., "metric_count": ..., "timestamp": ...}` tới port `NOTIFY_PORT`.
2. `UDPNotificationListener._listen()` nhận packet, parse JSON và gọi `on_new_data(message)`.
3. `on_new_data()` lấy danh sách topic đang active qua `ws_manager.get_active_topics(sysname)` và cho từng topic gọi `stream_topic_data()`.
4. `stream_topic_data()` dùng `get_topic_data()` để truy vấn DB và gọi `ws_manager.stream_data(sysname, topic, data)`.
5. `ws_manager.stream_data()` emit event `"data"` tới tất cả Socket.IO clients đang subscribe vào `sysname:topic`.

### Database Query Flow:
1. Bất kỳ luồng nào cần dữ liệu (HTTP render, subscribe initial, paginate, UDP push) gọi `get_topic_data()` trong `services/topic_service.py`.
2. Hàm query tương ứng trong `db/queries.py` chạy SQL, dùng `utils/serialize` để chuẩn hóa datetime.
3. Trả về dict dữ liệu metrics cho HTTP/Socket.IO để render hoặc gửi xuống client.

---

## 13. Changelog

- **2025-11-17**: Loại bỏ middleware `add_keep_alive_header` để đơn giản hóa pipeline HTTP; keep-alive hiện dựa hoàn toàn vào cấu hình mặc định của FastAPI/Uvicorn.
- **2025-11-17**: Gỡ cấu hình `timeout_keep_alive` và `timeout_graceful_shutdown` tại main entry point để quay lại thiết lập mặc định của Uvicorn.

---

MY NOTE
Hiện tại code không dùng “room” của Socket.IO theo nghĩa built‑in, mà tự quản lý “room logic” trong WebSocketManager:

Mỗi cặp sysname:topic đang có client subscribe tương ứng với 1 “room logic” (1 key trong topic_websockets).


