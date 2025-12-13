from flask import Flask
from flask_socketio import SocketIO
import time
from typing import Optional

from config import API_HOST, API_PORT
from notifications.udp_listener import UDPNotificationListener
from websocket.websocket_manager import ws_manager
from websocket.socket_handlers import register_socketio_events
from services.topic_service import get_topic_data, stream_topic_data
from api.router import api_bp


# UDP notification callback
def on_new_data(message: dict):
    """When new data arrives, stream it to all subscribed clients."""
    event = message.get('event')
    if event != 'new_data':
        print(f"[QueryService] Invalid event: {event}")
        return
    
    sysname = message.get('sysname')
    metric_count = message.get('metric_count', 0)
    notify_timestamp = message.get('timestamp')
    
    if not sysname:
        print(f"[QueryService] Invalid notification message: missing sysname")
        return
    
    print(f"[QueryService] New data notification for {sysname}, metric_count: {metric_count}, notify_timestamp: {notify_timestamp}")
    
    # Check which topics have active subscriptions
    try:
        active_topics = ws_manager.get_active_topics(sysname)

        # Only stream to topics that have subscribers
        for topic in active_topics:
            print(f"[QueryService] Streaming {topic} to subscribers with notify_timestamp: {notify_timestamp}")
            stream_topic_data(sysname, topic, notify_timestamp=notify_timestamp)
    except Exception as e:
        print(f"[QueryService] Error scheduling streaming tasks: {e}")


# Flask app & Socket.IO setup
app = Flask(__name__, static_folder="static", template_folder="template")
app.config['DEBUG'] = True
socketio = SocketIO(app, path="query-socket.io")

# Gán server cho WebSocketManager để nó có thể emit
ws_manager.sio = socketio

# Đăng ký Blueprint cho HTTP API
app.register_blueprint(api_bp)

# Đăng ký Socket.IO event handlers
register_socketio_events(socketio, ws_manager, get_topic_data)


if __name__ == "__main__":
    print("[Main] Starting Flask + Socket.IO app")
    notify_listener = UDPNotificationListener(callback=on_new_data)
    notify_listener.start()
    try:
        socketio.run(app, host=API_HOST, port=API_PORT, debug=False)
    finally:
        notify_listener.stop()
        print("[Main] Flask app shutdown")
