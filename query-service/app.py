from flask import Flask
from flask_socketio import SocketIO
from config import API_HOST, API_PORT
from notifications.udp_listener import UDPNotificationListener
from websocket.websocket_manager import ws_manager
from websocket.socket_handlers import register_socketio_events
from services.topic_service import get_topic_data, stream_topic_data
from api.router import api_bp
from web.router import web_bp

from utils.data_transformer import RealTimeTransformer

# UDP notification callback
def on_new_data(message: dict):
    """When new data arrives, stream it to all subscribed clients."""
    event = message.get('event')
    if event != 'new_data':
        print(f"[QueryService] Invalid event: {event}")
        return
    
    sysname = message.get('sysname')
    metrics = message.get('metrics')
    metric_count = message.get('metric_count', 0)
    ip_address = message.get('ip_address')
    
    if not sysname:
        print(f"[QueryService] Invalid notification message: missing sysname")
        return
    
    print(f"[QueryService] New data notification for {sysname}, metric_count: {metric_count}, has_metrics: {bool(metrics)}")
    
    # Check which topics have active subscriptions
    try:
        active_topics = ws_manager.get_active_topics(sysname)

        # Only stream to topics that have subscribers
        for topic in active_topics:
            # OPTIMIZATION: Use metrics list directly if available to avoid DB query
            if metrics and topic in ['systemstatus', 'network', 'disk', 'diskio']:
                try:
                    # print(f"[QueryService] Transforming metrics for {topic}")
                    extra_context = {'ip_address': ip_address} if ip_address else {}
                    transformed_data = RealTimeTransformer.transform(topic, metrics, extra_context)
                    if transformed_data:
                        ws_manager.stream_data(sysname, topic, transformed_data)
                        continue # Skip DB query
                except Exception as e:
                    print(f"[QueryService] Error transforming metrics for {topic}: {e}")
                    # If transform fails, fallback to DB query below
            
            # Fallback / Legacy: Query DB
            # Only run this if we didn't stream data via UDP transformation above
            print(f"[QueryService] Streaming {topic} to subscribers (DB Query)")
            stream_topic_data(sysname, topic)
    except Exception as e:
        print(f"[QueryService] Error scheduling streaming tasks: {e}")


# Flask app & Socket.IO setup
from datetime import timedelta
app = Flask(__name__, static_folder="static", template_folder="templates")
app.config['DEBUG'] = True
app.config['SECRET_KEY'] = 'dev_secret_key_change_in_prod'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)


# Absolute Path for Database
import os
basedir = os.path.abspath(os.path.dirname(__file__))
instance_path = os.path.join(basedir, 'instance')
if not os.path.exists(instance_path):
    os.makedirs(instance_path)

db_path = os.path.join(instance_path, 'site.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize Extensions
from extensions import limiter, db, socketio
limiter.init_app(app)
db.init_app(app)
socketio.init_app(app) 

# Create DB Tables if not exist
with app.app_context():
    from db.models import User
    db.create_all()
    # Optional: Create default admin if not exists
    if not User.query.filter_by(username='admin').first():
        print("Creating default admin user...")
        u = User(username='admin')
        u.set_password('admin')
        db.session.add(u)
        db.session.commit()


# Gán server cho WebSocketManager để nó có thể emit
ws_manager.sio = socketio

# Đăng ký Blueprint cho HTTP API
app.register_blueprint(api_bp)
app.register_blueprint(web_bp)

# Đăng ký Socket.IO event handlers
# Clients for Terminal Service (managed in main app scope)
clients = {}

# Đăng ký Socket.IO event handlers
register_socketio_events(socketio, ws_manager, get_topic_data, clients)

import os

# When debug=True, the reloader spawns a child process.
# We want to avoid starting the UDP listener in the main process (reloader parent)
# because the child process will also try to bind the same port, causing "Address already in use".
# debug_mode = True

# Check if we are in the reloader process (WERKZEUG_RUN_MAIN is set in the child)
# If debug is False, WERKZEUG_RUN_MAIN is never set, so we assume valid to start.
# If debug is True, we only start if we are in the child process (WERKZEUG_RUN_MAIN == 'true').
# is_reloader_child = os.environ.get("WERKZEUG_RUN_MAIN") == "true"

# should_start = True
# if debug_mode and not is_reloader_child:
#     should_start = False
#     print("[Main] Reloader parent: Skipping UDP listener start to avoid port conflict")

notify_listener = None
# if should_start:
print("[Main] Starting UDP Listener")
notify_listener = UDPNotificationListener(callback=on_new_data)
notify_listener.start()

try:
    socketio.run(app, host=API_HOST, port=API_PORT, debug=False)
finally:
    if notify_listener:
        notify_listener.stop()
    print("[Main] Flask app shutdown")