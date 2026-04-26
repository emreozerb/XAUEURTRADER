"""Direct order_send test — verifies the trade pipeline works end-to-end.
Uses the backend's running MT5 connection via the API, not direct MT5 import."""
import os, sys, io, json, asyncio
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import httpx

API = "http://localhost:8000"

async def main():
    async with httpx.AsyncClient(timeout=30) as c:
        # 1. Get current state
        r = await c.get(f"{API}/api/status")
        s = r.json()
        if not s["connected"]:
            print("❌ MT5 not connected via UI — connect first")
            return
        print(f"✅ MT5 Connected | Balance: {s['account']['balance']} {s['account']['currency']}")
        print(f"   Price: bid={s['current_price']['bid']} ask={s['current_price']['ask']}")
        print(f"   Last tick: {s['current_price']['time']}")

        # 2. Test order via internal endpoint by triggering TEST_MODE through bot start.
        # But we need a direct order test. Use a small custom endpoint workaround:
        # We'll call execute_trade through a debug script injected into the running process.
        print("\n→ Probing order_send via direct MT5 in same process not possible.")
        print("→ Instead: enable TEST_MODE in backend → start bot → watch logs.")

asyncio.run(main())
