"""Removing what a user made: new cards, decks, an avatar's own emote lines, translation languages, and bringing back an
uninstalled mod. Every removal moves files to the suite's trash (workspace/trash) through fsutil.trash, so the mod's
Undo brings them back; an uninstalled mod (a whole folder) comes back with restore_mod.

Other kinds keep their own remove functions (avatars, cardbacks, boards, music, packs, opponents, modes, stories, extra
emotes, sounds, card voice lines, replacements, changed originals); this module covers the kinds that had none.
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .fsutil import trash
from .game import workspace
from .mods import MODS, ID_RE, mod_dir, read_mod, slugify

_TEXT = {".json", ".txt", ".csv", ".tsv"}


def _find(mod_id: str, folder: str, ref: str, what: str) -> tuple[Path, dict]:
    """A JSON item in mods/<mod>/<folder>/ by file slug, name (any case) or numeric id."""
    read_mod(mod_id)
    d = mod_dir(mod_id) / folder
    ref = str(ref).strip()
    slug = slugify(ref) if ref else ""
    for p in sorted(d.glob("*.json")) if d.is_dir() else []:
        try:
            item = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            item = {}
        rid = str((item.get("ResourceId") or {}).get("Id", ""))
        if p.stem in (ref, slug) or (item.get("Name") or item.get("name") or "").lower() == ref.lower() or (rid and rid == ref):
            return p, item
    raise ValueError(f"{mod_id} has no {what} '{ref}'")


def _mentions(mod_id: str, needles: list[str], skip: set[Path]) -> list[str]:
    """Files of the mod (relative paths) whose text mentions any needle: a numeric id as a whole number, or a quoted slug."""
    root = mod_dir(mod_id)
    pats = [re.compile(r"(?<![\d-])" + re.escape(n) + r"(?!\d)") if n.lstrip("-").isdigit() else re.compile('"' + re.escape(n) + '"')
            for n in needles if n]
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in _TEXT or p.resolve() in skip:
            continue
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if any(pat.search(text) for pat in pats):
            out.append(p.relative_to(root).as_posix())
    return out


_KIND = {"decks": "the deck", "packs": "the pack", "opponents": "the AI opponent", "modes": "the game mode", "stories": "the story",
         "cards": "the card", "changes": "the changed card", "locale": "a translation", "boards": "the board"}


def _label(mod_id: str, rel: str) -> str:
    """A readable name for a file of the mod: "the deck Skyrim Heroes" (its own name when the file has one)."""
    parts = rel.split("/")
    kind = _KIND.get(parts[0])
    if kind is None:
        return rel
    name = parts[1] if len(parts) > 2 else Path(parts[-1]).stem
    if len(parts) == 2 and rel.endswith(".json"):
        try:
            item = json.loads((mod_dir(mod_id) / rel).read_text(encoding="utf-8"))
            name = item.get("Name") or item.get("name") or name
        except (OSError, ValueError):
            pass
    return f"{kind} {name}"


def card_usage(mod_id: str, card: str) -> dict:
    """Where else in the mod a new card is used (decks, packs, opponents, modes, stories, other cards), before removing it."""
    p, c = _find(mod_id, "cards", card, "new card")
    cid = str((c.get("ResourceId") or {}).get("Id", ""))
    files = _mentions(mod_id, [cid, p.stem], {p.resolve()})
    return {"mod": mod_id, "card": c.get("Name") or p.stem, "slug": p.stem, "id": cid, "files": files,
            "used_by": sorted({_label(mod_id, f) for f in files})}


def remove_card(mod_id: str, card: str) -> dict:
    """Delete a new card: its file, its art and its own voice clips go to the trash (Undo brings them back). Decks or other
    items that still use it are listed, and the mod's check flags them, so nothing breaks silently."""
    usage = card_usage(mod_id, card)
    p, c = _find(mod_id, "cards", card, "new card")
    root = mod_dir(mod_id)
    files = [root / "art" / f"{p.stem}.png"]
    files += [root / rel for rel in (c.get("audio") or {}).values() if isinstance(rel, str)]
    for f in files:
        if f.is_file():
            trash(f, mod_id)
    trash(p, mod_id)
    return {"mod": mod_id, "removed": p.stem, "name": usage["card"], "still_used_by": usage["used_by"], "files": usage["files"]}


def remove_deck(mod_id: str, deck: str) -> dict:
    """Delete a deck and its deck-list art."""
    p, d = _find(mod_id, "decks", deck, "deck")
    root = mod_dir(mod_id)
    art = d.get("deck_art") or {}
    for name in (art.values() if isinstance(art, dict) else []):     # mods.deck_art: file names in art/
        if isinstance(name, str) and (root / "art" / name).is_file():
            trash(root / "art" / name, mod_id)
    trash(p, mod_id)
    return {"mod": mod_id, "removed": p.stem, "name": d.get("name") or p.stem,
            "still_used_by": _mentions(mod_id, [d.get("type_name") or "", str(d.get("type_hash") or "")], {p.resolve()})}


