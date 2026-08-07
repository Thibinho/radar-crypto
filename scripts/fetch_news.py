#!/usr/bin/env python3
"""
Récupère les dernières actualités crypto via des flux RSS publics et
gratuits (CoinDesk, Cointelegraph — aucune clé API nécessaire) et écrit
data/news.json avec les articles les plus récents.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "data" / "news.json"

FEEDS_DEFAULT = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Journal du Coin", "https://journalducoin.com/feed/"),
    ("Cryptoast", "https://cryptoast.fr/feed/"),
]
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


def fetch_feed(name, url):
    req = urllib.request.Request(url, headers={"User-Agent": "radar-crypto/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[fetch_news] Erreur réseau sur {name}: {e}", file=sys.stderr)
        return []

    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        print(f"[fetch_news] XML invalide pour {name}: {e}", file=sys.stderr)
        return []

    items = []
    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        pub = item.findtext("pubDate")
        try:
            dt = parsedate_to_datetime(pub) if pub else datetime.now(timezone.utc)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            dt = datetime.now(timezone.utc)
        if title and link:
            items.append({
                "title": title,
                "link": link,
                "source": name,
                "published": dt.isoformat(),
            })
    return items


def load_feeds_and_max():
    """Lit news_feeds / news_max_items depuis config.json si présents,
    sinon retombe sur les valeurs par défaut codées en dur."""
    try:
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        raw_feeds = config.get("news_feeds")
        if raw_feeds:
            feeds = [(f["name"], f["url"]) for f in raw_feeds]
        else:
            feeds = FEEDS_DEFAULT
        max_items = config.get("news_max_items", 16)
        return feeds, max_items
    except Exception as e:
        print(f"[fetch_news] Impossible de lire config.json ({e}), utilisation des valeurs par défaut.", file=sys.stderr)
        return FEEDS_DEFAULT, 16


def main():
    feeds, max_items = load_feeds_and_max()
    all_items = []
    for name, url in feeds:
        all_items.extend(fetch_feed(name, url))

    if not all_items:
        print("[fetch_news] Aucun article récupéré, abandon.", file=sys.stderr)
        sys.exit(1)

    all_items.sort(key=lambda i: i["published"], reverse=True)
    top = all_items[:max_items]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": top,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fetch_news] OK — {len(top)} articles récupérés")


if __name__ == "__main__":
    main()
