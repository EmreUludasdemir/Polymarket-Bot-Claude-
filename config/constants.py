"""
Polymarket Bot Constants
Fixed values, contract addresses, and configuration constants
"""

# Polymarket Contract Addresses (Polygon Mainnet)
CONDITIONAL_TOKEN_ADDRESS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
CTF_EXCHANGE_ADDRESS = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_CTF_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

# API Endpoints
CLOB_API_HOST = "https://clob.polymarket.com"
GAMMA_API_HOST = "https://gamma-api.polymarket.com"
WS_MARKET_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
WS_USER_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/user"

# Polygon Network
POLYGON_CHAIN_ID = 137
POLYGON_RPC_URLS = [
    "https://polygon-rpc.com",
    "https://rpc-mainnet.matic.network",
    "https://rpc-mainnet.maticvigil.com",
]

# Trading Limits
MIN_ORDER_SIZE = 1.0  # Minimum $1 USDC
MAX_ORDER_SIZE = 10000.0  # Maximum $10k USDC per order
MIN_PRICE = 0.01  # Minimum price 1 cent
MAX_PRICE = 0.99  # Maximum price 99 cents
PRICE_TICK = 0.01  # Price increment

# Rate Limits (Polymarket CLOB)
MAX_ORDERS_PER_10S = 2400
MAX_REQUESTS_PER_SECOND = 100

# Risk Management Defaults
DEFAULT_RISK_PER_TRADE = 0.02  # 2% risk per trade
DEFAULT_MAX_DAILY_LOSS = 0.05  # 5% max daily loss
DEFAULT_MAX_DRAWDOWN = 0.20  # 20% max drawdown
DEFAULT_KELLY_FRACTION = 0.25  # Quarter Kelly

# Strategy-specific Constants
CRYPTO_MARKET_KEYWORDS = [
    "bitcoin", "btc", "ethereum", "eth",
    "price", "above", "below", "reach"
]

ESPORTS_MARKET_KEYWORDS = [
    "league of legends", "lol", "dota",
    "csgo", "counter-strike", "valorant"
]

# Time Constants (seconds)
POLL_INTERVAL_DEFAULT = 2
WS_HEARTBEAT_INTERVAL = 30
WS_RECONNECT_DELAY = 5
ORDER_TIMEOUT = 30

# Logging
LOG_FORMAT = "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
LOG_ROTATION = "1 day"
LOG_RETENTION = "30 days"
