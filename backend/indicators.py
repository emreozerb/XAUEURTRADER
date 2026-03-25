"""Technical indicator calculations using pandas-ta."""

import pandas as pd
import pandas_ta as ta


def calculate_indicators(df: pd.DataFrame, timeframe: str) -> dict:
    """
    Calculate technical indicators on a DataFrame of candles.
    Returns a dict of current indicator values.
    """
    if df is None or df.empty:
        return {}

    result = {}

    # EMA 50
    ema50 = ta.ema(df["close"], length=50)
    if ema50 is not None and len(ema50) > 0:
        result["ema_50"] = round(float(ema50.iloc[-1]), 5) if pd.notna(ema50.iloc[-1]) else None
    else:
        result["ema_50"] = None

    # EMA 200 (only meaningful for H1 with 100 candles)
    ema200 = ta.ema(df["close"], length=200)
    if ema200 is not None and len(ema200) > 0 and pd.notna(ema200.iloc[-1]):
        result["ema_200"] = round(float(ema200.iloc[-1]), 5)
    else:
        result["ema_200"] = None

    # ATR 14
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    if atr is not None and len(atr) > 0:
        result["atr_14"] = round(float(atr.iloc[-1]), 5) if pd.notna(atr.iloc[-1]) else None
    else:
        result["atr_14"] = None

    # RSI 14 (mainly for H1)
    rsi = ta.rsi(df["close"], length=14)
    if rsi is not None and len(rsi) > 0:
        result["rsi_14"] = round(float(rsi.iloc[-1]), 2) if pd.notna(rsi.iloc[-1]) else None
        # Also get previous RSI for crossover detection
        if len(rsi) > 1 and pd.notna(rsi.iloc[-2]):
            result["rsi_14_prev"] = round(float(rsi.iloc[-2]), 2)
        else:
            result["rsi_14_prev"] = None
    else:
        result["rsi_14"] = None
        result["rsi_14_prev"] = None

    # Bollinger Bands (mainly for H1)
    bbands = ta.bbands(df["close"], length=20, std=2)
    if bbands is not None and not bbands.empty:
        cols = bbands.columns
        result["bollinger_upper"] = round(float(bbands[cols[2]].iloc[-1]), 5) if pd.notna(bbands[cols[2]].iloc[-1]) else None
        result["bollinger_mid"] = round(float(bbands[cols[1]].iloc[-1]), 5) if pd.notna(bbands[cols[1]].iloc[-1]) else None
        result["bollinger_lower"] = round(float(bbands[cols[0]].iloc[-1]), 5) if pd.notna(bbands[cols[0]].iloc[-1]) else None
    else:
        result["bollinger_upper"] = None
        result["bollinger_mid"] = None
        result["bollinger_lower"] = None

    # Current price info
    result["current_close"] = round(float(df["close"].iloc[-1]), 5)
    result["prev_close"] = round(float(df["close"].iloc[-2]), 5) if len(df) > 1 else None

    return result


def get_full_series(df: pd.DataFrame) -> dict:
    """Get full indicator series for backtesting."""
    if df is None or df.empty:
        return {}

    ema50 = ta.ema(df["close"], length=50)
    ema200 = ta.ema(df["close"], length=200)
    atr = ta.atr(df["high"], df["low"], df["close"], length=14)
    rsi = ta.rsi(df["close"], length=14)
    bbands = ta.bbands(df["close"], length=20, std=2)

    return {
        "ema_50": ema50,
        "ema_200": ema200,
        "atr_14": atr,
        "rsi_14": rsi,
        "bbands": bbands,
    }
