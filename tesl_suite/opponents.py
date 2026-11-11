"""AI opponents: in-game AI characters that play in TESL: Everlasting (offline, against the game's own AI only).

Each opponent has a name, a title line, a portrait, a deck, a difficulty and an emote personality. They play:
- in Practice: chosen in the game's F10 menu ("Practice opponent"), or, with "Mod opponents and decks in random Practice"
  on, now and then in place of the game's practice opponents;
- in game modes and story battles that name them ("ai": "<mod>/<slug>"), which then use their portrait, name, deck,
  difficulty and personality unless the battle sets its own.

portrait: a square head-and-shoulders image like the game's AI portraits (a picture is cropped to that around the head),
"avatar:<slug>" (one of this mod's avatars: its round image) or "asset:<game image path>".
deck: "practice" (the game's practice AI decks), "random", or a deck by its type name (this mod's or another enabled
mod's) or display name.
difficulty: "chosen" (what the player picked), Novice, Apprentice, Adept, Expert or Master.
temperament: Friendly, Cocky, Playful, Stoic, or "" (decided by the name, like the game's own opponents).

Layout: mods/<id>/opponents/opponents.json + <slug>.png.
"""
from __future__ import annotations

import json
from pathlib import Path

from .fsutil import atomic_write, trash
from .mods import mod_dir, read_mod, slugify

DIFFICULTIES = ("chosen", "Novice", "Apprentice", "Adept", "Expert", "Master")
TEMPERAMENTS = ("", "Friendly", "Cocky", "Playful", "Stoic")
FIELDS = ("name", "title", "portrait", "deck", "random_size", "difficulty", "temperament", "practice")


def _path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "opponents" / "opponents.json"


def _read(mod_id: str) -> dict:
    p = _path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "opponents": []}


def _write(mod_id: str, data: dict) -> None:
    p = _path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def list_opponents(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "opponents": _read(mod_id)["opponents"]}


def options(game, mod_id: str) -> dict:
    """Choices for the app's form: decks, difficulties, personalities and this mod's avatars."""
    from . import avatars, modes
    decks = [d for d in modes.decks(game, mod_id) if d["deck"] != "own"]
    return {"decks": decks, "difficulties": list(DIFFICULTIES), "temperaments": list(TEMPERAMENTS),
            "avatars": [{"slug": a["slug"], "name": a["name"]} for a in avatars.list_avatars(mod_id)["avatars"]]}


def _problems(mod_id: str, o: dict) -> list[str]:
    out = []
    if not o.get("name"):
        out.append("a name is needed")
    if o.get("difficulty", "chosen") not in DIFFICULTIES:
        out.append(f"difficulty must be one of {', '.join(DIFFICULTIES)}")
    if o.get("temperament", "") not in TEMPERAMENTS:
        out.append("personality must be Friendly, Cocky, Playful, Stoic or empty")
    rs = o.get("random_size", 30)
    if not isinstance(rs, int) or not 10 <= rs <= 100:
        out.append("random deck size must be 10-100")
    p = o.get("portrait") or ""
    if p.startswith("avatar:"):
        from . import avatars
        if p[7:] not in {a["slug"] for a in avatars.list_avatars(mod_id)["avatars"]}:
            out.append(f"no avatar '{p[7:]}' in this mod")
    elif p and not p.startswith("asset:") and not (mod_dir(mod_id) / "opponents" / p).is_file():
        out.append(f"portrait file missing: {p}")
    return out


def save_opponent(mod_id: str, fields: dict, image: str | None = None, head: float = 0.22) -> dict:
    """Create or update an opponent (by slug, else by name). image: a picture file to crop into its portrait."""
    read_mod(mod_id)
    data = _read(mod_id)
    slug = fields.get("slug") or slugify(fields.get("name") or "")
    if not slug:
        raise ValueError("a name is needed")
    old = next((o for o in data["opponents"] if o["slug"] == slug), None)
    o = dict(old or {"slug": slug, "deck": "practice", "difficulty": "chosen", "temperament": "", "practice": True})
    for k in FIELDS:
        if k in fields and fields[k] is not None:
            o[k] = fields[k]
    if "random_size" in o:
        o["random_size"] = int(o["random_size"])
    o["practice"] = bool(o.get("practice", True))
    if image:
        src = Path(image)
        if not src.is_file():
            raise ValueError(f"Image not found: {image}")
        from . import avatars
        files = avatars.crops(src, mod_dir(mod_id) / "opponents", slug, head)
        folder = mod_dir(mod_id) / "opponents"
        (folder / files["circle"]).replace(folder / f"{slug}.png")   # the square head crop is the portrait, like the game's
        o["portrait"] = f"{slug}.png"
    errs = _problems(mod_id, o)
    if errs:
        raise ValueError(f"opponent {o.get('name') or slug}: " + "; ".join(errs))
    data["opponents"] = [x for x in data["opponents"] if x["slug"] != slug] + [o]
    _write(mod_id, data)
    return {"mod": mod_id, "opponent": o, "key": f"{mod_id}/{slug}", "total": len(data["opponents"]), "created": old is None}


def remove(mod_id: str, name: str) -> dict:
    data = _read(mod_id)
    slug = slugify(name)
    gone = [o for o in data["opponents"] if o["slug"] in (slug, name) or o.get("name") == name]
    if not gone:
        raise ValueError(f"{mod_id} has no AI opponent '{name}'")
    data["opponents"] = [o for o in data["opponents"] if o not in gone]
    for o in gone:
        p = o.get("portrait") or ""
        f = mod_dir(mod_id) / "opponents" / p
        if p and ":" not in p and f.is_file() and not any(x.get("portrait") == p for x in data["opponents"]):
            trash(f, mod_id)
    _write(mod_id, data)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(data["opponents"])}


def keys(mod_ids) -> list[str]:
    out = []
    for m in mod_ids:
        try:
            out += [f"{m}/{o['slug']}" for o in _read(m)["opponents"]]
        except (OSError, ValueError, KeyError):
            continue
    return out


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    seen = set()
    for o in _read(mod_id)["opponents"]:
        if o["slug"] in seen:
            errors.append(f"AI opponent {o['slug']}: listed twice")
        seen.add(o["slug"])
        errors += [f"AI opponent {o.get('name', o['slug'])}: {e}" for e in _problems(mod_id, o)]
    return errors, warnings
