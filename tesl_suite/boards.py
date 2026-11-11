"""New boards (playmats). A mod board re-skins one of the game's five boards: its painted table (2048 x 1024, 2:1) is your
image; the base board's 3D props stay. "rotation" adds it to the random board choice; "replace" always shows it instead of
that base. Players can also force one board in the offline game's F10 menu.

Layout: mods/<id>/boards/boards.json + <slug>.png.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

BASES = {"Original": "AppBase/CDGameBoard/Textures/Playmat_01_D", "IsleOfMadness": "ContentPack001/Textures/Gameboard/IOM_Playmat_01_D",
         "AllianceWar": "ContentPack003/Textures/Gameboards/AllianceWar/Playmat_AW_01_D",
         "Elsweyr": "ContentPack007/Textures/Gameboard/Elsweyr/ELS_Playmat_01_D", "RealmsOfOblivion": "ContentPack010/Textures/Gameboard/OC_Playmat_01"}
SIZES = {2048: (2048, 1024), 4096: (4096, 2048)}


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "boards" / "boards.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "boards": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def new_board(mod_id: str, name: str, image: str | None = None, base: str = "Original", mode: str = "rotation", size: int = 2048) -> dict:
    """A board on one of the five bases. Without an image the base's own table stays (a board of edits only:
    tesl_suite.board_edit)."""
    from PIL import Image
    read_mod(mod_id)
    if base not in BASES:
        raise ValueError(f"base must be one of {', '.join(BASES)}")
    if mode not in ("rotation", "replace"):
        raise ValueError("mode must be rotation or replace")
    if size not in SIZES:
        raise ValueError("size must be 2048 or 4096")
    slug = slugify(name)
    manifest = _read(mod_id)
    old = next((b for b in manifest["boards"] if b["slug"] == slug), None)
    if not image:
        entry = {"slug": slug, "name": name, "base": base, "mode": mode}
        if old and old.get("edits"):
            entry["edits"] = old["edits"]
        manifest["boards"] = [b for b in manifest["boards"] if b["slug"] != slug] + [entry]
        _write(mod_id, manifest)
        return {"mod": mod_id, "board": {**entry, "game_key": f"{mod_id}/{slug}"}, "total": len(manifest["boards"])}
    src = Path(image)
    if not src.is_file():
        raise ValueError(f"Image not found: {image}")
    tw, th = SIZES[size]
    img = Image.open(src).convert("RGB")
    w, h = img.size
    scale = max(tw / w, th / h)
    r = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (r.width - tw) // 2, (r.height - th) // 2
    dest = mod_dir(mod_id) / "boards" / f"{slug}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)
    r.crop((left, top, left + tw, top + th)).save(dest)
    entry = {"slug": slug, "name": name, "base": base, "mode": mode, "image": dest.name}
    if old and old.get("edits"):
        entry["edits"] = old["edits"]                    # re-painting keeps the board's edits
    manifest["boards"] = [b for b in manifest["boards"] if b["slug"] != slug] + [entry]
    _write(mod_id, manifest)
    return {"mod": mod_id, "board": {**entry, "size": [tw, th], "game_key": f"{mod_id}/{slug}"}, "total": len(manifest["boards"])}


def list_boards(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "boards": _read(mod_id)["boards"], "bases": list(BASES)}


def remove(mod_id: str, name: str) -> dict:
    manifest = _read(mod_id)
    slug = slugify(name)
    gone = [b for b in manifest["boards"] if b["slug"] in (slug, name)]
    if not gone:
        raise ValueError(f"{mod_id} has no board '{name}'")
    manifest["boards"] = [b for b in manifest["boards"] if b not in gone]
    for b in gone:
        f = mod_dir(mod_id) / "boards" / b.get("image", "")
        if b.get("image") and f.is_file():
            trash(f, mod_id)
        files = mod_dir(mod_id) / "boards" / b["slug"]
        if files.is_dir():
            import shutil
            trash(files, mod_id)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(manifest["boards"])}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors = []
    for b in _read(mod_id)["boards"]:
        if b.get("base") not in BASES:
            errors.append(f"board {b['slug']}: unknown base {b.get('base')}")
        if b.get("image") and not (mod_dir(mod_id) / "boards" / b["image"]).is_file():
            errors.append(f"board {b['slug']}: missing image")
    from . import board_edit
    errors += board_edit.check(mod_id)
    return errors, []
