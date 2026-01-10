"""
UDP Listener for receiving metrics from the rasberrypi collector.
Replaces: query-service/notifications/udp_listener.py

This runs as a background task inside the ASGI process (started in asgi.py).
It shares the same process as WebSocket consumers, allowing InMemoryChannelLayer to work.

Architecture Notes:
- Uses AsyncIO DatagramProtocol for non-blocking UDP reception
- Transforms raw metrics using RealTimeTransformer (stateful for rate calculation)
- Broadcasts transformed data to topic-specific Channel Layer groups
- NO database writes here - pure UDP -> WebSocket streaming
"""
import asyncio
import json
import logging
from typing import Optional, Set

from django.conf import settings
from channels.layers import get_channel_layer

from .data_transformer import get_transformer

logger = logging.getLogger(__name__)


class UDPProtocol(asyncio.DatagramProtocol):
    """
    AsyncIO UDP Protocol for receiving metric packets.
    
    Lifecycle:
    1. connection_made() - Called when transport is ready
    2. datagram_received() - Called for each UDP packet (non-blocking)
    3. error_received() - Called on socket errors (optional)
    4. connection_lost() - Called when transport is closed
    """
    
    # Topics that we transform and broadcast
    SUPPORTED_TOPICS = ('systemstatus', 'network', 'disk', 'diskio')
    
    def __init__(self):
        self.channel_layer = get_channel_layer()
        self.transformer = get_transformer()
        self.transport: Optional[asyncio.DatagramTransport] = None
        self._active_groups: Set[str] = set()  # Track which groups have been used
    
    def connection_made(self, transport: asyncio.DatagramTransport):
        """Called when the UDP socket is ready."""
        self.transport = transport
        logger.info(f"UDP Listener started on {settings.UDP_LISTEN_HOST}:{settings.UDP_LISTEN_PORT}")
    
    def connection_lost(self, exc: Optional[Exception]):
        """Called when the UDP socket is closed."""
        if exc:
            logger.error(f"UDP connection lost with error: {exc}")
        else:
            logger.info("UDP Listener stopped")
    
    def error_received(self, exc: Exception):
        """Called when a socket error occurs (non-fatal)."""
        logger.warning(f"UDP socket error (non-fatal): {exc}")
    
    def datagram_received(self, data: bytes, addr: tuple):
        """
        Called when a UDP packet is received. MUST NOT BLOCK.
        
        Expected format from rasberrypi collector:
        {
            "event": "new_data",
            "sysname": "raspi-pbl",
            "metric_count": 42,
            "timestamp": 1234567890.123,
            "ip_address": "192.168.1.100",
            "metrics": [
                {"name": "cpu.core.percent", "value": 42.5, "labels": {...}, "ts": 1234567890.123},
                ...
            ]
        }
        """
        try:
            message = json.loads(data.decode('utf-8'))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in UDP packet from {addr}: {e}")
            return
        except UnicodeDecodeError as e:
            logger.error(f"Invalid UTF-8 in UDP packet from {addr}: {e}")
            return
        
        # Validate message
        if message.get('event') != 'new_data':
            logger.warning(f"Ignoring UDP packet with event={message.get('event')}")
            return
        
        sysname = message.get('sysname')
        if not sysname:
            logger.warning("Missing sysname in UDP packet, dropping")
            return
        
        metrics = message.get('metrics', [])
        ip_address = message.get('ip_address')
        metric_count = message.get('metric_count', len(metrics))
        
        logger.debug(f"UDP from {addr}: sysname={sysname}, metrics={metric_count}")
        
        # Fire-and-forget: schedule the broadcast as a task
        # This ensures datagram_received returns immediately
        asyncio.create_task(
            self._broadcast_to_subscribers(sysname, metrics, ip_address)
        )
    
    async def _broadcast_to_subscribers(
        self,
        sysname: str,
        metrics: list,
        ip_address: Optional[str] = None
    ):
        """
        Transform raw metrics and broadcast to WebSocket subscribers.
        
        This method:
        1. Transforms metrics for each topic using RealTimeTransformer
        2. Broadcasts transformed data to topic-specific channel groups
        3. Matches Flask-SocketIO message format exactly for frontend compatibility
        
        Message format sent to consumers:
        {
            "type": "metrics.update",  # Maps to metrics_update() handler
            "sysname": "raspi-pbl",
            "topic": "systemstatus",
            "data": {...transformed data...}
        }
        """
        if not metrics:
            logger.debug(f"No metrics to broadcast for {sysname}")
            return
        
        for topic in self.SUPPORTED_TOPICS:
            group_name = f"metrics_{sysname}_{topic}"
            
            try:
                # Transform metrics for this topic
                # The transformer maintains state for rate calculations
                transformed_data = self.transformer.transform(
                    topic=topic,
                    metrics=metrics,
                    sysname=sysname,
                    ip_address=ip_address
                )
                
                if not transformed_data:
                    logger.debug(f"No transformed data for {topic}")
                    continue
                
                # Broadcast to channel layer group
                # NOTE: group_send is a no-op if no consumers in the group
                await self.channel_layer.group_send(
                    group_name,
                    {
                        "type": "metrics.update",  # Maps to metrics_update() in consumer
                        "sysname": sysname,
                        "topic": topic,
                        "data": transformed_data,
                    }
                )
                
                logger.debug(f"Broadcast {topic} to {group_name}")
                
            except Exception as e:
                # Log but don't crash - UDP listener must stay up
                logger.error(f"Error broadcasting {topic} to {group_name}: {e}", exc_info=True)


async def start_udp_listener():
    """
    Start the UDP listener as an asyncio task.
    Called from asgi.py during application startup.
    """
    loop = asyncio.get_event_loop()
    
    host = settings.UDP_LISTEN_HOST
    port = settings.UDP_LISTEN_PORT
    
    print(f"DEBUG: Attempting to start UDP Listener on {host}:{port}")
    logger.info(f"Starting UDP listener on {host}:{port}")
    
    try:
        transport, protocol = await loop.create_datagram_endpoint(
            lambda: UDPProtocol(),
            local_addr=(host, port)
        )
        print(f"DEBUG: UDP Listener STARTED successfully on {host}:{port}")
        
        # Keep the listener running forever
        try:
            await asyncio.Event().wait()  # Block forever
        finally:
            transport.close()
    except Exception as e:
        print(f"DEBUG: CRITICAL ERROR - UDP Listener failed to start: {e}")
        logger.error(f"UDP Listener failed: {e}")


def start_udp_listener_thread():
    """
    Bridge to run the async UDP listener from a synchronous thread.
    Used by apps.py ready() hook.
    """
    import asyncio
    
    # Create a new event loop for this thread
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    loop.run_until_complete(start_udp_listener())
