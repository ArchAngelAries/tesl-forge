"""User settings of this computer: workspace/settings.json in the Forge home (never shipped, never shared).

  game_dirs   extra TESL install folders (a second copy, a Bethesda.net install)   [list of folders]
  steam_dirs  extra Steam folders to look for the game (and Blender) in             [list of folders]
  blender     path to blender.exe; empty = find it automatically
  ffmpeg      path to ffmpeg; empty = find it on PATH
  ffprobe     path to ffprobe; empty = find it on PATH

Empty values mean "detect automatically". Nothing machine-specific is built into the program: every place on this
computer comes from here, from the Windows registry, from environment variables or from PATH.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

DEFAULTS = {"game_dirs": [], "steam_dirs": [], "blender": "", "ffmpeg": "", "ffprobe": ""}
LISTS = ("game_dirs", "steam_dirs")
PATHS = ("blender", "ffmpeg", "ffprobe")


def path() -> Path:
    from .game import SUITE_ROOT
    return SUITE_ROOT / "workspace" / "settings.json"


def _raw() -> dict:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load() -> dict:
    """All settings: the saved ones over the defaults (unknown keys are kept, so nothing is lost)."""
    raw = _raw()
    out = {**DEFAULTS, **raw}
    for k in LISTS:
        out[k] = [d for d in out[k] if isinstance(d, str) and d.strip()] if isinstance(out[k], list) else []
    for k in PATHS:
        out[k] = out[k].strip() if isinstance(out[k], str) else ""
    return out


def get(key: str):
    return load().get(key, DEFAULTS.get(key))


def save(changes: dict) -> dict:
    """Change some settings (only the known ones; lists are replaced as a whole). Returns all settings."""
    from .fsutil import atomic_write
    unknown = [k for k in changes if k not in DEFAULTS]
    if unknown:
        raise ValueError(f"Unknown setting {', '.join(unknown)}: one of {', '.join(DEFAULTS)}")
    data = _raw()
    for k, v in changes.items():
        if k in LISTS:
            if isinstance(v, str):
                v = [x for x in v.replace("\n", ";").split(";")]
            data[k] = [str(x).strip() for x in v if str(x).strip()]
        else:
            v = "" if v is None else str(v).strip()
            if v and not Path(v).exists():
                raise ValueError(f"{k}: '{v}' does not exist")
            data[k] = v
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return load()


def remember_game_dir(folder: str) -> None:
    dirs = [d for d in get("game_dirs") if d != folder]
    save({"game_dirs": [folder] + dirs})


# ---- finding things on this computer ---------------------------------------------------------------------------
def program_files() -> list[Path]:
    seen, out = set(), []
    for var in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
        v = os.environ.get(var)
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(Path(v))
    return out


def steam_roots() -> list[Path]:
    """Steam folders: the registry, Program Files/Steam, and the ones in the settings."""
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
    roots += [p / "Steam" for p in program_files()]
    roots += [Path(d) for d in get("steam_dirs")]
    return roots


def find_tool(name: str) -> str | None:
    """A helper program (ffmpeg, ffprobe): the setting if it works, else PATH."""
    chosen = get(name)
    if chosen and Path(chosen).is_file():
        return chosen
    return shutil.which(name)


def find_blender() -> str | None:
    chosen = get("blender")
    if chosen and Path(chosen).is_file():
        return chosen
    found = shutil.which("blender")
    if found:
        return found
    roots = [p / "Blender Foundation" for p in program_files()] + [r / "steamapps" / "common" / "Blender" for r in steam_roots()]
    exes = sorted((p for r in roots if r.is_dir() for p in r.rglob("blender.exe")), key=lambda p: p.parent.name, reverse=True)
    return str(exes[0]) if exes else None
