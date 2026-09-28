"""Subprocess bridge to the headless Node.js voronoi-treemap compute engine."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_ENGINE_SCRIPT = Path(__file__).parent / "compute_treemap.js"


def run_engine(hierarchy: dict, shape: dict, options: dict | None = None) -> dict:
    """Calls compute_treemap.js and returns the parsed result dict.

    Raises RuntimeError with the engine's stderr on failure.
    """
    payload = {
        "hierarchy": hierarchy,
        "shape": shape,
        "options": options or {},
    }
    proc = subprocess.run(
        ["node", str(_ENGINE_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"compute_treemap.js failed:\n{proc.stderr}")
    return json.loads(proc.stdout)
