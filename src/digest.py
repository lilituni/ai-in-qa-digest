"""Daily Influencer Digest.

Pipeline: fetch posts -> keep only today's -> format -> send to Telegram.

Run locally:
    pip install -r requirements.txt
    python digest.py --debug

Config comes from environment variables (see README.md / .env.example).
"""
from __future__ import annotations

import html
import logging
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()  # no-op if .env doesn't exist (e.g. on GitHub Actions)
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("digest")


# ---------- Config ----------------------------------------------------------

@dataclass(frozen=True)
class Config:
    apify_token: str
    bot_token: str
    chat_id: str
    profile_url: str
    author_name: str
    actor: str
    timezone: ZoneInfo
    send_empty_message: bool

    @classmethod
    def from_env(cls) -> "Config":
        try:
            return cls(
                apify_token=os.environ["APIFY_TOKEN"],
                bot_token=os.environ["TELEGRAM_BOT_TOKEN"],
                chat_id=os.environ["TELEGRAM_CHAT_ID"],
                profile_url=os.getenv("PROFILE_URL", "https://www.linkedin.com/in/tariqking"),
                author_name=os.getenv("AUTHOR_NAME", "Tariq King"),
                actor=os.getenv("APIFY_ACTOR", "myagizm~linkedin-profile-posts-scraper"),
                timezone=ZoneInfo(os.getenv("TIMEZONE", "Asia/Yerevan")),
                send_empty_message=os.getenv("SEND_EMPTY_MESSAGE", "true").lower() == "true",
            )
        except KeyError as e:
            sys.exit(f"Missing required environment variable: {e}")


DATE_KEYS = ["datePublished", "postedAt", "posted_at", "postedDate", "publishedAt", "date", "timestamp", "createdAt", "time"]
TEXT_KEYS = ["text", "content", "postText", "commentary", "description"]
URL_KEYS = ["url", "postUrl", "post_url", "link", "permalink"]


# ---------- Extract -----------------------------------------------------

def fetch_posts(cfg: Config) -> list[dict]:
    """Call the Apify actor and return raw post dicts."""
    url = f"https://api.apify.com/v2/acts/{cfg.actor}/run-sync-get-dataset-items"
    payload = {"startUrls": [{"url": cfg.profile_url}], "maxItems": 20}
    resp = requests.post(url, params={"token": cfg.apify_token}, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()


# ---------- Transform -----------------------------------------------------

def _first(item: dict, keys: list[str]):
    """Return the first present value among `keys` — scrapers don't agree on field names."""
    for key in keys:
        if item.get(key):
            return item[key]
    return None


def parse_date(value) -> datetime | None:
    """Normalize a scraper's date field (ISO string, epoch, or '3h'/'2d' style) to an aware datetime."""
    now = datetime.now(timezone.utc)

    if isinstance(value, dict):
        return parse_date(_first(value, ["date", "timestamp", "iso", "value"]))

    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e11 else value  # ms vs s epoch
        return datetime.fromtimestamp(seconds, tz=timezone.utc)

    if isinstance(value, str):
        s = value.strip().lower()
        if m := re.match(r"^(\d+)\s*(mo|m|h|d|w|y)\b", s):
            n, unit = int(m.group(1)), m.group(2)
            delta = {
                "m": timedelta(minutes=n), "h": timedelta(hours=n), "d": timedelta(days=n),
                "w": timedelta(weeks=n), "mo": timedelta(days=30 * n), "y": timedelta(days=365 * n),
            }[unit]
            return now - delta
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    return None


def is_today(dt: datetime | None, tz: ZoneInfo) -> bool:
    return dt is not None and dt.astimezone(tz).date() == datetime.now(tz).date()


def filter_todays_posts(posts: list[dict], tz: ZoneInfo) -> list[dict]:
    return [p for p in posts if is_today(parse_date(_first(p, DATE_KEYS)), tz)]


def format_post(post: dict, author_name: str, fallback_url: str) -> str:
    text = str(_first(post, TEXT_KEYS) or "").strip()
    excerpt = text if len(text) <= 600 else text[:600].rstrip() + "…"
    link = _first(post, URL_KEYS) or fallback_url
    return (
        f"<b>{html.escape(author_name)}</b>\n\n"
        f"{html.escape(excerpt)}\n\n"
        f'<a href="{html.escape(link, quote=True)}">View original post</a>'
    )


# ---------- Load -----------------------------------------------------

def send_telegram_message(cfg: Config, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage",
        json={"chat_id": cfg.chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False},
        timeout=30,
    )
    resp.raise_for_status()


# ---------- Orchestration -----------------------------------------------------

def run(cfg: Config, debug: bool = False) -> None:
    posts = fetch_posts(cfg)
    if True:
        for i, p in enumerate(posts):
            print(i, _first(p, DATE_KEYS))
    if debug and posts:
        log.info("Fields in first item: %s", sorted(posts[0].keys()))
        log.info("Raw date value: %r", _first(posts[0], DATE_KEYS))

    todays_posts = filter_todays_posts(posts, cfg.timezone)
    log.info("Fetched %d posts, %d from today", len(posts), len(todays_posts))

    if not todays_posts:
        if cfg.send_empty_message:
            send_telegram_message(cfg, "No new posts today.")
        return

    for post in todays_posts:
        send_telegram_message(cfg, format_post(post, cfg.author_name, cfg.profile_url))



if __name__ == "__main__":
    run(Config.from_env(), debug="--debug" in sys.argv)