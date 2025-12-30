"""
Notifications Module
Send alerts via Telegram or Discord (optional)
"""

from typing import Optional
from decimal import Decimal
import requests
from loguru import logger
from dataclasses import dataclass


@dataclass
class TradeAlert:
    """Trade notification data"""
    trade_type: str  # "entry", "exit", "stop_loss"
    market: str
    side: str
    size: Decimal
    price: Decimal
    pnl: Optional[Decimal] = None
    strategy: str = ""


@dataclass
class RiskAlert:
    """Risk notification data"""
    alert_type: str  # "drawdown", "daily_limit", "consecutive_losses"
    message: str
    current_value: Decimal
    limit_value: Decimal


class TelegramNotifier:
    """
    Send notifications via Telegram

    Setup:
    1. Create bot with @BotFather
    2. Get bot token
    3. Get your chat ID from @userinfobot
    """

    def __init__(self, bot_token: str, chat_id: str):
        """
        Initialize Telegram notifier

        Args:
            bot_token: Telegram bot token from BotFather
            chat_id: Your Telegram chat ID
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        self._enabled = bool(bot_token and chat_id)

    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """
        Send message to Telegram

        Args:
            message: Message text (supports HTML formatting)
            parse_mode: "HTML" or "Markdown"

        Returns:
            True if sent successfully
        """
        if not self._enabled:
            logger.debug("Telegram notifications disabled")
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }

            response = requests.post(url, json=data, timeout=10)
            response.raise_for_status()

            logger.debug("Telegram message sent")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False

    def send_trade_alert(self, alert: TradeAlert) -> bool:
        """Send trade alert"""
        emoji = "📈" if alert.side.upper() == "BUY" else "📉"
        pnl_text = f"\nPnL: ${alert.pnl:.2f}" if alert.pnl else ""

        message = f"""
{emoji} <b>Trade {alert.trade_type.upper()}</b>

Market: {alert.market[:50]}
Strategy: {alert.strategy}
Side: {alert.side}
Size: ${alert.size:.2f}
Price: {alert.price:.3f}{pnl_text}
"""
        return self.send_message(message.strip())

    def send_risk_alert(self, alert: RiskAlert) -> bool:
        """Send risk alert"""
        message = f"""
⚠️ <b>RISK ALERT: {alert.alert_type.upper()}</b>

{alert.message}
Current: {alert.current_value:.2%}
Limit: {alert.limit_value:.2%}
"""
        return self.send_message(message.strip())

    def send_daily_summary(
        self,
        pnl: Decimal,
        trades: int,
        win_rate: Decimal,
        balance: Decimal
    ) -> bool:
        """Send daily summary"""
        emoji = "🟢" if pnl >= 0 else "🔴"

        message = f"""
{emoji} <b>Daily Summary</b>

PnL: ${pnl:+.2f}
Trades: {trades}
Win Rate: {win_rate:.1%}
Balance: ${balance:.2f}
"""
        return self.send_message(message.strip())


class DiscordNotifier:
    """
    Send notifications via Discord webhook

    Setup:
    1. Create webhook in Discord channel settings
    2. Copy webhook URL
    """

    def __init__(self, webhook_url: str):
        """
        Initialize Discord notifier

        Args:
            webhook_url: Discord webhook URL
        """
        self.webhook_url = webhook_url
        self._enabled = bool(webhook_url)

    def send_message(
        self,
        content: str = "",
        embed_title: str = "",
        embed_description: str = "",
        embed_color: int = 0x5865F2
    ) -> bool:
        """
        Send message to Discord

        Args:
            content: Message content
            embed_title: Embed title
            embed_description: Embed description
            embed_color: Embed color (hex)

        Returns:
            True if sent successfully
        """
        if not self._enabled:
            logger.debug("Discord notifications disabled")
            return False

        try:
            data = {"content": content}

            if embed_title or embed_description:
                data["embeds"] = [{
                    "title": embed_title,
                    "description": embed_description,
                    "color": embed_color
                }]

            response = requests.post(
                self.webhook_url,
                json=data,
                timeout=10
            )
            response.raise_for_status()

            logger.debug("Discord message sent")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Discord message: {e}")
            return False

    def send_trade_alert(self, alert: TradeAlert) -> bool:
        """Send trade alert"""
        color = 0x00FF00 if alert.side.upper() == "BUY" else 0xFF0000
        pnl_text = f"\nPnL: ${alert.pnl:.2f}" if alert.pnl else ""

        description = f"""
**Market:** {alert.market[:50]}
**Strategy:** {alert.strategy}
**Side:** {alert.side}
**Size:** ${alert.size:.2f}
**Price:** {alert.price:.3f}{pnl_text}
"""
        return self.send_message(
            embed_title=f"Trade {alert.trade_type.upper()}",
            embed_description=description.strip(),
            embed_color=color
        )

    def send_risk_alert(self, alert: RiskAlert) -> bool:
        """Send risk alert"""
        description = f"""
{alert.message}
**Current:** {alert.current_value:.2%}
**Limit:** {alert.limit_value:.2%}
"""
        return self.send_message(
            embed_title=f"⚠️ RISK: {alert.alert_type.upper()}",
            embed_description=description.strip(),
            embed_color=0xFF6600
        )


class NotificationManager:
    """
    Unified notification manager

    Sends to all configured channels
    """

    def __init__(
        self,
        telegram_token: str = "",
        telegram_chat_id: str = "",
        discord_webhook: str = ""
    ):
        self.telegram = TelegramNotifier(telegram_token, telegram_chat_id)
        self.discord = DiscordNotifier(discord_webhook)

    def notify_trade(self, alert: TradeAlert):
        """Send trade notification to all channels"""
        self.telegram.send_trade_alert(alert)
        self.discord.send_trade_alert(alert)

    def notify_risk(self, alert: RiskAlert):
        """Send risk notification to all channels"""
        self.telegram.send_risk_alert(alert)
        self.discord.send_risk_alert(alert)

    def notify_message(self, message: str):
        """Send simple message to all channels"""
        self.telegram.send_message(message)
        self.discord.send_message(message)


# Placeholder for global notifier (configure in main.py)
notifier: Optional[NotificationManager] = None
