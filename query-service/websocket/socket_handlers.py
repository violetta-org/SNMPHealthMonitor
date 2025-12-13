import time
from flask import request


def register_socketio_events(socketio, ws_manager, get_topic_data):
    """
    Đăng ký tất cả Socket.IO event handlers cho query-service.

    socketio: Flask-SocketIO instance
    ws_manager: WebSocketManager instance
    get_topic_data: function để lấy dữ liệu metrics theo topic
    """

    @socketio.on("connect")
    def handle_connect():
        sid = request.sid
        print(f"[SocketIO] Client connected, sid={sid}")

    @socketio.on("disconnect")
    def handle_disconnect():
        sid = request.sid
        print(f"[SocketIO] Client disconnected, sid={sid}")
        ws_manager.disconnect(sid)

    @socketio.on("subscribe")
    def handle_subscribe(data):
        """
        Client yêu cầu subscribe vào một sysname/topic.
        data: { 'sysname': str, 'topic': str }
        """
        sid = request.sid
        sysname = data.get("sysname")
        topic = data.get("topic") or "systemstatus"

        print(f"[SocketIO] Subscribe requested: sid={sid}, sysname={sysname}, topic={topic}")

        if not sysname:
            print(f"[SocketIO] Missing sysname in subscribe payload: {data}")
            return

        # Đăng ký client vào topic
        ws_manager.connect(sid, sysname, topic)

        # Gửi dữ liệu ban đầu cho client vừa subscribe
        try:
            payload = get_topic_data(sysname, topic)
            socketio.emit(
                "data",
                {
                    "type": "data",
                    "topic": topic,
                    "sysname": sysname,
                    "data": payload,
                },
                to=sid,
            )
            print(f"[SocketIO] Sent initial {topic} data to sid={sid}")
        except Exception as e:
            print(
                f"[SocketIO] Error sending initial data for {sysname}/{topic} "
                f"to sid={sid}: {e}"
            )

    @socketio.on("ping")
    def handle_ping(data=None):
        """Đơn giản trả về pong để giữ kết nối."""
        sid = request.sid
        print(f"[SocketIO] Ping from sid={sid}, data={data}")
        socketio.emit("pong", {"ts": time.time()}, to=sid)

    @socketio.on("paginate")
    def handle_paginate(data):
        """
        Xử lý pagination cho diskio:
        data: { 'sysname': str, 'topic': 'diskio', 'page': int, 'per_page': int }
        """
        sid = request.sid
        sysname = data.get("sysname")
        topic = data.get("topic", "diskio")
        page = int(data.get("page", 1))
        per_page = int(data.get("per_page", 10))

        print(
            f"[SocketIO] Paginate requested: sid={sid}, sysname={sysname}, "
            f"topic={topic}, page={page}, per_page={per_page}"
        )

        if not sysname:
            print(f"[SocketIO] Missing sysname in paginate payload: {data}")
            return

        if topic != "diskio":
            print(f"[SocketIO] Pagination only supported for diskio topic, got {topic}")
            return

        try:
            payload = get_topic_data(sysname, topic, page=page, per_page=per_page)
            socketio.emit(
                "data",
                {
                    "type": "data",
                    "topic": topic,
                    "sysname": sysname,
                    "data": payload,
                },
                to=sid,
            )
            print(f"[SocketIO] Sent paginated {topic} data to sid={sid}")
        except Exception as e:
            print(
                f"[SocketIO] Error sending paginated data for {sysname}/{topic} "
                f"to sid={sid}: {e}"
            )


