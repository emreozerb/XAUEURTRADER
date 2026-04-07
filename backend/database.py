"""SQLite database setup and queries."""

import aiosqlite
import os
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "trading_bot.db")


async def init_db():
    """Create database tables if they don't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS analysis_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                xaueur_price REAL,
                h1_ema50 REAL,
                h1_ema200 REAL,
                h4_ema50 REAL,
                h4_ema200 REAL,
                rsi_14 REAL,
                atr_14 REAL,
                trend TEXT,
                session TEXT,
                ai_action TEXT,
                ai_confidence INTEGER,
                ai_reasoning TEXT,
                executed INTEGER DEFAULT 0,
                skipped_reason TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trade_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_timestamp TEXT NOT NULL,
                exit_timestamp TEXT,
                direction TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                stop_loss REAL NOT NULL,
                take_profit REAL NOT NULL,
                lot_size REAL NOT NULL,
                risk_eur REAL,
                result TEXT,
                pips REAL,
                pnl_eur REAL,
                duration_minutes INTEGER,
                exit_reason TEXT,
                ai_confidence INTEGER,
                ai_reasoning TEXT,
                account_balance_at_entry REAL,
                account_balance_at_exit REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS weekly_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week TEXT NOT NULL UNIQUE,
                total_trades INTEGER,
                wins INTEGER,
                losses INTEGER,
                win_rate_pct REAL,
                net_pips REAL,
                net_pnl_eur REAL,
                avg_confidence_winners REAL,
                avg_confidence_losers REAL,
                best_trade_pips REAL,
                worst_trade_pips REAL,
                avg_trade_duration_min REAL,
                max_drawdown_eur REAL,
                max_drawdown_pct REAL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                source TEXT,
                message TEXT NOT NULL
            )
        """)
        await db.commit()


async def get_db():
    """Get a database connection."""
    return aiosqlite.connect(DB_PATH)


async def log_analysis(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO analysis_log (
                timestamp, xaueur_price, h1_ema50, h1_ema200, h4_ema50, h4_ema200,
                rsi_14, atr_14, trend, session, ai_action, ai_confidence,
                ai_reasoning, executed, skipped_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("timestamp"), data.get("xaueur_price"),
            data.get("h1_ema50"), data.get("h1_ema200"),
            data.get("h4_ema50"), data.get("h4_ema200"),
            data.get("rsi_14"), data.get("atr_14"),
            data.get("trend"), data.get("session"),
            data.get("ai_action"), data.get("ai_confidence"),
            data.get("ai_reasoning"), data.get("executed", 0),
            data.get("skipped_reason")
        ))
        await db.commit()


async def log_trade(data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO trade_log (
                entry_timestamp, exit_timestamp, direction, entry_price, exit_price,
                stop_loss, take_profit, lot_size, risk_eur, result, pips, pnl_eur,
                duration_minutes, exit_reason, ai_confidence, ai_reasoning,
                account_balance_at_entry, account_balance_at_exit
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("entry_timestamp"), data.get("exit_timestamp"),
            data.get("direction"), data.get("entry_price"), data.get("exit_price"),
            data.get("stop_loss"), data.get("take_profit"), data.get("lot_size"),
            data.get("risk_eur"), data.get("result"), data.get("pips"),
            data.get("pnl_eur"), data.get("duration_minutes"), data.get("exit_reason"),
            data.get("ai_confidence"), data.get("ai_reasoning"),
            data.get("account_balance_at_entry"), data.get("account_balance_at_exit")
        ))
        await db.commit()


