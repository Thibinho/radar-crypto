#!/usr/bin/env python3
"""
Récupère la capitalisation de marché par catégorie CoinGecko et met à jour
data/narratives_history.json avec le point du jour, pour chaque narratif
défini dans config.json.

Ce script est fait pour tourner de façon planifiée (GitHub Actions, cron...).
Il est idempotent : relancé plusieurs fois le même jour, il remplace le point
du jour au lieu de le dupliquer.
"""
import json
import sys
from datetime import date, timezone, datetime
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "narratives_history.json"
API_URL = "https://api.coingecko.com/api/v3/coins/categories"


def fetch_categories():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "radar-crypto/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def match_narrative(category, keywords):
    name = (category.get("name") or "").lower()
    cat_id = (category.get("id") or "").lower()
    for kw in keywords:
        kw = kw.lower()
        if kw in name or kw in cat_id:
            return True
    return False


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    narratives = config["narratives"]

    try:
        categories = fetch_categories()
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[fetch_narratives] Erreur réseau CoinGecko: {e}", file=sys.stderr)
        sys.exit(1)

    today = datetime.now(timezone.utc).date().isoformat()
    values = {}
    for n in narratives:
        best = None
        for cat in categories:
            mc = cat.get("market_cap")
            if not mc:
                continue
            if match_narrative(cat, n["keywords"]):
                # somme si plusieurs catégories matchent, garde la plus grosse sinon
                best = (best or 0) + mc
        if best is not None:
            values[n["name"]] = round(best, 2)
        else:
            print(f"[fetch_narratives] Aucune catégorie trouvée pour '{n['name']}'", file=sys.stderr)

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history = []

    history = [h for h in history if h["date"] != today]
    history.append({"date": today, "values": values})
    history.sort(key=lambda h: h["date"])
    history = history[-730:]  # garde ~2 ans max

    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_narratives] OK — {len(values)} narratifs mis à jour pour {today}")


if __name__ == "__main__":
    main()
