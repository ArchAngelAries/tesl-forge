"""Game-audio support (FMOD) for the installed TESL Forge.

Decoding the game's own sounds needs the FMOD Engine library (fmod.dll, proprietary, Firelight Technologies). Its free
licence doesn't let us redistribute it in TESL Forge (see NOTICE.md), so the installed app ships without it. On request
(the user clicks "Get game-audio support"), it downloads the same fmod_toolkit package that `pip` installs in the zip
version, from PyPI, verifies its SHA-256 from PyPI's own listing, and keeps only fmod.dll in
Documents/TESL Forge/runtime/fmod/, used on this computer only. Everything else in TESL Forge works without it.
Credit: audio decoding uses FMOD Studio by Firelight Technologies Pty Ltd (through fmod_toolkit), when installed.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

from .game import FROZEN, SUITE_ROOT

PACKAGE, VERSION = "fmod-toolkit", "0.1.3"   # the version TESL Forge is tested with (requirements: via UnityPy)
MEMBER = "fmod_toolkit/libfmod/Windows/x64/fmod.dll"


def dll() -> Path:
    return SUITE_ROOT / "runtime" / "fmod" / "fmod.dll"


def _bundled() -> Path | None:
    """fmod_toolkit's own copy (the zip version: installed by pip on this computer)."""
    # found without importing it: importing loads fmod.dll at once and fails when it is missing
    try:
        import importlib.util
        spec = importlib.util.find_spec("fmod_toolkit")
        if spec is None or not spec.origin:
            return None
        p = Path(spec.origin).parent / "libfmod" / "Windows" / "x64" / "fmod.dll"
        return p if p.is_file() else None
    except Exception:
        return None


def apply() -> bool:
    """Point fmod_toolkit at a downloaded fmod.dll when there is one. Returns whether game audio can be decoded."""
    if dll().is_file():
        os.environ["PYFMODEX_DLL_PATH"] = str(dll())
        return True
    return _bundled() is not None


def status() -> dict:
    return {"available": apply(), "downloaded": dll().is_file(), "installed_app": FROZEN,
            "source": f"https://pypi.org/project/{PACKAGE}/{VERSION}/"}


def install() -> dict:
    """Download fmod_toolkit from PyPI (on the user's request), verify it, keep fmod.dll."""
    with urllib.request.urlopen(f"https://pypi.org/pypi/{PACKAGE}/{VERSION}/json", timeout=30) as r:
        info = json.load(r)
    files = [f for f in info.get("urls", []) if f.get("packagetype") == "bdist_wheel"]
    files.sort(key=lambda f: ("win_amd64" not in f["filename"], f["filename"]))   # a Windows wheel first, else a universal one
    for f in files:
        with urllib.request.urlopen(f["url"], timeout=120) as r:
            data = r.read()
        if hashlib.sha256(data).hexdigest() != f.get("digests", {}).get("sha256"):
            raise ValueError(f"{f['filename']}: checksum does not match PyPI's listing; nothing was kept")
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if MEMBER not in z.namelist():
                continue
            target = dll()
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(z.read(MEMBER))
            tmp.replace(target)
            (target.parent / "SOURCE.txt").write_text(
                f"fmod.dll from {f['filename']} ({f['url']}), sha256 of the wheel {f['digests']['sha256']}.\n"
                "FMOD Engine by Firelight Technologies Pty Ltd; proprietary, used on this computer only (https://www.fmod.com/legal).\n",
                encoding="utf-8")
            apply()
            return {**status(), "file": f["filename"]}
    raise ValueError("PyPI has no fmod_toolkit wheel with a Windows fmod.dll")
