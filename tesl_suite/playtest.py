"""Play test: start TESL: Everlasting with a mod enabled, then read back what the game loaded.

The engine writes `.offline-user-data/mod-report.json` in the game folder each time it loads mods: the mods it loaded (in
order), what each one brought, and every problem (a skipped mod and why, a missing image, an unknown card in a deck ...).
Forge only reads that file; it never writes inside the game folder.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from .game import GameInstall

EXE = "The Elder Scrolls Legends.exe"


def _report_path(game: GameInstall) -> Path:
    return Path(game.root) / ".offline-user-data" / "mod-report.json"


def running() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", f"IMAGENAME eq {EXE}", "/NH"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return EXE.lower() in out.lower()


def report(game: GameInstall, mod_id: str | None = None) -> dict:
    """The game's last mod-load report; with mod_id, only what concerns that mod."""
    p = _report_path(game)
    if not p.is_file():
        return {"available": False, "running": running(), "note": "No report yet: start the game once with TESL: Everlasting (Play test does this)."}
    try:
        r = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        return {"available": False, "running": running(), "note": f"The report could not be read ({e})."}
    r["available"] = True
    r["running"] = running()
    r["age_seconds"] = max(0, int(time.time() - p.stat().st_mtime))
    if mod_id:
        r["loaded_this"] = mod_id in r.get("loaded", [])
        r["problems"] = [x for x in r.get("problems", []) if x.startswith(mod_id + ":") or x.startswith(mod_id + "/") or f"\\{mod_id}" in x or f"/{mod_id}" in x]
    return r


def launch(game: GameInstall, mod_id: str | None = None, enable: bool = True) -> dict:
    """Enable the mod (if asked) and start the game offline. Returns the checks made before starting."""
    from . import mods
    notes = []
    if mod_id:
        v = mods.validate(game, mod_id)
        if not v["valid"]:
            raise ValueError(f"{mod_id} has problems to fix first: " + "; ".join(v["errors"][:5]))
        notes += v["warnings"][:5]
        if enable and not next((m["enabled"] for m in mods.list_mods() if m["id"] == mod_id), False):
            mods.set_enabled(mod_id, True)
            notes.append(f"{mod_id} enabled")
    if running():
        return {"started": False, "notes": notes + ["The game is already running: quit it and press Play test again so it loads the mod changes."]}
    exe = Path(game.root) / EXE
    if not exe.is_file():
        raise ValueError(f"Game not found at {exe}")
    before = _report_path(game).stat().st_mtime if _report_path(game).is_file() else 0
    subprocess.Popen([str(exe), "--tesl-offline-native"], cwd=game.root, close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
    return {"started": True, "report_before": before, "notes": notes + ["Starting TESL: Everlasting. The load report appears here once the game reaches its menu."]}
