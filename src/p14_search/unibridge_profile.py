"""UniBridge profile: the same engine and code as P14, pointed at the UniBridge corpus.

Only storage locations and the principals file differ (own SQLite file, own Qdrant collection, own roles).
The insufficient-evidence thresholds are read from eval/results/unibridge/calibration.json, written by
eval/unibridge/calibrate.py on the tuning split only (0 = never flag, when not calibrated yet).
"""

from __future__ import annotations

import json
from pathlib import Path

from p14_search.config import Settings, get_settings

ROOT = Path(__file__).resolve().parents[2]
CALIBRATION = ROOT / "eval" / "results" / "unibridge" / "calibration.json"
OVERRIDES = {
    "sqlite_path": Path("data/processed/unibridge.sqlite"),
    "qdrant_collection": "unibridge_passages",
    "principals_path": Path("config/principals_unibridge.json"),
    "display_system": "S2",
    "shadow_system": None,
}


def unibridge_settings(base: Settings | None = None) -> Settings:
    update = dict(OVERRIDES)
    if CALIBRATION.exists():
        cal = json.loads(CALIBRATION.read_text(encoding="utf-8"))
        update.update(ie_min_dense=cal["ie_min_dense"], ie_min_bm25=cal["ie_min_bm25"])
    else:
        update.update(ie_min_dense=0.0, ie_min_bm25=0.0)
    return (base or get_settings()).model_copy(update=update)
