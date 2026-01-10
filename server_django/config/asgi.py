"""
ASGI config for SNMPHealthMonitor Django project.

This is the main entry point for Daphne.
It also starts the UDP listener as a background task.
"""
import os
import asyncio

# PyMySQL monkey-patch (before Django imports)
import pymysql
pymysql.install_as_MySQLdb()

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack

# Initialize Django ASGI application early to ensure AppRegistry is populated
django_asgi_app = get_asgi_application()

# Import WebSocket routing (must be after Django setup)
from apps.realtime.routing import websocket_urlpatterns
from apps.realtime.udp_listener import start_udp_listener

# Flag to ensure UDP listener starts only once
_udp_started = False


class LifespanManager:
    """
    Manages ASGI lifespan events to start background tasks.
    This ensures the UDP listener runs in the same process as WebSockets.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        global _udp_started
        # print(f"DEBUG: ASGI Scope type: {scope['type']}") # UNCOMMENT TO DEBUG SCOPES
        
        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    # Start UDP listener as background task
                    if not _udp_started:
                        print("DEBUG: Lifespan Startup detected - Launching UDP Listener")
                        asyncio.create_task(start_udp_listener())
                        _udp_started = True
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        else:
            await self.app(scope, receive, send)


# Main ASGI application with Protocol routing
application = LifespanManager(
    ProtocolTypeRouter({
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(
            URLRouter(websocket_urlpatterns)
        ),
    })
)
