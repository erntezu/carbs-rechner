"""Brücke zwischen Browser (JavaScript) und carbs_logik.py. Läuft in Pyodide und in CPython (Tests).

Alle Funktionen nehmen und liefern JSON-Text; numpy-Werte werden in einfache Python-Typen umgewandelt.
"""

import json
import math

import numpy as np

import carbs_logik as cl


def _einfach(o):
    if isinstance(o, dict):
        return {str(k): _einfach(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_einfach(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        o = float(o)
        return o if math.isfinite(o) else None
    return o


def normalisieren(text):
    """Roh-Plan (JSON) -> vollständiger, typsicherer Plan (JSON)."""
    return json.dumps(_einfach(cl.plan_normalisieren(json.loads(text))))


def berechnen(text):
    """Plan (JSON) -> Ergebnis von plan_berechnen (JSON)."""
    return json.dumps(_einfach(cl.plan_berechnen(json.loads(text))))
