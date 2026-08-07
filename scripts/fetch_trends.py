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
change son site. Si ce script échoue, le tableau de bord reste utilisable
avec les autres sources / l'import CSV manuel.
"""
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from pytrends.request import TrendReq

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "trends_history.json"

CHUNK_SIZE = 5


def chunk_with_pivot(terms, pivot, size):
    """Découpe `terms` en lots de taille `size`, chaque lot (sauf le premier)
    inclut `pivot` en plus pour permettre le rééchelonnage."""
    chunks = []
    others = [t for t in terms if t != pivot]
    first = [pivot] + others[: size - 1]
    chunks.append(first)
    rest = others[size - 1 :]
    for i in range(0, len(rest), size - 1):
        chunks.append([pivot] + rest[i : i + size - 1])
    return chunks


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

    all_values = {}   # term -> raw last-day value
    pivot_values = []  # pivot value observed in each chunk, for rescaling

    for chunk in chunks:
        try:
            pytrends.build_payload(chunk, timeframe=timeframe, geo=geo)
            df = pytrends.interest_over_time()
        except Exception as e:
            print(f"[fetch_trends] Erreur sur le lot {chunk}: {e}", file=sys.stderr)
            continue
        if df.empty:
            continue
        last_row = df.iloc[-1]
        chunk_pivot_val = float(last_row.get(pivot, 0) or 0)
        pivot_values.append(chunk_pivot_val)
        for term in chunk:
            if term in last_row:
                all_values[term] = {"raw": float(last_row[term]), "chunk_pivot": chunk_pivot_val}
        time.sleep(1)  # anti rate-limit

    # rescale using the first chunk's pivot value as the reference
    reference = pivot_values[0] if pivot_values else None
    final_values = {}
    for term, info in all_values.items():
        if reference and info["chunk_pivot"] > 0:
            scale = reference / info["chunk_pivot"]
        else:
            scale = 1.0
        final_values[term] = round(info["raw"] * scale, 1)

    if not final_values:
        print("[fetch_trends] Aucune donnée récupérée, abandon.", file=sys.stderr)
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
    print(f"[fetch_trends] OK — {len(final_values)} termes mis à jour pour {today}")


if __name__ == "__main__":
    main()
