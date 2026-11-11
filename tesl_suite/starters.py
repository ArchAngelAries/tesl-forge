"""Starters: new mods that begin with something to edit instead of an empty folder.

- "blank": an empty mod.
- "copy": a full copy of another mod (the sample mod makes a complete starter pack: cards, decks, avatars, card backs,
  boards, music, modes, stories, AI opponents). The copy gets its own ids, so the two can be enabled together: card ids are
  regenerated and every reference to them (decks) follows; "<old>/..." and "mod.<old>...." references become the new id.
- kits that add one first item to edit: "card" (a new card copied from an original), "story", "mode",
  "opponent".
"""
from __future__ import annotations

import json
import shutil

from .fsutil import atomic_write
from .mods import all_mod_ids, fnv32, mod_cards, mod_dir, new_mod, read_mod

KINDS = {
    "blank": "Empty mod",
    "copy": "Copy of a mod (the sample mod is a complete starter pack)",
    "card": "A first card (a copy of Fiery Imp to change)",
    "story": "A first story (one act, chapter, dialogue and battle)",
    "mode": "A first game mode",
    "opponent": "A first AI opponent",
}
SKIP_COPY = {"history", "trash"}


def _retarget(value, old: str, new: str, ids: dict):
    """Walk a JSON value: mod-id prefixes become the new id; card ids follow the id map (under id/Id/resourceId keys)."""
    if isinstance(value, dict):
        return {k: (ids.get(v, v) if k in ("id", "Id", "resourceId") and isinstance(v, int) else _retarget(v, old, new, ids)) for k, v in value.items()}
    if isinstance(value, list):
        return [_retarget(v, old, new, ids) for v in value]
    if isinstance(value, str):
        for a, b in ((f"{old}/", f"{new}/"), (f"mod.{old}.", f"mod.{new}."), (f"MOD:{old}/", f"MOD:{new}/"), (f"MOD:opponent:{old}/", f"MOD:opponent:{new}/")):
            if value.startswith(a):
                return b + value[len(a):]
        return value
    return value


def copy_mod(source: str, mod_id: str, name: str, author: str = "", description: str = "") -> dict:
    src_meta = read_mod(source)
    new_mod(mod_id, name, author, description or src_meta.get("description", ""))
    src, dst = mod_dir(source), mod_dir(mod_id)
    for item in src.iterdir():
        if item.name == "mod.json" or item.name in SKIP_COPY:
            continue
        if item.is_dir():
            shutil.copytree(item, dst / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dst / item.name)
    # New card ids: same rule as new cards (fnv32 of mod/slug, salted past any id in use).
    taken = {c["ResourceId"]["Id"] for m in all_mod_ids() if m != mod_id for c in mod_cards(m)}
    ids = {}
    for c in mod_cards(source):
        slug = c["ResourceId"]["UniqueName"]
        salt, cid = 0, fnv32(f"tesl-mod:{mod_id}/{slug}")
        while cid in taken or cid in (0, -1):
            salt += 1
            cid = fnv32(f"tesl-mod:{mod_id}/{slug}#{salt}")
        taken.add(cid)
        ids[c["ResourceId"]["Id"]] = cid
    changed = 0
    for p in dst.rglob("*.json"):
        try:
            text = p.read_text(encoding="utf-8")
            data = json.loads(text)
        except (OSError, ValueError):
            continue
        out = _retarget(data, source, mod_id, ids)
        if out != data:
            atomic_write(p, json.dumps(out, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
            changed += 1
    meta = read_mod(mod_id)
    for k in ("requires_engine", "dependencies", "conflicts", "load_after", "load_before"):
        if k in src_meta:
            meta[k] = src_meta[k]
    meta["based_on"] = f"{source} {src_meta.get('version', '')}".strip()
    atomic_write(dst / "mod.json", json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"mod": meta, "copied_from": source, "cards": len(ids), "files_retargeted": changed}


def create(game, mod_id: str, name: str, kind: str = "blank", author: str = "", description: str = "", source: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"starter must be one of {', '.join(KINDS)}")
    if kind == "copy":
        if not source:
            raise ValueError("choose the mod to copy")
        return {**copy_mod(source, mod_id, name, author, description), "starter": kind}
    out = {**new_mod(mod_id, name, author, description), "starter": kind}
    try:
        if kind == "card":
            from . import mods
            card = mods.new_card(game, mod_id, "My First Card", "Fiery Imp")
            out["first"] = {"card": "My First Card", "template": "Fiery Imp", "result": card}
        elif kind == "story":
            from . import stories
            out["first"] = stories.new_story(mod_id, "My First Story", "Edit me on the Stories page.")
        elif kind == "mode":
            from . import modes
            out["first"] = modes.save_mode(game, mod_id, "My First Mode", "Edit me on the Game modes page.")
        elif kind == "opponent":
            from . import opponents
            out["first"] = opponents.save_opponent(mod_id, {"name": "My First Opponent", "title": "Edit me on the AI opponents page",
                                                             "portrait": "asset:ContentPack000/Images/AIPortraits/DBH_Opponent_Portraits/DBH_NPC_CRDL_02_284_avatar_png"})
    except Exception as e:   # the mod exists either way; say what could not be added
        out["note"] = f"The mod was created, but its first {kind} could not be added: {e}"
    return out


def kinds() -> dict:
    return {"kinds": [{"kind": k, "label": v} for k, v in KINDS.items()], "mods": all_mod_ids()}
