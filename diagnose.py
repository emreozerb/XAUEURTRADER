"""End-to-end diagnostic — validates AI key, MT5, indicators, full strategy flow."""
import asyncio, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from dotenv import load_dotenv
load_dotenv(override=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.config import settings, bot_config
from backend.ai_engine import ai_engine
from backend.mt5_connector import mt5_connector
from backend.indicators import calculate_indicators
from backend.strategy import identify_trend, check_buy_signal, check_sell_signal, calculate_sl_tp
from backend.risk_manager import risk_manager


async def main():
    print("=" * 70)
    print("XAUEUR TRADER — END-TO-END DIAGNOSTIC")
    print("=" * 70)

    # 1. ENV / API KEY
    print("\n[1] ENV CHECK")
    key = settings.anthropic_api_key
    print(f"   ANTHROPIC_API_KEY: {key[:18]}...{key[-6:]} ({len(key)} chars)")
    assert len(key) > 50, "Key not loaded"

    # 2. AI ENGINE
    print("\n[2] AI ENGINE TEST (real Claude API call)")
    ai_engine.initialize(key)
    test_packet = {
        "current_price": {"bid": 4025.0, "ask": 4025.23},
        "indicators": {"m15": {"ema_50": 4020.0, "rsi_14": 55, "atr_14": 1.5},
                       "h4": {"ema_50": 4015.0, "ema_200": 3980.0}},
        "trend": "uptrend", "open_positions": [], "active_session": "London",
        "ema50_proximity": True, "rsi_zone": "buy_ok", "upcoming_events": [],
        "last_5_trades": [], "account": {"balance": 2992.83, "equity": 2992.83},
    }
    result = await ai_engine.analyze(test_packet)
    if result is None:
        print(f"   ❌ FAILED: {ai_engine.last_error_reason}")
        return
    print(f"   ✅ AI responded: action={result['action']}, confidence={result['confidence']}%")
    print(f"      reasoning: {result['reasoning'][:120]}...")

    # 3. MT5 CONNECTION
    print("\n[3] MT5 CONNECTION")
    if not mt5_connector.connected:
        print("   ⚠ MT5 not connected via UI yet. Connect in browser first.")
        return
    print(f"   ✅ Connected. Balance: {mt5_connector.account_info_data['balance']} {mt5_connector.account_info_data['currency']}")
    print(f"      Symbol info: {mt5_connector.symbol_info}")

    # 4. CANDLES + INDICATORS
    print("\n[4] LIVE DATA")
    m15 = mt5_connector.get_candles("M15", 50)
    h4 = mt5_connector.get_candles("H4", 50)
    price = mt5_connector.get_current_price()
    print(f"   M15 candles: {len(m15) if m15 is not None else 'None'}")
    print(f"   H4 candles: {len(h4) if h4 is not None else 'None'}")
    print(f"   Current price: bid={price['bid']}, ask={price['ask']}")

    m15_ind = calculate_indicators(m15, "M15")
    h4_ind = calculate_indicators(h4, "H4")
    trend = identify_trend(h4_ind, current_price=price['bid'])
    print(f"   M15 EMA50={m15_ind.get('ema_50'):.2f}, RSI={m15_ind.get('rsi_14'):.1f}, ATR={m15_ind.get('atr_14'):.2f}")
    print(f"   H4 trend: {trend}")

    # 5. STRATEGY SIGNAL CHECK
    print("\n[5] STRATEGY SIGNAL CHECK")
    buy = check_buy_signal(m15_ind, trend, "london", True, [])
    sell = check_sell_signal(m15_ind, trend, "london", True, [])
    print(f"   BUY signal: {buy['signal']} | reasons: {buy['reasons'][:2]}")
    print(f"   SELL signal: {sell['signal']} | reasons: {sell['reasons'][:2]}")

    # 6. RISK / LOT SIZE CALC
    print("\n[6] RISK MANAGER")
    sl_tp = calculate_sl_tp("buy", price['ask'], m15_ind['atr_14'], m15_ind['ema_50'])
    lot_calc = risk_manager.calculate_lot_size(
        account_balance=2992.83, free_margin=2992.83,
        risk_pct=2.0, sl_distance=abs(price['ask'] - sl_tp['stop_loss']),
        symbol_info=mt5_connector.symbol_info
    )
    print(f"   SL: {sl_tp['stop_loss']:.2f}, TP: {sl_tp['take_profit']:.2f}")
    print(f"   Lot calc: {lot_calc}")

    print("\n" + "=" * 70)
    print("✅ ALL SYSTEMS OPERATIONAL — bot is ready to trade.")
    print("=" * 70)

asyncio.run(main())
