#!/usr/bin/env python3
"""
Récupère la capitalisation de marché par catégorie CoinGecko et met à jour
data/narratives_history.json avec le point du jour, pour chaque narratif
défini dans config.json.

Sauvegarde également un instantané COMPLET de toutes les catégories
CoinGecko (pas seulement celles suivies) dans
data/categories_snapshot_history.json — utilisé ensuite par
generate_alerts.py pour détecter des narratifs émergents non encore suivis.

Ce script est fait pour tourner de façon planifiée (GitHub Actions, cron...).
Il est idempotent : relancé plusieurs fois le même jour, il remplace le point
du jour au lieu de le dupliquer.
"""
import json
import os
import sys
from datetime import date, timezone, datetime
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "narratives_history.json"
SNAPSHOT_PATH = ROOT / "data" / "categories_snapshot_history.json"
API_URL = "https://api.coingecko.com/api/v3/coins/categories"
API_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
SNAPSHOT_RETENTION_DAYS = 60  # suffisant pour comparer sur plusieurs semaines


def fetch_categories():
    headers = {"User-Agent": "radar-crypto/1.0"}
    if API_KEY:
        headers["x-cg-demo-api-key"] = API_KEY
    req = urllib.request.Request(API_URL, headers=headers)
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

    # --- 1. Mise à jour de l'historique des narratifs suivis ---
    values = {}
    for n in narratives:
        best = None
        for cat in categories:
            mc = cat.get("market_cap")
            if not mc:
                continue
            if match_narrative(cat, n["keywords"]):
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
    history = history[-730:]
    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_narratives] OK — {len(values)} narratifs mis à jour pour {today}")

    # --- 2. Instantané complet des catégories (pour détection d'émergents) ---
    all_caps = {c["id"]: {"name": c.get("name", c["id"]), "market_cap": c.get("market_cap") or 0}
                for c in categories if c.get("market_cap")}

    if SNAPSHOT_PATH.exists():
        snap_history = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    else:
        snap_history = []
    snap_history = [s for s in snap_history if s["date"] != today]
    snap_history.append({"date": today, "categories": all_caps})
    snap_history.sort(key=lambda s: s["date"])
    snap_history = snap_history[-SNAPSHOT_RETENTION_DAYS:]
    SNAPSHOT_PATH.write_text(json.dumps(snap_history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_narratives] OK — instantané de {len(all_caps)} catégories sauvegardé pour {today}")


if __name__ == "__main__":
    main()
