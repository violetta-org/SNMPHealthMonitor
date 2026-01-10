"""
WebSocket Consumers for real-time metric streaming.
Replaces: query-service/websocket/socket_handlers.py

Protocol Compatibility:
- MUST match Flask-SocketIO event names for frontend compatibility
- Client sends: subscribe/unsubscribe actions via JSON
- Server sends: 'data' events with topic and transformed metrics

Message Formats:
- Flask-SocketIO used: socketio.emit("data", message, to=sid)
- Django Channels uses: self.send_json({...})
- Both produce identical JSON for the frontend
"""
import logging
from typing import Set

from channels.generic.websocket import AsyncJsonWebsocketConsumer

logger = logging.getLogger(__name__)


class MetricsConsumer(AsyncJsonWebsocketConsumer):
    """
    Handles WebSocket connections for real-time metric updates.
    
    Protocol (MUST match Flask-SocketIO for frontend compatibility):
    
    Client -> Server:
        Subscribe:   {"action": "subscribe", "sysname": "raspi-pbl", "topic": "systemstatus"}
        Unsubscribe: {"action": "unsubscribe", "sysname": "raspi-pbl", "topic": "systemstatus"}
    
    Server -> Client (matches Flask ws_manager.stream_data format):
        {
            "type": "data",
            "topic": "systemstatus",
            "sysname": "raspi-pbl",
            "data": {
                "system_info": {...},
                "load_avg": {...},
                "cpu_percent": [...],
                "memory": {...},
                "swap": {...},
                "network": [...],
                "device_info": {"online": true, "last_seen": "..."}
            }
        }
    
    Note: Flask-SocketIO emits "data" event. In Django Channels, we send JSON
    with {"type": "data", ...} to maintain the same structure the frontend expects.
    """
    
    async def connect(self):
        """Handle new WebSocket connection."""
        self.subscriptions: Set[str] = set()  # Track subscribed groups
        
        # Optional: sysname from URL route (if using /ws/metrics/<sysname>/)
        self.sysname = self.scope['url_route']['kwargs'].get('sysname')
        
        await self.accept()
        logger.info(f"WebSocket connected: {self.channel_name}")
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection - leave all groups."""
        for group_name in list(self.subscriptions):
            try:
                await self.channel_layer.group_discard(group_name, self.channel_name)
            except Exception as e:
                logger.error(f"Error leaving group {group_name}: {e}")
        
        self.subscriptions.clear()
        logger.info(f"WebSocket disconnected: {self.channel_name} (code={close_code})")
    
    async def receive_json(self, content: dict):
        """
        Handle incoming JSON messages from client.
        
        Actions:
        - subscribe: Join a channel group for a specific sysname:topic
        - unsubscribe: Leave a channel group
        """
        action = content.get('action')
        sysname = content.get('sysname') or self.sysname
        topic = content.get('topic')
        
        if not action:
            await self.send_json({"error": "Missing 'action' field"})
            return
        
        if action == 'subscribe':
            if not sysname or not topic:
                await self.send_json({
                    "error": "Missing 'sysname' or 'topic' for subscribe"
                })
                return
            
            group_name = f"metrics_{sysname}_{topic}"
            
            # Join the group
            await self.channel_layer.group_add(group_name, self.channel_name)
            self.subscriptions.add(group_name)
            
            logger.info(f"Subscribed {self.channel_name} to {group_name}")
            
            # Send confirmation (optional - Flask version doesn't do this)
            await self.send_json({
                "status": "subscribed",
                "sysname": sysname,
                "topic": topic
            })
        
        elif action == 'unsubscribe':
            if not sysname or not topic:
                await self.send_json({
                    "error": "Missing 'sysname' or 'topic' for unsubscribe"
                })
                return
            
            group_name = f"metrics_{sysname}_{topic}"
            
            # Leave the group
            await self.channel_layer.group_discard(group_name, self.channel_name)
            self.subscriptions.discard(group_name)
            
            logger.info(f"Unsubscribed {self.channel_name} from {group_name}")
            
            await self.send_json({
                "status": "unsubscribed",
                "sysname": sysname,
                "topic": topic
            })
        
        else:
            await self.send_json({"error": f"Unknown action: {action}"})
    
    async def metrics_update(self, event: dict):
        """
        Handler for 'metrics.update' messages from Channel Layer.
        
        Called when UDP listener broadcasts new data via:
            channel_layer.group_send(group_name, {"type": "metrics.update", ...})
        
        The 'type' field in group_send maps to method name:
            "metrics.update" -> metrics_update()
        
        Message format sent to client (MUST match Flask ws_manager.stream_data):
        {
            "type": "data",
            "topic": "systemstatus",
            "sysname": "raspi-pbl",
            "data": {...transformed metrics...}
        }
        """
        # Format message EXACTLY as Flask's ws_manager.stream_data() does
        await self.send_json({
            "type": "data",
            "topic": event.get("topic"),
            "sysname": event.get("sysname"),
            "data": event.get("data"),
        })
