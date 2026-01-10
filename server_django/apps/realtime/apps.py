from django.apps import AppConfig
import threading
import logging
import os

logger = logging.getLogger(__name__)

class RealtimeConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.realtime'
    verbose_name = 'Realtime Streaming'

    def ready(self):
        print("DEBUG: RealtimeConfig.ready() called") # DEBUG PROBE
        
        # Start always for now to debug - we can refine logic later if it runs twice
        from .udp_listener import start_udp_listener_thread
        
        logger.info("Initializing UDP Listener Thread via AppConfig...")
        print("DEBUG: Launching UDP thread...")
        t = threading.Thread(target=start_udp_listener_thread, daemon=True)
        t.start()
