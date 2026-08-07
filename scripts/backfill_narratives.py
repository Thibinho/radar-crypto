#!/usr/bin/env python3
"""
Reconstitue un historique de capitalisation par narratif en additionnant
l'historique de marché des cryptos qui composent chaque catégorie CoinGecko,
puis recalibre le résultat sur la vraie capitalisation totale du jour
(gratuite, déjà présente dans /coins/categories) pour limiter l'écart dû au
fait qu'on ne regarde que les N plus grosses cryptos de chaque catégorie.

Améliorations vs version précédente :
- Agrège TOUTES les catégories CoinGecko qui matchent un narratif (pas
  seulement la première), en dédupliquant les cryptos communes.
- Recalibre chaque narratif sur sa vraie capitalisation totale actuelle
  (somme des market_cap réels des catégories matchées) — gratuit, aucun
  appel API supplémentaire, juste plus précis.
- Support optionnel d'une clé API CoinGecko "Demo" (gratuite) via la
  variable d'environnement COINGECKO_API_KEY, pour des limites de requêtes
  plus généreuses.

À lancer une seule fois (ou occasionnellement) pour peupler l'historique
passé. La mise à jour quotidienne normale (fetch_narratives.py) prend le
relais ensuite pour le jour présent uniquement.
"""
import json
import os
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
API_KEY = os.environ.get("COINGECKO_API_KEY", "").strip()
SLEEP_BETWEEN_CALLS = 0.8 if API_KEY else 1.6  # la clé Demo autorise un rythme plus rapide


def api_get(path, params=None, retries=3):
    qs = ""
    if params:
        qs = "?" + "&".join(f"{k}={v}" for k, v in params.items())
    url = BASE + path + qs
    headers = {"User-Agent": "radar-crypto/1.0"}
    if API_KEY:
        headers["x-cg-demo-api-key"] = API_KEY
    req = urllib.request.Request(url, headers=headers)
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


def match_categories(all_categories, keywords):
    """Retourne TOUTES les catégories qui matchent (pas juste la première)."""
    matches = []
    for cat in all_categories:
        name = (cat.get("name") or "").lower()
        cid = (cat.get("id") or "").lower()
        for kw in keywords:
            if kw.lower() in name or kw.lower() in cid:
                matches.append(cat)
                break
    return matches


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    narratives = config["narratives"]
    days = config.get("backfill_days", 180)
    coins_per_category = config.get("backfill_coins_per_narrative", 15)

    if API_KEY:
        print("Clé API CoinGecko détectée — rythme accéléré.")
    else:
        print("Pas de clé API — rythme prudent (ajoutez COINGECKO_API_KEY pour accélérer).")

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
        matched_cats = match_categories(all_categories, n["keywords"])
        if not matched_cats:
            print(f"[{name}] aucune catégorie trouvée, ignoré.")
            continue

        cat_ids = [c["id"] for c in matched_cats]
        actual_total_today = sum(c.get("market_cap") or 0 for c in matched_cats)
        print(f"[{name}] {len(cat_ids)} catégorie(s) CoinGecko: {', '.join(cat_ids)} (cap. réelle: ${actual_total_today:,.0f})")

        # Récupère les top coins de chaque catégorie matchée, dédupliqués
        seen_coin_ids = set()
        coins = []
        for cat_id in cat_ids:
            batch = api_get("/coins/markets", {
                "vs_currency": "usd", "category": cat_id,
                "order": "market_cap_desc", "per_page": coins_per_category, "page": 1
            })
            time.sleep(SLEEP_BETWEEN_CALLS)
            if not batch:
                continue
            for coin in batch:
                if coin["id"] not in seen_coin_ids:
                    seen_coin_ids.add(coin["id"])
                    coins.append(coin)

        if not coins:
            print(f"[{name}] aucune crypto trouvée, ignoré.")
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

        if not per_date_sum:
            print(f"[{name}] aucune donnée historique récupérée, ignoré.")
            continue

        # Recalibrage sur la vraie capitalisation totale du jour (gratuit, précis)
        most_recent_date = max(per_date_sum.keys())
        approx_today = per_date_sum[most_recent_date]
        scale = (actual_total_today / approx_today) if approx_today > 0 else 1.0

        print(f"[{name}] {len(per_date_sum)} jours · {len(coins)} cryptos · calibrage x{scale:.2f}")
        for date, total in per_date_sum.items():
            history_by_date.setdefault(date, {})[name] = round(total * scale, 2)

    new_history = [{"date": d, "values": v} for d, v in history_by_date.items()]
    new_history.sort(key=lambda h: h["date"])
    new_history = new_history[-730:]

    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — historique narratifs: {len(new_history)} dates au total.")


if __name__ == "__main__":
    main()
