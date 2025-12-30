"""
WebSocket Manager
Handles real-time data streaming from Polymarket
"""

import asyncio
import json
from typing import Optional, Callable, Dict, List, Any
from dataclasses import dataclass
from enum import Enum
import websockets
from websockets.exceptions import ConnectionClosed
from loguru import logger

from config.constants import (
    WS_MARKET_URL,
    WS_USER_URL,
    WS_HEARTBEAT_INTERVAL,
    WS_RECONNECT_DELAY
)


class WSMessageType(Enum):
    """WebSocket message types"""
    PRICE_CHANGE = "price_change"
    BOOK_UPDATE = "book_update"
    TRADE = "trade"
    ORDER_UPDATE = "order_update"
    HEARTBEAT = "heartbeat"


@dataclass
class WSMessage:
    """Parsed WebSocket message"""
    type: WSMessageType
    market_id: str
    data: Dict[str, Any]
    timestamp: float


class WebSocketManager:
    """
    Manages WebSocket connections to Polymarket

    Features:
    - Automatic reconnection
    - Heartbeat management
    - Message parsing and routing
    - Multiple subscription support
    """

    def __init__(
        self,
        market_url: str = WS_MARKET_URL,
        user_url: str = WS_USER_URL
    ):
        self.market_url = market_url
        self.user_url = user_url

        self._market_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._user_ws: Optional[websockets.WebSocketClientProtocol] = None

        self._subscriptions: Dict[str, List[Callable]] = {}
        self._is_running = False
        self._reconnect_attempts = 0
        self._max_reconnect_attempts = 10

    async def connect_market(self) -> bool:
        """
        Connect to market data WebSocket

        Returns:
            True if connection successful
        """
        try:
            self._market_ws = await websockets.connect(
                self.market_url,
                ping_interval=WS_HEARTBEAT_INTERVAL,
                ping_timeout=10
            )
            logger.info("Connected to market WebSocket")
            self._reconnect_attempts = 0
            return True

        except Exception as e:
            logger.error(f"Failed to connect to market WebSocket: {e}")
            return False

    async def connect_user(self, api_key: str, api_secret: str) -> bool:
        """
        Connect to user data WebSocket (for order updates)

        Args:
            api_key: API key
            api_secret: API secret

        Returns:
            True if connection successful
        """
        try:
            # User WebSocket requires authentication
            headers = {
                "POLY_API_KEY": api_key,
                "POLY_SECRET": api_secret
            }

            self._user_ws = await websockets.connect(
                self.user_url,
                extra_headers=headers,
                ping_interval=WS_HEARTBEAT_INTERVAL,
                ping_timeout=10
            )
            logger.info("Connected to user WebSocket")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to user WebSocket: {e}")
            return False

    async def subscribe_market(self, market_id: str, token_ids: List[str]) -> bool:
        """
        Subscribe to market updates

        Args:
            market_id: Market identifier
            token_ids: List of token IDs to subscribe to

        Returns:
            True if subscription successful
        """
        if not self._market_ws:
            logger.error("Market WebSocket not connected")
            return False

        try:
            subscribe_msg = {
                "type": "subscribe",
                "channel": "market",
                "markets": token_ids
            }

            await self._market_ws.send(json.dumps(subscribe_msg))
            logger.info(f"Subscribed to market: {market_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to market {market_id}: {e}")
            return False

    async def unsubscribe_market(self, token_ids: List[str]) -> bool:
        """
        Unsubscribe from market updates

        Args:
            token_ids: Token IDs to unsubscribe from

        Returns:
            True if unsubscription successful
        """
        if not self._market_ws:
            return False

        try:
            unsubscribe_msg = {
                "type": "unsubscribe",
                "channel": "market",
                "markets": token_ids
            }

            await self._market_ws.send(json.dumps(unsubscribe_msg))
            logger.info(f"Unsubscribed from tokens: {token_ids}")
            return True

        except Exception as e:
            logger.error(f"Failed to unsubscribe: {e}")
            return False

    def add_handler(self, message_type: WSMessageType, handler: Callable):
        """
        Add a message handler for a specific message type

        Args:
            message_type: Type of message to handle
            handler: Callback function(message: WSMessage)
        """
        type_key = message_type.value
        if type_key not in self._subscriptions:
            self._subscriptions[type_key] = []
        self._subscriptions[type_key].append(handler)

    def remove_handler(self, message_type: WSMessageType, handler: Callable):
        """Remove a message handler"""
        type_key = message_type.value
        if type_key in self._subscriptions:
            self._subscriptions[type_key].remove(handler)

    async def _process_message(self, raw_message: str):
        """
        Process incoming WebSocket message

        Args:
            raw_message: Raw JSON message string
        """
        try:
            data = json.loads(raw_message)

            # Determine message type
            msg_type = data.get("type", "unknown")
            market_id = data.get("market", data.get("asset_id", ""))

            # Create WSMessage
            import time
            message = WSMessage(
                type=WSMessageType(msg_type) if msg_type in [t.value for t in WSMessageType] else WSMessageType.HEARTBEAT,
                market_id=market_id,
                data=data,
                timestamp=time.time()
            )

            # Route to handlers
            type_key = message.type.value
            if type_key in self._subscriptions:
                for handler in self._subscriptions[type_key]:
                    try:
                        await handler(message) if asyncio.iscoroutinefunction(handler) else handler(message)
                    except Exception as e:
                        logger.error(f"Handler error: {e}")

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"Error processing message: {e}")

    async def _listen_market(self):
        """Listen for market data messages"""
        while self._is_running and self._market_ws:
            try:
                message = await self._market_ws.recv()
                await self._process_message(message)

            except ConnectionClosed:
                logger.warning("Market WebSocket connection closed")
                if self._is_running:
                    await self._reconnect_market()
                break

            except Exception as e:
                logger.error(f"Error in market listener: {e}")
                await asyncio.sleep(1)

    async def _reconnect_market(self):
        """Attempt to reconnect to market WebSocket"""
        while self._reconnect_attempts < self._max_reconnect_attempts:
            self._reconnect_attempts += 1
            delay = min(WS_RECONNECT_DELAY * (2 ** self._reconnect_attempts), 60)

            logger.info(f"Reconnecting in {delay}s (attempt {self._reconnect_attempts})")
            await asyncio.sleep(delay)

            if await self.connect_market():
                # Re-subscribe to previous markets
                logger.info("Reconnected successfully")
                return

        logger.error("Max reconnection attempts reached")

    async def start(self):
        """Start WebSocket listeners"""
        self._is_running = True
        await self.connect_market()

        # Start listener task
        asyncio.create_task(self._listen_market())
        logger.info("WebSocket manager started")

    async def stop(self):
        """Stop WebSocket connections"""
        self._is_running = False

        if self._market_ws:
            await self._market_ws.close()
            self._market_ws = None

        if self._user_ws:
            await self._user_ws.close()
            self._user_ws = None

        logger.info("WebSocket manager stopped")

    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return (
            self._market_ws is not None
            and self._market_ws.open
        )
