"""Configuration management for the trading bot."""

import os
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


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
    risk_per_trade_pct: float = 2.0
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
        """Ensure risk is capped at 5%."""
        return min(max(self.risk_per_trade_pct, 1.0), 5.0)


settings = Settings()
bot_config = BotConfig()
