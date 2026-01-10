from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO

# Initialize Extensions
# storage_uri="memory://" is default, but explicit here for clarity
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"], storage_uri="memory://")
db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

