"""Edit existing mod items in place: cards, decks, avatars, card backs, boards, music tracks.

An edit keeps the item's slug, file and game id (decks, stories, modes and saved collections that refer to it keep working);
only the fields given change, the rest stay. A new name changes the name shown in the game, not the id. Every edit is one
undo step (tesl_suite.fsutil). The creators' own helpers (art import, crops, textures, OGG conversion) are reused.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path

from .fsutil import atomic_write
from .mods import (RULE_FIELDS, _original_cards, _set_attr, collectible, deck_art, deck_rules, find_card, import_art, mod_dir,
                   read_mod)


def _card_file(mod_id: str, card: str) -> Path:
    from .mods import slugify
    root = mod_dir(mod_id) / "cards"
    for p in (root / f"{card}.json", root / f"{slugify(card)}.json"):
        if p.is_file():
            return p
    for p in root.glob("*.json") if root.is_dir() else []:
        c = json.loads(p.read_text(encoding="utf-8"))
        if str(c["ResourceId"]["Id"]) == str(card) or (c.get("Name") or "").lower() == str(card).lower():
            return p
    raise ValueError(f"{mod_id} has no card '{card}'")


def edit_card(game, mod_id: str, card: str, name: str | None = None, cost=None, attack=None, health=None, text: str | None = None,
              rarity: str | None = None, unique: bool | None = None, art: str | None = None, rules_from: str | None = None,
              abilities: list | None = None, keywords: dict | None = None) -> dict:
    read_mod(mod_id)
    path = _card_file(mod_id, card)
    c = json.loads(path.read_text(encoding="utf-8"))
    slug = c["ResourceId"]["UniqueName"]
    if name:
        c["Name"] = name
    for attr, value in (("ManaCost", cost), ("Attack", attack), ("MaxHealth", health)):
        if value not in (None, ""):
            _set_attr(c, attr, int(value))
    if rarity:
        c["Rarity"] = rarity
    if unique is not None:
        c["Unique"] = bool(unique)
        c["MaxCopies"] = 1 if unique else 3
    notes = []
    if rules_from or abilities is not None or keywords:
        originals = _original_cards(game)
        meta = c.get("_mod") or {}
        base = find_card(game, str(meta.get("rules_template") or meta.get("template") or c["ResourceId"]["Id"]), originals)   # rules_template: the voice moved to another card
        for field in RULE_FIELDS:            # start again from the template's rules, then apply the new ones
            if field in base:
                c[field] = copy.deepcopy(base[field])
        c["MechanicsEntries"] = copy.deepcopy(base.get("MechanicsEntries") or [])
        if rules_from:
            donor = find_card(game, rules_from, originals)
            for field in RULE_FIELDS:
                if field in donor:
                    c[field] = copy.deepcopy(donor[field])
            c["MechanicsEntries"] = copy.deepcopy(donor.get("MechanicsEntries") or [])
            if text is None:
                text = donor.get("Description")
        if abilities is not None or keywords:
            from . import rules
            composed = rules.compose(c, abilities, keywords, lambda ref: find_card(game, ref, originals))
            notes = composed["notes"]
            if text is None and composed["text"] is not None:
                text = composed["text"]
        meta.update({"rules_from": rules_from, "abilities": abilities, "keywords": keywords})
        c["_mod"] = meta
    if text is not None:
        c["Description"] = text
    art_info = import_art(Path(art), mod_dir(mod_id) / "art" / f"{slug}.png") if art else None
    atomic_write(path, json.dumps(c, indent=1, ensure_ascii=False))
    return {"mod": mod_id, "card": {"id": c["ResourceId"]["Id"], "slug": slug, "name": c["Name"], "text": c.get("Description"), "notes": notes},
            "art": art_info}


def edit_deck(game, mod_id: str, deck: str, name: str | None = None, cards_spec: str | list | None = None, art_card: str | None = None,
              description: str | None = None) -> dict:
    from .mods import slugify
    read_mod(mod_id)
    path = mod_dir(mod_id) / "decks" / f"{slugify(deck)}.json"
    if not path.is_file():
        raise ValueError(f"{mod_id} has no deck '{deck}'")
    d = json.loads(path.read_text(encoding="utf-8"))
    originals = _original_cards(game)
    if name:
        d["name"] = name
    if description is not None:
        d["description"] = description
    if cards_spec:
        from .mods import deck_entries
        entries = []
        for card, count in deck_entries(game, cards_spec, originals):
            if not collectible(card):
                raise ValueError(f"'{card['Name']}' is a token or other non-collectible card")
            entries.append({"id": card["ResourceId"]["Id"], "name": card["Name"], "count": count})
        problems = deck_rules([(find_card(game, str(e["id"]), originals), e["count"]) for e in entries])
        if problems:
            raise ValueError("Deck breaks the game's deck rules: " + "; ".join(problems))
        d["cards"] = entries
    if art_card:
        art = find_card(game, art_card, originals)
        d["art_card"] = art["ResourceId"]["Id"]
        art_src = mod_dir(mod_id) / "art" / f"{art['ResourceId']['UniqueName']}.png"
        if art.get("_mod") and art_src.is_file():
            d["deck_art"] = deck_art(art_src, mod_dir(mod_id), path.stem)
        else:
            d.pop("deck_art", None)
    atomic_write(path, json.dumps(d, indent=1, ensure_ascii=False))
    return {"mod": mod_id, "deck": {**d, "total_cards": sum(e["count"] for e in d["cards"])}}


def _manifest_entry(module, key: str, mod_id: str, slug: str):
    manifest = module._read(mod_id)
    entry = next((e for e in manifest[key] if e["slug"] == slug or e.get("name", "").lower() == slug.lower()), None)
    if entry is None:
        raise ValueError(f"{mod_id} has no {key[:-1]} '{slug}'")
    return manifest, entry


def edit_avatar(mod_id: str, avatar: str, name: str | None = None, image: str | None = None, head: float | None = None, voice: str | None = None) -> dict:
    from . import avatars
    manifest, entry = _manifest_entry(avatars, "avatars", mod_id, avatar)
    if name:
        entry["name"] = name
    if voice is not None:
        if voice and voice not in {a["unique_name"] for a in avatars.original_avatars()}:
            raise ValueError(f"Unknown voice '{voice}'")
        if voice: entry["voice"] = voice
        else: entry.pop("voice", None)
    if image:
        files = avatars.crops(Path(image), mod_dir(mod_id) / "avatars", entry["slug"], head if head is not None else 0.22)
        entry.update({k: files[k] for k in ("image", "circle")})
    avatars._write(mod_id, manifest)
    return {"mod": mod_id, "avatar": entry}


def edit_cardback(mod_id: str, cardback: str, name: str | None = None, image: str | None = None, price: int | None = None,
                  unlock: str | None = None) -> dict:
    from . import cardbacks
    manifest, entry = _manifest_entry(cardbacks, "cardbacks", mod_id, cardback)
    if name:
        entry["name"] = name
    if price is not None:
        if int(price) < 0:
            raise ValueError("price must be 0 (free) or more gold")
        entry["price"] = int(price)
    if unlock is not None:
        if unlock: entry["unlock"] = unlock
        else: entry.pop("unlock", None)
    if image:
        root = mod_dir(mod_id) / "cardbacks"
        cardbacks.make_texture(Path(image), root / entry["image"], root / entry["store"])
    cardbacks._write(mod_id, manifest)
    return {"mod": mod_id, "cardback": entry}


def edit_board(mod_id: str, board: str, name: str | None = None, image: str | None = None, base: str | None = None, mode: str | None = None) -> dict:
    from . import boards
    manifest, entry = _manifest_entry(boards, "boards", mod_id, board)
    if image:   # re-paint through the creator under the board's own slug (keeps its edits), then keep its name
        old_name = entry["name"]
        boards.new_board(mod_id, entry["slug"], image, base or entry["base"], mode or entry["mode"])
        manifest, entry = _manifest_entry(boards, "boards", mod_id, entry["slug"])
        entry["name"] = name or old_name
    if name:
        entry["name"] = name
    if base:
        if base not in boards.BASES:
            raise ValueError(f"base must be one of {', '.join(boards.BASES)}")
        entry["base"] = base
    if mode:
        if mode not in ("rotation", "replace"):
            raise ValueError("mode must be rotation or replace")
        entry["mode"] = mode
    boards._write(mod_id, manifest)
    return {"mod": mod_id, "board": entry}


def edit_track(mod_id: str, track: str, name: str | None = None, file: str | None = None, contexts: list | None = None,
               mode: str | None = None, volume: float | None = None) -> dict:
    from . import music
    manifest, entry = _manifest_entry(music, "tracks", mod_id, track)
    if name:
        entry["name"] = name
    if contexts is not None:
        known = {c["context"] for c in music.contexts(mod_id)}
        bad = [c for c in contexts if c not in known and not c.startswith(("Board:", "Mode:"))]
        if bad or not contexts:
            raise ValueError(f"Unknown or no context(s): {bad}")
        entry["contexts"] = list(dict.fromkeys(contexts))
    if mode:
        if mode not in ("replace", "rotation"):
            raise ValueError("mode must be replace or rotation")
        entry["mode"] = mode
    if volume is not None:
        entry["volume"] = max(0.0, min(1.0, float(volume)))
    if file:
        seconds, dest = music._to_ogg(Path(file), mod_dir(mod_id) / "music" / entry["file"])
        entry["file"] = dest.name
    music._write(mod_id, manifest)
    return {"mod": mod_id, "track": entry}


KINDS = {"card": "edit_card", "deck": "edit_deck", "avatar": "edit_avatar", "cardback": "edit_cardback", "board": "edit_board", "track": "edit_track"}
NEEDS_GAME = {"card", "deck"}


def edit(game, mod_id: str, kind: str, item: str, fields: dict) -> dict:
    """Edit one item: kind card|deck|avatar|cardback|board|track, item = its slug (or name/id), fields = only what changes."""
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    fn = globals()[KINDS[kind]]
    fields = {k: v for k, v in (fields or {}).items() if v is not None and v != ""}
    return fn(game, mod_id, item, **fields) if kind in NEEDS_GAME else fn(mod_id, item, **fields)

