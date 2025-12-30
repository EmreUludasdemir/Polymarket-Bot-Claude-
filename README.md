# Polymarket Trading Bot

Production-ready automated trading bot for Polymarket prediction markets, optimized for $500 starting capital.

## Features

- **Multi-Strategy Trading**
  - YES+NO Arbitrage: Risk-free profit when YES + NO < $1.00
  - Crypto Price Prediction: BTC/ETH up/down markets using technical analysis

- **Risk Management**
  - Kelly Criterion position sizing (quarter-Kelly)
  - Daily loss limits (5% = $25)
  - Maximum drawdown protection (20% = $100)
  - Consecutive loss circuit breakers
  - Position-level stop-losses

- **Production Ready**
  - Paper trading mode for testing
  - SQLite database for trade logging
  - Docker support for VPS deployment
  - Comprehensive logging

## Quick Start

### 1. Clone and Setup

```bash
# Clone repository
git clone <repo-url>
cd polymarket-bot

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit with your credentials
nano .env
```

Required settings:
- `PRIVATE_KEY`: Your Ethereum wallet private key
- `PROXY_WALLET_ADDRESS`: Your Polymarket profile address
- `SIGNATURE_TYPE`: Usually `1` for email login

### 3. Run the Bot

```bash
# Paper trading (recommended first)
python main.py --paper

# Live trading
python main.py

# Debug mode
python main.py --debug
```

## Configuration

### Trading Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `INITIAL_CAPITAL` | 500 | Starting capital in USDC |
| `RISK_PER_TRADE` | 0.02 | 2% risk per trade |
| `MAX_DAILY_LOSS` | 0.05 | 5% max daily loss |
| `MAX_DRAWDOWN` | 0.20 | 20% max drawdown |
| `MIN_EDGE_THRESHOLD` | 0.03 | 3% minimum edge to trade |
| `KELLY_FRACTION` | 0.25 | Quarter-Kelly sizing |

### Strategies

#### Arbitrage Strategy
- Monitors YES + NO price spreads
- Executes when spread > 0.5%
- Uses up to 50% of capital (low risk)

#### Crypto Price Strategy
- Trades BTC/ETH up/down markets
- Uses RSI + momentum indicators
- Quarter-Kelly position sizing

## Docker Deployment

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f

# Paper trading
docker-compose --profile paper up -d
```

## Project Structure

```
polymarket-bot/
├── config/           # Configuration management
├── core/             # API client, auth, websocket
├── strategies/       # Trading strategies
├── risk/             # Risk management
├── data/             # Market data handling
├── database/         # SQLite models
├── utils/            # Helper utilities
├── tests/            # Unit tests
├── main.py           # Entry point
├── Dockerfile
└── docker-compose.yml
```

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=.

# Run specific test file
pytest tests/test_position_sizing.py -v
```

## Risk Warning

⚠️ **IMPORTANT**:
- Trading involves risk of financial loss
- Start with paper trading mode
- Never invest more than you can afford to lose
- This bot is for educational purposes

## License

MIT License - See LICENSE file for details.
