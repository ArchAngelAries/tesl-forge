"""Bulk import: many items in one go.

- cards_csv: a spreadsheet of new cards, one per row. Columns (header row, any order; only name and template needed):
  name, template (an original card to copy rules from), cost, power, health, rarity, text, art (a picture file name, found
  among the uploaded files or next to the CSV), unique (yes/no). Existing cards of the same name are updated instead.
- art_by_name: many pictures; each file is matched to a card by its file name ("Whiterun Wolfcaller.png",
  "whiterun-wolfcaller.jpg"). A mod card gets it as its art; an original card gets a remastered art replacement.
- music: many audio files as soundtrack tracks for the chosen moments.
Each run is one undo step (Ctrl+Z in the app). Rows that fail are reported and the rest still import.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from .mods import mod_cards, read_mod, slugify

YES = {"yes", "y", "true", "1", "x"}


def _num(v):
    v = (v or "").strip()
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        raise ValueError(f"'{v}' is not a number")


def _find_file(name: str, files: dict[str, str], base: Path | None) -> str | None:
    if not name:
        return None
    key = name.strip().lower()
    for k, path in files.items():
        if k.lower() == key or Path(k).stem.lower() == Path(key).stem.lower():
            return path
    if base is not None and (base / name).is_file():
        return str(base / name)
    raise ValueError(f"art file '{name}' not found among the uploaded files")


def cards_csv(game, mod_id: str, text: str, files: dict[str, str] | None = None, base: str | None = None) -> dict:
    """files: {original file name: uploaded path} for art pictures."""
    from . import edits, mods
    read_mod(mod_id)
    files = files or {}
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        raise ValueError("the CSV has no rows (the first row must name the columns: name, template, cost, power, health, ...)")
    cols = {c.strip().lower(): c for c in rows[0].keys() if c}
    if "name" not in cols:
        raise ValueError("the CSV needs a 'name' column")
    get = lambda r, k: (r.get(cols[k]) or "").strip() if k in cols else ""
    existing = {c.get("Name", "").lower(): c["ResourceId"]["UniqueName"] for c in mod_cards(mod_id)}
    done, failed = [], []
    for i, r in enumerate(rows, start=2):
        name = get(r, "name")
        if not name:
            continue
        try:
            art = _find_file(get(r, "art"), files, Path(base) if base else None)
            unique = (get(r, "unique").lower() in YES) if get(r, "unique") else None
            stats = dict(cost=_num(get(r, "cost")), attack=_num(get(r, "power") or get(r, "attack")), health=_num(get(r, "health")),
                         text=get(r, "text") or None, rarity=get(r, "rarity").title() or None, art=art, unique=unique)
            if name.lower() in existing:
                edits.edit_card(game, mod_id, existing[name.lower()], **stats)
                done.append({"row": i, "card": name, "action": "updated"})
            else:
                template = get(r, "template")
                if not template:
                    raise ValueError("a new card needs a 'template' (an original card to copy rules from)")
                mods.new_card(game, mod_id, name, template, **stats)
                done.append({"row": i, "card": name, "action": "created"})
        except Exception as e:
            failed.append({"row": i, "card": name, "error": str(e)})
    return {"mod": mod_id, "imported": len(done), "failed": failed, "rows": done}


def art_by_name(game, mod_id: str, files: dict[str, str]) -> dict:
    """files: {original file name: uploaded path}. Mod cards get new art; original cards get a replacement."""
    from . import edits, replace
    from .mods import _original_cards
    read_mod(mod_id)
    mine = {}
    for c in mod_cards(mod_id):
        mine[slugify(c.get("Name", ""))] = c["ResourceId"]["UniqueName"]
    originals = {slugify(c.get("Name", "")): c.get("Name") for c in _original_cards(game).values() if c.get("Name")}
    done, failed = [], []
    for fname, path in files.items():
        key = slugify(Path(fname).stem)
        try:
            if key in mine:
                edits.edit_card(game, mod_id, mine[key], art=path)
                done.append({"file": fname, "card": mine[key], "action": "mod card art"})
            elif key in originals:
                replace.add(game, mod_id, path, card=originals[key])
                done.append({"file": fname, "card": originals[key], "action": "original card art replaced"})
            else:
                failed.append({"file": fname, "error": "no card with this name (name the file after the card)"})
        except Exception as e:
            failed.append({"file": fname, "error": str(e)})
    return {"mod": mod_id, "imported": len(done), "failed": failed, "rows": done}


def music(mod_id: str, files: dict[str, str], contexts: list[str], mode: str = "rotation") -> dict:
    from . import music as _music
    read_mod(mod_id)
    if not contexts:
        raise ValueError("choose at least one moment for the tracks to play at")
    done, failed = [], []
    for fname, path in files.items():
        try:
            _music.add_track(mod_id, Path(fname).stem.replace("_", " ").replace("-", " ").strip() or "Track", path, contexts, mode)
            done.append({"file": fname})
        except Exception as e:
            failed.append({"file": fname, "error": str(e)})
    return {"mod": mod_id, "imported": len(done), "failed": failed, "rows": done}


def template_csv() -> str:
    return ("name,template,cost,power,health,rarity,text,art,unique\n"
            "Riften Cutpurse,Fiery Imp,2,2,1,Common,,riften-cutpurse.png,no\n")
