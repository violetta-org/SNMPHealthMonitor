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
# Strong references to background tasks to prevent garbage collection
_background_tasks = set()


class LifespanManager:
    """
    Manages ASGI lifespan events to start background tasks.
    This ensures the UDP listener runs in the same process as WebSockets.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        global _udp_started
        # Log every ASGI scope to confirm lifespan events are received
        print(f"DEBUG: LifespanManager.__call__ scope={scope['type']}", flush=True)

        if scope['type'] == 'lifespan':
            while True:
                message = await receive()
                if message['type'] == 'lifespan.startup':
                    is_runserver = any('runserver' in arg for arg in os.sys.argv)
                    is_main_process = os.environ.get('RUN_MAIN') == 'true'

                    if not _udp_started and (not is_runserver or is_main_process):
                        print("DEBUG: Lifespan Startup - Launching UDP Listener", flush=True)
                        task = asyncio.create_task(start_udp_listener())
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
                        _udp_started = True
                    else:
                        print(f"DEBUG: Lifespan Startup skipped (is_runserver={is_runserver}, is_main={is_main_process}, started={_udp_started})", flush=True)
                    await send({'type': 'lifespan.startup.complete'})
                elif message['type'] == 'lifespan.shutdown':
                    await send({'type': 'lifespan.shutdown.complete'})
                    return
        else:
            # Fallback: start UDP listener on first real request if lifespan never fired
            if not _udp_started:
                print("DEBUG: Lifespan never fired! Starting UDP listener on first request", flush=True)
                task = asyncio.create_task(start_udp_listener())
                _background_tasks.add(task)
                task.add_done_callback(_background_tasks.discard)
                _udp_started = True
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
