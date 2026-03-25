# XAUEUR AI Trading Bot

Autonomous AI-powered trading bot for XAUEUR (Gold/Euro) that connects to MetaTrader 5, analyzes the market using a trend-following strategy with Claude AI, and executes trades with user approval.

## Prerequisites

- **Windows** with MetaTrader 5 installed and logged in
- **Python 3.11+**
- **Node.js 18+**
- Anthropic API key (for Claude AI analysis)
- Finnhub API key (free tier, for economic calendar)

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

```bash
copy .env.example .env
```

Edit `.env` and add your API keys:
- `ANTHROPIC_API_KEY` - from console.anthropic.com
- `FINNHUB_API_KEY` - from finnhub.io (free)

### 3. Start the backend

```bash
python -m backend.main
```

The API server starts at `http://localhost:8000`.

### 4. Start the frontend

```bash
cd frontend
npm install
npm start
```

Opens at `http://localhost:3000`.

### 5. Configure in the UI

1. Enter MT5 account number, password, and server name
2. Enter API keys (or set them in `.env`)
3. Set risk per trade (default 2%)
4. Select lot size mode (default: Approval)
5. **Run a backtest first** to validate the strategy
6. Start the bot on a **demo account** first

## Architecture

- **Backend**: Python FastAPI with WebSocket for real-time updates
- **MT5 Connection**: Official MetaTrader5 Python package (single-threaded)
- **Indicators**: pandas-ta for EMA, RSI, ATR, Bollinger Bands
- **AI Analysis**: Claude claude-sonnet-4-20250514 called once per H1 candle close
- **Database**: SQLite for trade logging
- **Frontend**: React with dark theme, Recharts for equity curves

## Strategy (Phase 1)

- **Trend**: 4H EMA 50/200 crossover
- **Entry**: H1 pullback to EMA 50 with RSI confirmation
- **Stop-Loss**: 1.5x ATR from entry
- **Take-Profit**: 2.5x ATR, then trailing at 1x ATR from EMA 50
- **Filters**: Session (London/NY), news, cooldown, weekend

## Safety

- Max 5% risk across all positions
- 20% drawdown auto-stop
- 3 consecutive losses = 4-hour pause
- Every order must have a stop-loss
- 24h inactivity check
- Emergency Close All button always visible
