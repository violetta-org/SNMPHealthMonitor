import time
from typing import Set, Dict, List
from utils.logging import configure_logger

class WebSocketManager:
    def __init__(self):
        # Flask-SocketIO instance sẽ được gán từ app.py
        self.sio = None
        # Mapping: topic_key (sysname:topic) -> set of Socket.IO session ids (sid)
        self.topic_websockets: Dict[str, Set[str]] = {}
        # Reverse mapping: sid -> topic_key
        self.websocket_topic: Dict[str, str] = {}
        self.logger = configure_logger(__name__)

    def connect(self, sid: str, sysname: str, topic: str):
        """
        Kết nối một Socket.IO client (sid) và subscribe vào topic cụ thể.
        Topic được xác định ngay khi client gửi subscribe.
        """
        topic_key = f"{sysname}:{topic}"

        if topic_key not in self.topic_websockets:
            self.topic_websockets[topic_key] = set()
        self.topic_websockets[topic_key].add(sid)

        self.websocket_topic[sid] = topic_key

        self.logger.info(f"Client connected to {topic_key} (sid={sid})")

    def disconnect(self, sid: str):
        """Ngắt kết nối Socket.IO client và cleanup tất cả references."""
        topic_key = self.websocket_topic.get(sid)

        if topic_key:
            if topic_key in self.topic_websockets:
                self.topic_websockets[topic_key].discard(sid)
                if not self.topic_websockets[topic_key]:
                    del self.topic_websockets[topic_key]

            del self.websocket_topic[sid]

            self.logger.info(f"Client disconnected from {topic_key} (sid={sid})")
        else:
            self.logger.warning(f"Client disconnected (topic not found, sid={sid})")

    def stream_data(self, sysname: str, topic: str, data: dict):
        """
        Gửi dữ liệu đến tất cả clients đã subscribe vào sysname:topic này.
        Đây là hàm duy nhất để gửi dữ liệu cho clients.
        Chỉ gửi nếu có clients đang subscribe vào topic này.
        """
        topic_key = f"{sysname}:{topic}"

        subscribed_websockets = self.topic_websockets.get(topic_key, set())

        if not subscribed_websockets:
            self.logger.debug(f"No websockets for {topic_key}, skipping data stream")
            return

        message = {
            "type": "data",
            "topic": topic,
            "sysname": sysname,
            "data": data,
        }

        self.logger.debug(
            f"Streaming {topic} data to "
            f"{len(subscribed_websockets)} client(s) for {topic_key}"
        )

        if self.sio is None:
            self.logger.error("Socket.IO server not attached, cannot stream data")
            return

        # Emit đến từng client; Flask-SocketIO emit là thread-safe
        for sid in list(subscribed_websockets):
            try:
                self.sio.emit("data", message, to=sid)
                self.logger.debug(f"Successfully emitted {topic} data to sid={sid}")
            except Exception as e:
                self.logger.error(f"Error emitting data to sid={sid}: {e}")

    def get_active_topics(self, sysname: str) -> List[str]:
        """
        Lấy danh sách các topics đang có websockets cho một sysname.
        Helper method để query thông tin subscriptions.
        """
        active_topics: List[str] = []
        for topic_key in self.topic_websockets.keys():
            if topic_key.startswith(f"{sysname}:"):
                topic_name = topic_key.split(":", 1)[1]
                if topic_name not in active_topics:
                    active_topics.append(topic_name)
        self.logger.debug(f"Active topics for {sysname}: {active_topics}")
        return active_topics


ws_manager = WebSocketManager()
