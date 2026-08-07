#!/usr/bin/env python3
"""
Récupère les dernières actualités crypto via des flux RSS publics et
gratuits (CoinDesk, Cointelegraph, Journal du Coin, Cryptoast — aucune
clé API nécessaire) et écrit data/news.json avec les articles les plus
récents.
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

FEEDS = [
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Journal du Coin", "https://journalducoin.com/feed/"),
    ("Cryptoast", "https://cryptoast.fr/feed/"),
]

MAX_ITEMS = 16


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


def main():
    all_items = []
    for name, url in FEEDS:
        all_items.extend(fetch_feed(name, url))

    if not all_items:
        print("[fetch_news] Aucun article récupéré, abandon.", file=sys.stderr)
        sys.exit(1)

    all_items.sort(key=lambda i: i["published"], reverse=True)
    top = all_items[:MAX_ITEMS]

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "items": top,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fetch_news] OK — {len(top)} articles récupérés")


if __name__ == "__main__":
    main()
