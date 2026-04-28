"""Configuration management for the trading bot."""

import os
from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load .env from the project root (directory containing backend/).
# Using an explicit path + override=True ensures:
#   1. The correct .env is found regardless of the server's working directory.
#   2. Values in .env always win over any pre-existing OS environment variables.
_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=True)


class Settings(BaseSettings):
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")
    finnhub_api_key: str = Field(default="", env="FINNHUB_API_KEY")
    host: str = "0.0.0.0"
    port: int = 8000
    db_path: str = "trading_bot.db"


class BotConfig(BaseModel):
    """Runtime bot configuration, set via UI."""
    mt5_account: int = 0
    mt5_password: str = ""
    mt5_server: str = ""
    symbol: str = "XAUEUR"
    # PHASE 4 — REPLACED: risk_per_trade_pct: float = 5.0
    risk_per_trade_pct: float = 2.5  # Phase 5 — halved to reduce per-loss EUR cost
    # PHASE 5 — minimum lot floor: when risk-based calc would produce a very
    # small lot (broker min is usually 0.01), bump up to this floor so the
    # trade is meaningful. Setting this above the risk-based result means the
    # trade exceeds the configured risk_per_trade_pct — logged when it happens.
    # Set to 0.0 to disable (use raw broker minimum).
    min_trade_lot_floor: float = 0.10
    # PHASE 5 — intra-candle re-analysis cadence (seconds). When a position is
    # open, the analysis cycle will fire this often (in addition to M15 candle
    # closes) to let the AI re-evaluate the exit. Set 0 to disable.
    intra_candle_analysis_sec: int = 90
    # lot_size_mode is always "auto" — approval flow removed
    # max_concurrent_positions is always 1
    # Internal state
    bot_running: bool = False
    bot_status: str = "stopped"  # stopped, running, analyzing, paused, error
    error_message: str | None = None
    pause_until: str | None = None   # ISO timestamp; None = permanent pause
    start_balance: float = 0.0
    consecutive_losses: int = 0
    last_sl_hit_time: str | None = None
    last_user_interaction: str | None = None

    def validate_risk(self) -> float:
        """Ensure risk is between 1% and 10%."""
        return min(max(self.risk_per_trade_pct, 1.0), 10.0)


settings = Settings()
bot_config = BotConfig()
