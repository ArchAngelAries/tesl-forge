"""Change an original card in place (offline gameplay mods).

A change is a full copy of an original card in mods/<mod-id>/changes/<slug>.json, keeping the card's id. Edit it like any
mod card (name, cost, power, health, text, rarity, abilities, keywords: tesl_suite.edits.edit_card finds it). The engine
(TESL: Everlasting level 57+, OfflineMods changes/) copies it over the installed card when the mod is enabled: the
collection, deck builder and matches all use the changed card, and every deck that holds it plays the new version.
Changes are gameplay: they load offline only, never in online-safe mode. Remove a change to restore the original card.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .fsutil import atomic_write, trash
from .mods import _active, _original_cards, all_mod_ids, find_card, mod_dir, read_mod, slugify

CHANGES = "changes"


def _folder(mod_id: str) -> Path:
    return mod_dir(mod_id) / CHANGES


def _entries(mod_id: str) -> list[tuple[Path, dict]]:
    folder = _folder(mod_id)
    out = []
    for p in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError):
            out.append((p, {}))
    return out


def _attr(card: dict, name: str):
    for a in card.get("EntityAttributes") or []:
        if a.get("Name") == name:
            return a.get("Value")
    return None


def _summary(card: dict, original: dict | None, path: Path) -> dict:
    stats = {k: _attr(card, a) for k, a in (("cost", "ManaCost"), ("attack", "Attack"), ("health", "MaxHealth"))}
    base = {k: _attr(original, a) for k, a in (("cost", "ManaCost"), ("attack", "Attack"), ("health", "MaxHealth"))} if original else {}
    changed = [k for k in ("cost", "attack", "health") if original and stats[k] != base[k]]
    if original:
        if (card.get("Name") or "") != (original.get("Name") or ""):
            changed.append("name")
        if (card.get("Description") or "") != (original.get("Description") or ""):
            changed.append("text")
        if card.get("Rarity") != original.get("Rarity"):
            changed.append("rarity")
        from .mods import RULE_FIELDS
        if any(card.get(f) != original.get(f) for f in RULE_FIELDS):
            changed.append("abilities")
    return {"id": card.get("ResourceId", {}).get("Id"), "slug": path.stem, "name": card.get("Name"),
            "original_name": (original or {}).get("Name"), "text": card.get("Description"), "rarity": card.get("Rarity"),
            **stats, "original": base, "changed": changed}


def list_changes(game, mod_id: str) -> dict:
    read_mod(mod_id)
    originals = _original_cards(game)
    return {"mod": mod_id, "changes": [_summary(c, originals.get(c.get("ResourceId", {}).get("Id")), p) for p, c in _entries(mod_id)]}


def change_card(game, mod_id: str, card: str) -> dict:
    """Start changing an original card: copy it into the mod (or return the existing change of that card)."""
    read_mod(mod_id)
    originals = _original_cards(game)
    base = find_card(game, str(card), originals)
    cid = base["ResourceId"]["Id"]
    if cid not in originals:
        raise ValueError(f"'{base.get('Name')}' is a mod card; edit it in its own mod instead of changing it")
    for p, c in _entries(mod_id):
        if c.get("ResourceId", {}).get("Id") == cid:
            return {"mod": mod_id, "existing": True, "change": _summary(c, base, p)}
    slug = slugify(base.get("Name") or str(cid)) or str(abs(cid))
    path = _folder(mod_id) / f"{slug}.json"
    n = 2
    while path.exists():
        path = _folder(mod_id) / f"{slug}-{n}.json"
        n += 1
    c = copy.deepcopy(base)
    c["_mod"] = {"changes": cid, "template": cid}
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(c, indent=1, ensure_ascii=False))
    return {"mod": mod_id, "existing": False, "change": _summary(c, base, path)}


def remove_change(mod_id: str, card: str) -> dict:
    """Restore the original card: the change file goes to the suite's trash (undoable)."""
    read_mod(mod_id)
    for p, c in _entries(mod_id):
        if p.stem == card or str(c.get("ResourceId", {}).get("Id")) == str(card) or (c.get("Name") or "").lower() == str(card).lower():
            trash(p)
            return {"mod": mod_id, "removed": p.stem, "id": c.get("ResourceId", {}).get("Id")}
    raise ValueError(f"{mod_id} does not change '{card}'")


def change_file(mod_id: str, card: str) -> Path | None:
    """The change file of this card (slug, id or name), or None (tesl_suite.edits)."""
    for p, c in _entries(mod_id):
        if p.stem == card or str(c.get("ResourceId", {}).get("Id")) == str(card) or (c.get("Name") or "").lower() == str(card).lower():
            return p
    return None


def validate_changes(game, mod_id: str, types: set[str]) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    originals = _original_cards(game)
    seen = {}
    active = {str(Path(x).resolve()) for x in _active()}
    for p, c in _entries(mod_id):
        cid = c.get("ResourceId", {}).get("Id")
        if not c:
            errors.append(f"changes/{p.name}: not readable JSON")
            continue
        if cid not in originals:
            errors.append(f"changes/{p.name}: {cid} is not an original card (a change keeps the original card's id)")
            continue
        if cid in seen:
            errors.append(f"changes/{p.name}: changes the same card as changes/{seen[cid]}")
        seen[cid] = p.name
        for field in ("Name", "Definition", "Image", "EntityAttributes"):
            if not c.get(field):
                errors.append(f"changes/{p.name}: missing {field}")
        unknown = set(re.findall(r'"\$type"\s*:\s*"([A-Za-z0-9_.+]+)"', json.dumps(c))) - types
        if unknown:
            errors.append(f"changes/{p.name}: rule types the game does not have: {sorted(unknown)}")
        for other in all_mod_ids():
            if other == mod_id or str(mod_dir(other).resolve()) not in active:
                continue
            if any(oc.get("ResourceId", {}).get("Id") == cid for _, oc in _entries(other)):
                warnings.append(f"changes/{p.name}: enabled mod {other} also changes {originals[cid].get('Name')} (only the first in the load order applies)")
    return errors, warnings
