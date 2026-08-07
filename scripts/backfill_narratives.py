#!/usr/bin/env python3
"""
Reconstitue un historique de capitalisation par narratif en additionnant
l'historique de marché des cryptos qui composent chaque catégorie CoinGecko.

L'API gratuite de CoinGecko ne fournit pas d'historique de capitalisation
PAR CATÉGORIE directement — seulement par crypto individuelle
(/coins/{id}/market_chart). On reconstruit donc l'historique d'un narratif
en sommant, jour par jour, la capitalisation des N plus grosses cryptos de
la catégorie correspondante.

⚠️ C'est une approximation : seules les N plus grosses cryptos de chaque
catégorie sont prises en compte (voir backfill_coins_per_narrative dans
config.json), pas la totalité. Pour la plupart des narratifs, les plus
grosses cryptos représentent l'essentiel de la capitalisation, donc l'écart
reste généralement faible.

À lancer une seule fois (ou occasionnellement) pour peupler l'historique
passé. La mise à jour quotidienne normale (fetch_narratives.py) prend le
relais ensuite pour le jour présent uniquement.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "narratives_history.json"
BASE = "https://api.coingecko.com/api/v3"
SLEEP_BETWEEN_CALLS = 1.6  # respecte le rate-limit gratuit de CoinGecko


def api_get(path, params=None, retries=3):
    qs = ""
    if params:
        qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    url = BASE + path + qs
    req = urllib.request.Request(url, headers={"User-Agent": "radar-crypto/1.0"})
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                wait = 20 * attempt
                print(f"  [rate-limit] pause {wait}s…", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  [erreur HTTP {e.code}] {url}", file=sys.stderr)
            return None
        except urllib.error.URLError as e:
            print(f"  [erreur réseau] {url}: {e}", file=sys.stderr)
            return None
    return None


def match_category_ids(all_categories, keywords):
    matches = []
    for cat in all_categories:
        name = (cat.get("name") or "").lower()
        cid = (cat.get("id") or "").lower()
        for kw in keywords:
            if kw.lower() in name or kw.lower() in cid:
                matches.append(cat["id"])
                break
    return matches


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    narratives = config["narratives"]
    days = config.get("backfill_days", 180)
    coins_per_narrative = config.get("backfill_coins_per_narrative", 15)

    print("Récupération de la liste des catégories CoinGecko…")
    all_categories = api_get("/coins/categories")
    if not all_categories:
        print("Impossible de récupérer les catégories, abandon.", file=sys.stderr)
        sys.exit(1)
    time.sleep(SLEEP_BETWEEN_CALLS)

    if HISTORY_PATH.exists():
        history_list = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history_list = []
    history_by_date = {h["date"]: h.get("values", {}) for h in history_list}

    for n in narratives:
        name = n["name"]
        cat_ids = match_category_ids(all_categories, n["keywords"])
        if not cat_ids:
            print(f"[{name}] aucune catégorie trouvée, ignoré.")
            continue
        cat_id = cat_ids[0]  # la catégorie la plus pertinente (premier match)
        print(f"[{name}] catégorie CoinGecko: {cat_id}")

        coins = api_get("/coins/markets", {
            "vs_currency": "usd", "category": cat_id,
            "order": "market_cap_desc", "per_page": coins_per_narrative, "page": 1
        })
        time.sleep(SLEEP_BETWEEN_CALLS)
        if not coins:
            print(f"[{name}] aucune crypto trouvée dans la catégorie, ignoré.")
            continue

        per_date_sum = {}
        for coin in coins:
            coin_id = coin["id"]
            chart = api_get(f"/coins/{coin_id}/market_chart", {
                "vs_currency": "usd", "days": days, "interval": "daily"
            })
            time.sleep(SLEEP_BETWEEN_CALLS)
            if not chart or "market_caps" not in chart:
                continue
            for ts_ms, cap in chart["market_caps"]:
                date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
                per_date_sum[date] = per_date_sum.get(date, 0) + cap

        print(f"[{name}] {len(per_date_sum)} jours récupérés sur {len(coins)} cryptos.")
        for date, total in per_date_sum.items():
            history_by_date.setdefault(date, {})[name] = round(total, 2)

    new_history = [{"date": d, "values": v} for d, v in history_by_date.items()]
    new_history.sort(key=lambda h: h["date"])
    new_history = new_history[-730:]

    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — historique narratifs: {len(new_history)} dates au total.")


if __name__ == "__main__":
    main()
