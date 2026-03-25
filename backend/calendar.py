"""Finnhub economic calendar integration."""

import httpx
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

HIGH_IMPACT_EVENTS = [
    "FOMC", "Federal Funds Rate", "Interest Rate Decision",
    "CPI", "Consumer Price Index",
    "Non-Farm Payrolls", "NFP", "Nonfarm Payrolls",
    "ECB", "Main Refinancing Rate",
    "GDP", "Gross Domestic Product",
    "PPI", "Producer Price Index",
    "Unemployment Rate", "Unemployment Claims",
]


class EconomicCalendar:
    def __init__(self):
        self.api_key = ""
        self.events: list[dict] = []
        self.last_fetch: datetime | None = None

    async def fetch_events(self, api_key: str) -> list[dict]:
        """Fetch upcoming economic events from Finnhub."""
        self.api_key = api_key
        if not api_key:
            return []

        now = datetime.now(timezone.utc)

        # Only fetch once per hour
        if self.last_fetch and (now - self.last_fetch) < timedelta(hours=1):
            return self.events

        try:
            from_date = now.strftime("%Y-%m-%d")
            to_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://finnhub.io/api/v1/calendar/economic",
                    params={
                        "from": from_date,
                        "to": to_date,
                        "token": api_key,
                    }
                )
                resp.raise_for_status()
                data = resp.json()

            raw_events = data.get("economicCalendar", [])
            filtered = []
            for ev in raw_events:
                event_name = ev.get("event", "")
                impact = ev.get("impact", "")
                country = ev.get("country", "")

                # Only USD and EUR high-impact events
                if country not in ("US", "EU", "DE", "FR", "EMU"):
                    continue

                is_high = impact == "high" or any(
                    kw.lower() in event_name.lower() for kw in HIGH_IMPACT_EVENTS
                )
                if not is_high:
                    continue

                filtered.append({
                    "event": event_name,
                    "time": ev.get("time", ""),
                    "date": ev.get("date", ""),
                    "impact": "high",
                    "currency": country,
                    "actual": ev.get("actual"),
                    "estimate": ev.get("estimate"),
                    "prev": ev.get("prev"),
                })

            self.events = filtered
            self.last_fetch = now
            logger.info(f"Fetched {len(filtered)} high-impact events.")
            return filtered

        except Exception as e:
            logger.error(f"Failed to fetch economic calendar: {e}")
            return self.events  # Return cached

    def is_news_clear(self, utc_now: datetime | None = None) -> bool:
        """
        Check if there's no high-impact event within:
        - 30 minutes before
        - 15 minutes after
        """
        if utc_now is None:
            utc_now = datetime.now(timezone.utc)

        for ev in self.events:
            try:
                event_date = ev.get("date", "")
                event_time = ev.get("time", "")
                if not event_date or not event_time:
                    continue
                event_dt = datetime.strptime(
                    f"{event_date} {event_time}", "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)

                # 30 min before to 15 min after
                window_start = event_dt - timedelta(minutes=30)
                window_end = event_dt + timedelta(minutes=15)

                if window_start <= utc_now <= window_end:
                    return False
            except (ValueError, TypeError):
                continue

        return True

    def get_upcoming_events(self, hours: int = 24) -> list[dict]:
        """Get events within the next N hours."""
        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(hours=hours)
        upcoming = []
        for ev in self.events:
            try:
                event_date = ev.get("date", "")
                event_time = ev.get("time", "")
                if not event_date or not event_time:
                    continue
                event_dt = datetime.strptime(
                    f"{event_date} {event_time}", "%Y-%m-%d %H:%M:%S"
                ).replace(tzinfo=timezone.utc)
                if now <= event_dt <= cutoff:
                    upcoming.append(ev)
            except (ValueError, TypeError):
                continue
        return upcoming


economic_calendar = EconomicCalendar()
