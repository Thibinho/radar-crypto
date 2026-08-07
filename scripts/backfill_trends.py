#!/usr/bin/env python3
"""
Récupère l'historique complet (plusieurs mois) de l'intérêt Google Trends
pour les termes définis dans config.json, et remplit data/trends_history.json.

Contrairement à fetch_trends.py (qui ne prend que le point du jour),
ce script récupère toute une plage de dates en un seul appel par lot de
termes — Google Trends fournit nativement l'historique passé.

À lancer une seule fois (ou occasionnellement) pour peupler le passé.
La mise à jour quotidienne normale (fetch_trends.py) prend le relais
ensuite pour ajouter un point chaque jour.
"""
import json
import random
import sys
import time
from pathlib import Path

from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "trends_history.json"

CHUNK_SIZE = 5
MAX_RETRIES = 4
BASE_DELAY = 45


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
            return pytrends.interest_over_time()
        except Exception as e:
            if attempt == MAX_RETRIES:
                print(f"[backfill_trends] Échec définitif sur {chunk}: {e}", file=sys.stderr)
                return None
            delay = BASE_DELAY * (2 ** (attempt - 1)) + random.uniform(0, 10)
            print(f"[backfill_trends] Tentative {attempt}/{MAX_RETRIES} échouée sur {chunk} ({e}), retry dans {delay:.0f}s…", file=sys.stderr)
            time.sleep(delay)
    return None


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    terms = config["trends_terms"]
    geo = config.get("trends_geo", "")
    backfill_timeframe = config.get("backfill_trends_timeframe", "today 12-m")

    if not terms:
        print("Aucun terme configuré.")
        return

    pivot = terms[0]
    chunks = chunk_with_pivot(terms, pivot, CHUNK_SIZE)

    pytrends = TrendReq(hl="fr-FR", tz=60)

    chunk_dfs = []
    for i, chunk in enumerate(chunks):
        df = fetch_chunk_with_retry(pytrends, chunk, backfill_timeframe, geo)
        chunk_dfs.append(df)
        if i < len(chunks) - 1:
            time.sleep(random.uniform(10, 20))

    if HISTORY_PATH.exists():
        history_list = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history_list = []
    history_by_date = {h["date"]: h.get("values", {}) for h in history_list}

    reference_series = None
    for i, (chunk, df) in enumerate(zip(chunks, chunk_dfs)):
        if df is None or df.empty:
            continue
        df = df.copy()
        df.index = df.index.date.astype(str)

        if i == 0:
            reference_series = df[pivot]
            scale = 1.0
        else:
            ratios = []
            for date in df.index:
                if date in reference_series.index:
                    ref_val = reference_series.loc[date]
                    cur_val = df.loc[date, pivot]
                    if cur_val and cur_val > 0:
                        ratios.append(ref_val / cur_val)
            scale = (sum(ratios) / len(ratios)) if ratios else 1.0

        for term in chunk:
            if term not in df.columns:
                continue
            for date, val in df[term].items():
                scaled = round(float(val) * scale, 1)
                history_by_date.setdefault(date, {})[term] = scaled

    new_history = [{"date": d, "values": v} for d, v in history_by_date.items()]
    new_history.sort(key=lambda h: h["date"])
    new_history = new_history[-730:]

    if len(new_history) == 0:
        print("Aucune donnée récupérée, abandon.", file=sys.stderr)
        sys.exit(1)

    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK — historique trends: {len(new_history)} dates au total.")


if __name__ == "__main__":
    main()
