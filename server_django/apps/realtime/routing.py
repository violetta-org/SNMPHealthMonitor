"""
WebSocket URL routing for Django Channels.
"""
from django.urls import re_path
from . import consumers
from . import consumers_remote

websocket_urlpatterns = [
    # Main metrics WebSocket endpoint
    # Matches: ws://localhost:8000/ws/metrics/
    re_path(r'ws/metrics/$', consumers.MetricsConsumer.as_asgi()),
    
    # Device-specific endpoint (alternative)
    # Matches: ws://localhost:8000/ws/metrics/<sysname>/
    re_path(r'ws/metrics/(?P<sysname>\w+)/$', consumers.MetricsConsumer.as_asgi()),

    # WebSSH and remote system management endpoints
    re_path(r'ws/terminal/$', consumers_remote.TerminalConsumer.as_asgi()),
    re_path(r'ws/system/$', consumers_remote.SystemConsumer.as_asgi()),
]
