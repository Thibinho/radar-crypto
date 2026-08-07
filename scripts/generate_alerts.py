#!/usr/bin/env python3
"""
Génère data/alerts.json à partir des données déjà collectées (aucun appel
API supplémentaire) :

1. "movers" — narratifs SUIVIS dont la capitalisation a bougé fortement
   (au-delà du seuil movement_alert_threshold_pct) sur les 7 derniers jours.

2. "emerging" — catégories CoinGecko NON suivies dont la capitalisation
   croît rapidement (au-delà de emerging_growth_threshold_pct) et dépasse
   un plancher minimum (emerging_min_market_cap), détectées en comparant
   les instantanés complets sauvegardés par fetch_narratives.py.

À lancer après fetch_narratives.py (qui alimente les deux fichiers sources).
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"
HISTORY_PATH = ROOT / "data" / "narratives_history.json"
SNAPSHOT_PATH = ROOT / "data" / "categories_snapshot_history.json"
ALERTS_PATH = ROOT / "data" / "alerts.json"


def find_nearest_snapshot(snap_history, target_date):
    """Retourne le snapshot dont la date est la plus proche (<=) de target_date."""
    candidates = [s for s in snap_history if s["date"] <= target_date]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s["date"])


def compute_movers(config):
    threshold = config.get("movement_alert_threshold_pct", 15)
    if not HISTORY_PATH.exists():
        return []
    history = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    if len(history) < 2:
        return []

    today_entry = history[-1]
    today_date = today_entry["date"]
    week_ago_target = (datetime.fromisoformat(today_date) - timedelta(days=7)).date().isoformat()
    past_entries = [h for h in history if h["date"] <= week_ago_target]
    past_entry = past_entries[-1] if past_entries else history[0]

    movers = []
    for name, current_val in today_entry.get("values", {}).items():
        past_val = past_entry.get("values", {}).get(name)
        if not past_val:
            continue
        change_pct = ((current_val / past_val) - 1) * 100
        if abs(change_pct) >= threshold:
            movers.append({
                "name": name,
                "change_pct": round(change_pct, 1),
                "direction": "up" if change_pct > 0 else "down",
                "market_cap": current_val,
            })
    movers.sort(key=lambda m: abs(m["change_pct"]), reverse=True)
    return movers


def compute_emerging(config):
    growth_threshold = config.get("emerging_growth_threshold_pct", 25)
    min_cap = config.get("emerging_min_market_cap", 50_000_000)
    lookback_days = config.get("emerging_lookback_days", 7)

    if not SNAPSHOT_PATH.exists():
        return []
    snap_history = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    if len(snap_history) < 2:
        return []

    tracked_keywords = []
    config_narratives = json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("narratives", [])
    for n in config_narratives:
        tracked_keywords.extend([kw.lower() for kw in n["keywords"]])

    today_snap = snap_history[-1]
    target_date = (datetime.fromisoformat(today_snap["date"]) - timedelta(days=lookback_days)).date().isoformat()
    past_snap = find_nearest_snapshot(snap_history[:-1], target_date)
    if not past_snap:
        return []

    emerging = []
    for cat_id, info in today_snap["categories"].items():
        name_lower = info["name"].lower()
        if any(kw in name_lower or kw in cat_id.lower() for kw in tracked_keywords):
            continue  # déjà suivi, on ignore
        current_cap = info["market_cap"]
        if current_cap < min_cap:
            continue
        past_info = past_snap["categories"].get(cat_id)
        if not past_info or not past_info.get("market_cap"):
            continue
        past_cap = past_info["market_cap"]
        change_pct = ((current_cap / past_cap) - 1) * 100
        if change_pct >= growth_threshold:
            emerging.append({
                "name": info["name"],
                "change_pct": round(change_pct, 1),
                "market_cap": current_cap,
            })

    emerging.sort(key=lambda e: e["change_pct"], reverse=True)
    return emerging[:5]


def main():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    movers = compute_movers(config)
    emerging = compute_emerging(config)

    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "movers": movers,
        "emerging": emerging,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[generate_alerts] OK — {len(movers)} mouvement(s) fort(s), {len(emerging)} narratif(s) émergent(s)")


if __name__ == "__main__":
    main()
