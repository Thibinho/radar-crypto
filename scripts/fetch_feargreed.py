#!/usr/bin/env python3
"""
Récupère le Fear & Greed Index crypto (API gratuite alternative.me,
aucune clé nécessaire) et met à jour data/feargreed.json.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parent.parent
HISTORY_PATH = ROOT / "data" / "feargreed.json"
API_URL = "https://api.alternative.me/fng/?limit=30"


def main():
    req = urllib.request.Request(API_URL, headers={"User-Agent": "radar-crypto/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"[fetch_feargreed] Erreur réseau: {e}", file=sys.stderr)
        sys.exit(1)

    entries = payload.get("data", [])
    if not entries:
        print("[fetch_feargreed] Réponse vide, abandon.", file=sys.stderr)
        sys.exit(1)

    if HISTORY_PATH.exists():
        history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    else:
        history = []
    history_by_date = {h["date"]: h for h in history}

    for e in entries:
        date = datetime.fromtimestamp(int(e["timestamp"]), tz=timezone.utc).date().isoformat()
        history_by_date[date] = {
            "date": date,
            "value": int(e["value"]),
            "classification": e.get("value_classification", ""),
        }

    new_history = list(history_by_date.values())
    new_history.sort(key=lambda h: h["date"])
    new_history = new_history[-730:]

    HISTORY_PATH.write_text(json.dumps(new_history, ensure_ascii=False, indent=2), encoding="utf-8")
    latest = new_history[-1]
    print(f"[fetch_feargreed] OK — aujourd'hui: {latest['value']} ({latest['classification']})")


if __name__ == "__main__":
    main()