async def update_trade_exit(trade_id: int, data: dict):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            UPDATE trade_log SET
                exit_timestamp = ?, exit_price = ?, result = ?, pips = ?,
                pnl_eur = ?, duration_minutes = ?, exit_reason = ?,
                account_balance_at_exit = ?
            WHERE id = ?
        """, (
            data.get("exit_timestamp"), data.get("exit_price"),
            data.get("result"), data.get("pips"), data.get("pnl_eur"),
            data.get("duration_minutes"), data.get("exit_reason"),
            data.get("account_balance_at_exit"), trade_id
        ))
        await db.commit()


async def get_last_n_trades(n: int = 5) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trade_log ORDER BY id DESC LIMIT ?", (n,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_trade_log(limit: int = 50) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM trade_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_performance_summary() -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN result='win' THEN 1 ELSE 0 END) as wins, "
            "SUM(CASE WHEN result='loss' THEN 1 ELSE 0 END) as losses, "
            "SUM(pips) as net_pips, "
            "SUM(pnl_eur) as net_pnl_eur, "
            "AVG(CASE WHEN pips > 0 THEN pips / NULLIF(ABS(stop_loss - entry_price), 0) END) as avg_rr "
            "FROM trade_log WHERE result IS NOT NULL"
        )
        row = await cursor.fetchone()
        if not row or row[0] == 0:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0, "net_pips": 0, "net_pnl_eur": 0,
                "avg_rr": 0, "max_drawdown_eur": 0, "max_drawdown_pct": 0
            }
        total, wins, losses = row[0], row[1] or 0, row[2] or 0
        win_rate = (wins / total * 100) if total > 0 else 0

        # Calculate max drawdown
        cursor2 = await db.execute(
            "SELECT pnl_eur FROM trade_log WHERE result IS NOT NULL ORDER BY id"
        )
        pnls = [r[0] for r in await cursor2.fetchall() if r[0] is not None]
        max_dd = 0
        peak = 0
        cumulative = 0
        for pnl in pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd

        cursor3 = await db.execute(
            "SELECT account_balance_at_entry FROM trade_log ORDER BY id ASC LIMIT 1"
        )
        first_row = await cursor3.fetchone()
        start_bal = first_row[0] if first_row and first_row[0] else 10000
        max_dd_pct = (max_dd / start_bal * 100) if start_bal > 0 else 0

        return {
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
            "net_pips": round(row[4] or 0, 1),
            "net_pnl_eur": round(row[5] or 0, 2),
            "avg_rr": round(row[6] or 0, 2) if row[6] else 0,
            "max_drawdown_eur": round(max_dd, 2),
            "max_drawdown_pct": round(max_dd_pct, 1)
        }


async def log_event(level: str, message: str, source: str = "system") -> None:
    """Persist an event/alert to the event_log table."""
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO event_log (timestamp, level, source, message) VALUES (?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), level, source, message)
            )
            await db.commit()
    except Exception as exc:
        # Don't let logging failures crash the bot — just print to stderr
        import sys
        print(f"[event_log write error] {exc}", file=sys.stderr)


async def get_event_log(limit: int = 200) -> list[dict]:
    """Return the most recent events, newest first."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM event_log ORDER BY id DESC LIMIT ?", (limit,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def generate_weekly_summary(week_str: str):
    """Generate and store weekly summary."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT * FROM trade_log WHERE entry_timestamp LIKE ? AND result IS NOT NULL",
            (f"%{week_str}%",)
        )
        # This is a simplified approach - in production, filter by actual week dates
        rows = await cursor.fetchall()
        if not rows:
            return None

        trades = []
        for r in rows:
            trades.append({
                "pips": r[11], "pnl_eur": r[12], "result": r[10],
                "ai_confidence": r[15], "duration_minutes": r[13]
            })

        total = len(trades)
        wins = sum(1 for t in trades if t["result"] == "win")
        losses = sum(1 for t in trades if t["result"] == "loss")
        win_rate = (wins / total * 100) if total > 0 else 0
        net_pips = sum(t["pips"] or 0 for t in trades)
        net_pnl = sum(t["pnl_eur"] or 0 for t in trades)

        winner_confs = [t["ai_confidence"] for t in trades if t["result"] == "win" and t["ai_confidence"]]
        loser_confs = [t["ai_confidence"] for t in trades if t["result"] == "loss" and t["ai_confidence"]]
        pips_list = [t["pips"] or 0 for t in trades]
        durations = [t["duration_minutes"] or 0 for t in trades]

        summary = {
            "week": week_str,
            "total_trades": total,
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1),
            "net_pips": round(net_pips, 1),
            "net_pnl_eur": round(net_pnl, 2),
            "avg_confidence_winners": round(sum(winner_confs) / len(winner_confs), 1) if winner_confs else 0,
            "avg_confidence_losers": round(sum(loser_confs) / len(loser_confs), 1) if loser_confs else 0,
            "best_trade_pips": max(pips_list) if pips_list else 0,
            "worst_trade_pips": min(pips_list) if pips_list else 0,
            "avg_trade_duration_min": round(sum(durations) / len(durations), 1) if durations else 0,
            "max_drawdown_eur": 0,
            "max_drawdown_pct": 0
        }

        await db.execute("""
            INSERT OR REPLACE INTO weekly_summary (
                week, total_trades, wins, losses, win_rate_pct, net_pips,
                net_pnl_eur, avg_confidence_winners, avg_confidence_losers,
                best_trade_pips, worst_trade_pips, avg_trade_duration_min,
                max_drawdown_eur, max_drawdown_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, tuple(summary.values()))
        await db.commit()
        return summary
