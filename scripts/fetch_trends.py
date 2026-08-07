#!/usr/bin/env python3
"""
Récupère l'intérêt de recherche Google Trends pour les termes définis dans
config.json et met à jour data/trends_history.json avec les points du jour.

Utilise la librairie non-officielle `pytrends`. Google Trends limite les
requêtes à 5 mots-clés par appel : les termes sont donc traités par lots de
5, avec un terme "pivot" partagé entre lots pour rééchelonner grossièrement
les scores et les rendre comparables entre eux (approximation raisonnable,
pas une garantie mathématique).

⚠️ pytrends n'est pas une API officielle Google : elle peut casser si Google
change son site, et les IP partagées de GitHub Actions se font souvent
limiter (erreur 429). Ce script réessaie automatiquement avec des pauses
croissantes pour limiter ce risque, sans garantie à 100%.
"""
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "trends_history.json"

CHUNK_SIZE = 5
MAX_RETRIES = 4
BASE_DELAY = 45  # secondes, augmente à chaque tentative (backoff exponentiel)


def chunk_with_pivot(terms, pivot, size):
    chunks = []
    others = [t for t in terms if t != pivot]
    first = [pivot] + others[: size - 1]
    chunks.append(first)
    rest = others[size - 1 :]
    for i in range(0, len(rest), size - 1):
        chunks.append([pivot] + rest[i : i + size - 1])
    return chunks


def fetch_chunk_with_retry(pytrends, chunk, timeframe, geo):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            pytrends.build_payload(chunk, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
            return df
        except Exception as e:
            is_rate_limit = "429" in str(e) or "TooManyRequestsError" in type(e).__name__
            if attempt == MAX_RETRIES:
                print(f"[fetch_trends] Échec définitif sur {chunk} après {attempt} tentatives: {e}", file=sys.stderr)
                return None
            delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 10)
            reason = "rate-limit (429)" if is_rate_limit else str(e)
            print(f"[fetch_trends] Tentative {attempt}/{MAX_RETRIES} échouée sur {chunk} ({reason}), nouvelle tentative dans {delay:.0f}s…", file=sys.stderr)
            time.sleep(delay)
    return None


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    terms = config["trends_terms"]
    timeframe = config.get("trends_timeframe", "now 7-d")
    geo = config.get("trends_geo", "")

    if not terms:
        print("[fetch_trends] Aucun terme configuré.")
        return

    pivot = terms[0]
    chunks = chunk_with_pivot(terms, pivot, CHUNK_SIZE)

    pytrends = TrendReq(hl="fr-FR", tz=60)
    today = datetime.now(timezone.utc).date().isoformat()

    all_values = {}
    pivot_values = []

    for i, chunk in enumerate(chunks):
        df = fetch_chunk_with_retry(pytrends, chunk, timeframe, geo)
        if df is None or df.empty:
            continue
        last_row = df.iloc[-1]
        chunk_pivot_val = float(last_row.get(pivot, 0) or 0)
        pivot_values.append(chunk_pivot_val)
        for term in chunk:
            if term in last_row:
                all_values[term] = {"raw": float(last_row[term]), "chunk_pivot": chunk_pivot_val}
        if i < len(chunks) - 1:
            time.sleep(random.uniform(8, 15))  # pause entre lots, même en cas de succès

    reference = pivot_values[0] if pivot_values else None
    final_values = {}
    for term, info in all_values.items():
        scale = (reference / info["chunk_pivot"]) if (reference and info["chunk_pivot"] > 0) else 1.0
        final_values[term] = round(info["raw"] * scale, 1)

    if not final_values:
        print("[fetch_trends] Aucune donnée récupérée après retries, abandon pour aujourd'hui (réessai demain).", file=sys.stderr)
        sys.exit(1)

    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history = []

    history = [h for h in history if h["date"] != today]
    history.append({"date": today, "values": final_values})
    history.sort(key=lambda h: h["date"])
    history = history[-730:]

    HISTORY_PATH.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[fetch_trends] OK — {len(final_values)} termes mis à jour pour {today} ({len(final_values)}/{len(terms)} récupérés)")


if __name__ == "__main__":
    main()
