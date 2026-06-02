from django.apps import AppConfig
import threading
import logging

logger = logging.getLogger(__name__)

class RealtimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.realtime'
    verbose_name = 'Realtime Streaming'

    def ready(self):
        print("DEBUG: RealtimeConfig.ready() called") # DEBUG PROBE
        
        # Removed UDP thread startup from here because it is now handled by asgi.py (LifespanManager)
        # to ensure it runs in the same asyncio loop as WebSockets and doesn't run twice.
        # logger.info("Initializing UDP Listener Thread via AppConfig...")
        # print("DEBUG: Launching UDP thread...")
        # t = threading.Thread(target=start_udp_listener_thread, daemon=True)
        # t.start()
