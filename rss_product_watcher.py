#!/usr/bin/env python3
"""Scheduled RSS/Atom watcher for new product alerts.

Runs in GitHub Actions (or locally), tracks seen entries per feed in JSON,
and emails only newly discovered products.
"""

from __future__ import annotations

import json
import os
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlparse

import feedparser


# Optional defaults. Prefer using FEED_URLS env var in production.
FEEDS = [
    # "https://example.com/collections/all.atom",
    # "https://example2.com/collections/all.atom",
]

STATE_FILE = Path("seen_feed_items.json")
MAX_ITEMS_PER_FEED = int(os.environ.get("MAX_ITEMS_PER_FEED", "40"))
MAX_UIDS_PER_FEED = int(os.environ.get("MAX_UIDS_PER_FEED", "1000"))

# If enabled, the first time a feed is seen we learn current entries without alerting.
BOOTSTRAP_ON_EMPTY_STATE = os.environ.get("BOOTSTRAP_ON_EMPTY_STATE", "true").lower() == "true"

# Email/SMTP configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "465"))
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", SMTP_USERNAME)
EMAIL_TO = [e.strip() for e in os.environ.get("EMAIL_TO", "").split(",") if e.strip()]


def configured_feeds() -> list[str]:
    """Return feed URLs from FEED_URLS env var or fallback FEEDS list."""
    env_feeds = [u.strip() for u in os.environ.get("FEED_URLS", "").split(",") if u.strip()]
    return env_feeds if env_feeds else FEEDS


def load_state(path: Path) -> dict[str, list[str]]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: dict[str, list[str]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_uid(entry: dict) -> str:
    """Use stable fields first so feed reorderings do not trigger duplicates."""
    for key in ("id", "guid", "link"):
        value = entry.get(key)
        if value:
            return str(value).strip()

    title = str(entry.get("title", "")).strip()
    published = str(entry.get("published", entry.get("updated", ""))).strip()
    return f"{title}::{published}"


def parse_feed(feed_url: str) -> list[dict]:
    parsed = feedparser.parse(feed_url)
    if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", None):
        bozo_exception = getattr(parsed, "bozo_exception", "Unknown parsing error")
        raise RuntimeError(f"Unable to parse feed {feed_url}: {bozo_exception}")
    return list(parsed.entries[:MAX_ITEMS_PER_FEED])


def fetch_new_items(feed_url: str, seen_uids: list[str]) -> tuple[list[dict], list[str]]:
    entries = parse_feed(feed_url)
    seen_lookup = set(seen_uids)
    new_items: list[dict] = []
    updated_seen = list(seen_uids)

    for entry in entries:
        uid = normalize_uid(entry)
        if uid in seen_lookup:
            continue
        new_items.append(
            {
                "uid": uid,
                "title": str(entry.get("title", "(no title)")),
                "link": str(entry.get("link", "")),
                "published": str(entry.get("published", entry.get("updated", ""))),
                "feed_url": feed_url,
            }
        )
        updated_seen.append(uid)
        seen_lookup.add(uid)

    updated_seen = updated_seen[-MAX_UIDS_PER_FEED:]
    return new_items, updated_seen


def build_email(new_items: list[dict]) -> tuple[str, str]:
    if len(new_items) == 1:
        host = urlparse(new_items[0]["feed_url"]).netloc
        subject = f"New product detected ({host}): {new_items[0]['title']}"
    else:
        subject = f"{len(new_items)} new products detected"

    lines = ["New product(s) found in monitored feeds:\n"]
    for item in new_items:
        host = urlparse(item["feed_url"]).netloc
        lines.append(f"- {item['title']}")
        if item["published"]:
            lines.append(f"  Published: {item['published']}")
        lines.append(f"  Link: {item['link']}")
        lines.append(f"  Feed: {host}")
        lines.append("")
    return subject, "\n".join(lines).rstrip() + "\n"


def send_email(subject: str, body: str) -> None:
    if not SMTP_USERNAME or not SMTP_PASSWORD:
        raise RuntimeError("SMTP credentials are missing. Set SMTP_USERNAME and SMTP_PASSWORD.")
    if not EMAIL_TO:
        raise RuntimeError("EMAIL_TO is missing. Add at least one recipient.")
    if not EMAIL_FROM:
        raise RuntimeError("EMAIL_FROM is missing.")

    message = EmailMessage()
    message["From"] = EMAIL_FROM
    message["To"] = ", ".join(EMAIL_TO)
    message["Subject"] = subject
    message.set_content(body)

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=context) as server:
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(message)


def main() -> int:
    feeds = configured_feeds()
    if not feeds:
        print("ERROR: Add feed URLs via FEED_URLS env var or FEEDS in the script.")
        return 2

    state = load_state(STATE_FILE)
    all_new: list[dict] = []

    for feed_url in feeds:
        seen = state.get(feed_url, [])

        # On first encounter, prime state without emailing historical entries.
        if BOOTSTRAP_ON_EMPTY_STATE and feed_url not in state:
            initial_entries = parse_feed(feed_url)
            state[feed_url] = [normalize_uid(e) for e in initial_entries][-MAX_UIDS_PER_FEED:]
            print(f"Bootstrapped {feed_url} with {len(state[feed_url])} existing entries.")
            continue

        new_items, updated_seen = fetch_new_items(feed_url, seen)
        state[feed_url] = updated_seen
        all_new.extend(new_items)

    save_state(STATE_FILE, state)

    if all_new:
        subject, body = build_email(all_new)
        send_email(subject, body)
        print(f"Emailed {len(all_new)} new item(s).")
    else:
        print("No new items.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