def clear_emote(mod_id: str, avatar: str, emote: str) -> dict:
    """Remove an avatar's own line for one emote (text and voice clip); the borrowed voice's line plays again."""
    from . import avatars
    manifest = avatars._read(mod_id)
    slug = slugify(avatar)
    entry = next((a for a in manifest["avatars"] if a["slug"] in (slug, avatar)), None)
    if entry is None:
        raise ValueError(f"{mod_id} has no avatar '{avatar}'")
    kind = next((t for t in avatars.EMOTE_TYPES if t.lower() == str(emote).replace(" ", "").lower()), None)
    line = (entry.get("emotes") or {}).pop(kind, None) if kind else None
    if line is None:
        raise ValueError(f"{entry.get('name', avatar)} has no own '{emote}' line")
    if line.get("audio"):
        f = mod_dir(mod_id) / "avatars" / line["audio"]
        if f.is_file():
            trash(f, mod_id)
    if not entry.get("emotes"):
        entry.pop("emotes", None)
    avatars._write(mod_id, manifest)
    return {"mod": mod_id, "avatar": entry["slug"], "cleared": kind}


def remove_language(mod_id: str, lang: str) -> dict:
    """Delete one translation language of a mod."""
    read_mod(mod_id)
    p = mod_dir(mod_id) / "locale" / f"{lang}.json"
    if not p.is_file():
        raise ValueError(f"{mod_id} has no '{lang}' translation")
    trash(p, mod_id)
    return {"mod": mod_id, "removed": lang}


# ---- uninstalled mods ----------------------------------------------------------------------------------------------------
def _uninstalled_dirs() -> list[Path]:
    t = workspace() / "trash"
    return sorted((d for d in t.iterdir() if d.is_dir() and (d / "mod.json").is_file()), reverse=True) if t.is_dir() else []


def uninstalled() -> dict:
    """Mods uninstalled from the suite (whole folders in workspace/trash), newest first; restore_mod brings one back."""
    out = []
    for d in _uninstalled_dirs():
        try:
            meta = json.loads((d / "mod.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
        mid = meta.get("id") or re.sub(r"-\d{8}-\d{6}$", "", d.name)
        out.append({"folder": d.name, "id": mid, "name": meta.get("name") or mid, "installed_again": (MODS / mid).exists()})
    return {"mods": out}


def restore_mod(folder: str) -> dict:
    """Move an uninstalled mod back into the mods folder (not enabled; enable it on Load order)."""
    d = next((x for x in _uninstalled_dirs() if x.name == folder), None)
    if d is None:
        raise ValueError(f"No uninstalled mod '{folder}'")
    try:
        mid = json.loads((d / "mod.json").read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError):
        mid = None
    mid = mid or re.sub(r"-\d{8}-\d{6}$", "", d.name)
    if not ID_RE.match(mid):
        raise ValueError(f"'{mid}' is not a valid mod id")
    if (MODS / mid).exists():
        raise ValueError(f"A mod '{mid}' is installed already; uninstall or rename it first")
    MODS.mkdir(parents=True, exist_ok=True)
    shutil.move(str(d), str(MODS / mid))
    return {"mod": mid, "restored_from": d.name}


# ---- one entry point for every kind (agents: MCP remove_item) -----------------------------------------------------------
KINDS = ("card", "deck", "avatar", "avatar_emote", "extra_emote", "cardback", "board", "track", "pack", "opponent", "mode",
         "story", "sound", "card_voice", "replacement", "change", "language")


def remove_item(mod_id: str, kind: str, item: str, extra: dict | None = None) -> dict:
    """Remove anything a mod made. item: slug or name (sound id, asset path, language code...). extra: avatar_emote
    {emote}, extra_emote {avatar?}, card_voice {line}. Everything goes to the trash and the mod's Undo brings it back."""
    from . import avatars, boards, cardbacks, changes, modes, music, opponents, packs, replace, sounds, stories
    extra = extra or {}
    calls = {
        "card": lambda: remove_card(mod_id, item),
        "deck": lambda: remove_deck(mod_id, item),
        "avatar": lambda: avatars.remove(mod_id, item),
        "avatar_emote": lambda: clear_emote(mod_id, item, extra["emote"]),
        "extra_emote": lambda: avatars.remove_extra_emote(mod_id, item, extra.get("avatar") or None),
        "cardback": lambda: cardbacks.remove(mod_id, item),
        "board": lambda: boards.remove(mod_id, item),
        "track": lambda: music.remove(mod_id, item),
        "pack": lambda: packs.remove(mod_id, item),
        "opponent": lambda: opponents.remove(mod_id, item),
        "mode": lambda: modes.remove_mode(mod_id, item),
        "story": lambda: stories.remove_story(mod_id, item),
        "sound": lambda: sounds.remove_replacement(mod_id, item),
        "card_voice": lambda: sounds.remove_card_voice(mod_id, item, extra["line"]),
        "replacement": lambda: replace.remove(mod_id, item),
        "change": lambda: changes.remove_change(mod_id, item),
        "language": lambda: remove_language(mod_id, item),
    }
    if kind not in calls:
        raise ValueError(f"kind: one of {', '.join(KINDS)}")
    return calls[kind]()
