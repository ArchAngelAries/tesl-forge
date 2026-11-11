"""Game modes: custom matches against the AI, played from the offline game's Practice screen.

A mode sets the lanes (1 or 2, any implemented lane type, size 2/4/6), each side's health, starting magicka, runes,
deck (your own, any mod or original deck, or a random one) and cards already in hand, lanes or supports at the start,
the AI's difficulty and name, who goes first, turn rules (extra draws, extra magicka, damage or healing each turn, a
random creature every few turns, lanes that change every few turns), the board, its music ("Mode:<mod>/<mode>" in
tesl music) and gold for a win.

In the game: F10 > "Practice mode: <name>", then Play > Practice.
Layout: mods/<id>/modes/modes.json {"format": 1, "modes": [...]}.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
import re
from pathlib import Path

from .game import GameInstall
from .mods import mod_dir, read_mod, slugify

# Lane types the offline engine implements (Field and Shadow plus OfflineEngine.StoryLaneRules.Supported).
LANES = ["Default", "Stealth", "Plunder", "Windy", "Altar_Of_Silence", "Armor", "Armory", "Barracks", "Campfire", "Conveyor", "Docks", "Eclipse",
         "Flanking", "Fountain", "Graveyard", "Heist", "Incinerator", "Jail", "Library", "Liquid_Courage", "Madness", "Mage_Tower",
         "Masquerade_Ball", "Mine_Depths", "Monastery", "Order", "Reanimation", "Sewer", "Smelting", "Surplus", "Temple", "Torment", "Venom", "Water",
         "Renewal", "Siege", "Killing_Field", "King_Of_The_Hill", "Blitz", "Ballista_Tower", "Hall_Of_Mirrors", "Champions_Arena", "Lucky",
         "Fortifications", "Warzone", "Inner_Fire", "Zoo", "Wispmothers_Blessing", "Mania", "Dementia"]
NOT_YET = ["City_Gates", "Jode"]    # no rule text in the game
ZONES = {"hand": "in hand", "lane1": "in the first lane", "lane2": "in the second lane", "support": "as supports", "deck": "shuffled into the deck"}
RULES = {"draw_per_turn": "extra cards drawn each turn", "magicka_per_turn": "extra max magicka each turn", "damage_per_turn": "damage to the active player each turn",
         "heal_per_turn": "healing for the active player each turn", "random_creature_every": "a random creature for the active player every N turns",
         "lane_shuffle_every": "lanes change to random types every N turns"}
DIFFICULTIES = ["chosen", "Novice", "Adept", "Expert"]


def _texts() -> dict[str, str]:
    from .sounds import _texts as t
    return t(None)


def lanes() -> list[dict]:
    """Implemented lane types with the game's own name and rule text."""
    texts = _texts()
    out = []
    for name in LANES + NOT_YET:
        camel = name.replace("_", "")
        label = {"Default": "Field Lane", "Stealth": "Shadow Lane"}.get(name)
        desc = {"Default": texts.get("glossary.fieldlane.description", ""), "Stealth": texts.get("glossary.shadowlane.description", "")}.get(name, "")
        for k in (f"{camel}lane.title", f"isles.lanes.{camel}.name", f"lanes.{camel}.title", f"{camel}.title"):
            if not label and texts.get(k.lower()):
                label = texts[k.lower()]
        for k in (f"{camel}lane.description", f"isles.lanes.{camel}.description", f"lanes.{camel}.description"):
            if not desc and texts.get(k.lower()):
                desc = texts[k.lower()]
        for k in (f"com.direwolfdigital.hydra.data.draft.scenariomodifiers.{camel}.text", f"com.direwolfdigital.hydra.data.draft.scenariomodifiers.{camel}.fieldlane.text",
                  f"com.direwolfdigital.hydra.data.draft.scenariomodifiers.{name}.text"):
            full = texts.get(k.lower())
            if full and not desc:
                head = re.search(r"<b>(.*?)</b>", full)
                if head and not label:
                    label = head.group(1)
                desc = full.split("<br>", 1)[-1]
        out.append({"type": name, "label": re.sub(r"<[^>]+>", "", label or name.replace("_", " ").title() + " Lane"),
                    "description": re.sub(r"<[^>]+>", "", desc), "implemented": name in LANES})
    return out


def decks(game: GameInstall, mod_id: str | None = None) -> list[dict]:
    """Decks a mode can use: the mod's decks and the game's AI/premade decks (by name)."""
    out = [{"deck": "own", "label": "The player's chosen deck"}, {"deck": "random", "label": "A random deck"},
           {"deck": "practice", "label": "A practice AI deck (AI only)"}]
    if mod_id:
        for f in sorted((mod_dir(mod_id) / "decks").glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            out.append({"deck": d["type_name"], "label": d.get("name", d["type_name"]) + " (this mod)"})
    return out


def _path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "modes" / "modes.json"


def _read(mod_id: str) -> dict:
    p = _path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "modes": []}


def _write(mod_id: str, data: dict) -> None:
    p = _path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def list_modes(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "modes": _read(mod_id)["modes"]}


def _side(s: dict | None) -> dict:
    s = dict(s or {})
    out = {}
    for k in ("health", "magicka", "runes", "extra_cards", "random_size"):
        if s.get(k) not in (None, ""):
            out[k] = int(s[k])
    if s.get("deck"):
        out["deck"] = s["deck"]
    cards = {z: [c for c in (s.get("cards") or {}).get(z, []) if c] for z in ZONES}
    cards = {z: v for z, v in cards.items() if v}
    if cards:
        out["cards"] = cards
    return out


def save_mode(game: GameInstall, mod_id: str, name: str, description: str = "", lanes_: list | None = None, player: dict | None = None,
              opponent: dict | None = None, first: str = "random", difficulty: str = "chosen", opponent_name: str | None = None,
              rules: dict | None = None, board: str | None = None, reward_gold: int = 0, ai: str | None = None) -> dict:
    """Create or replace a mode. lanes_: [{"type": "Plunder", "size": 4}, ...] (1 or 2)."""
    read_mod(mod_id)
    slug = slugify(name)
    lanes_ = lanes_ or [{"type": "Default", "size": 4}, {"type": "Stealth", "size": 4}]
    if not 1 <= len(lanes_) <= 2:
        raise ValueError("a mode has 1 or 2 lanes")
    for l in lanes_:
        if l.get("type") not in LANES:
            raise ValueError(f"lane type {l.get('type')} is not playable offline yet; choose one of: {', '.join(LANES)}")
        if int(l.get("size", 4)) not in (2, 4, 6):
            raise ValueError("lane size must be 2, 4 or 6")
    if first not in ("random", "player", "opponent"):
        raise ValueError("first must be random, player or opponent")
    if difficulty not in DIFFICULTIES:
        raise ValueError(f"difficulty must be one of {', '.join(DIFFICULTIES)}")
    entry = {"slug": slug, "name": name, "description": description, "lanes": [{"type": l["type"], "size": int(l.get("size", 4))} for l in lanes_],
             "player": _side(player), "opponent": _side(opponent), "first": first, "difficulty": difficulty,
             "rules": {k: int(v) for k, v in (rules or {}).items() if k in RULES and v not in (None, "", 0, "0")}}
    if rules and rules.get("no_mulligan"):
        entry["rules"]["no_mulligan"] = True
    if opponent_name:
        entry["opponent_name"] = opponent_name
    if ai:
        entry["ai"] = ai
    if board:
        entry["board"] = board
    if reward_gold:
        entry["reward_gold"] = int(reward_gold)
    errors = check_entry(game, mod_id, entry)
    if errors:
        raise ValueError("; ".join(errors))
    data = _read(mod_id)
    data["modes"] = [m for m in data["modes"] if m["slug"] != slug] + [entry]
    _write(mod_id, data)
    return {"mod": mod_id, "mode": entry, "game_key": f"{mod_id}/{slug}", "total": len(data["modes"])}


def remove_mode(mod_id: str, name: str) -> dict:
    data = _read(mod_id)
    slug = slugify(name)
    gone = [m for m in data["modes"] if m["slug"] in (slug, name)]
    if not gone:
        raise ValueError(f"{mod_id} has no mode '{name}'")
    data["modes"] = [m for m in data["modes"] if m not in gone]
    _write(mod_id, data)
    return {"mod": mod_id, "removed": gone[0]["slug"]}


_NAMES: dict = {}


def _card_names(game: GameInstall, mod_id: str) -> set[str]:
    from .cards import load_sets
    sets = load_sets(game)
    if _NAMES.get("sets") is not sets:
        _NAMES.clear(); _NAMES["sets"] = sets; _NAMES["names"] = {c.get("Name", "").lower() for s in sets for c in (s.get("Cards") or []) if c}
    names = set(_NAMES["names"])
    for f in (mod_dir(mod_id) / "cards").glob("*.json") if (mod_dir(mod_id) / "cards").is_dir() else []:
        names.add(json.loads(f.read_text(encoding="utf-8")).get("Name", "").lower())
    return names


def check_entry(game: GameInstall, mod_id: str, m: dict) -> list[str]:
    errors = []
    known = None
    deck_names = {d["deck"] for d in decks(game, mod_id)}
    for side in ("player", "opponent"):
        s = m.get(side) or {}
        if s.get("deck") and s["deck"] not in deck_names and game is not None:
            errors.append(f"mode {m['slug']}: {side} deck '{s['deck']}' not found (own, random, practice or a deck of this mod)")
        for zone, cards in (s.get("cards") or {}).items():
            if zone not in ZONES:
                errors.append(f"mode {m['slug']}: unknown place '{zone}'")
            for c in cards:
                if known is None:
                    known = _card_names(game, mod_id) if game is not None else set()
                if known and c.lower() not in known:
                    errors.append(f"mode {m['slug']}: no card named '{c}'")
        if s.get("health") is not None and not 1 <= int(s["health"]) <= 999:
            errors.append(f"mode {m['slug']}: {side} health must be 1..999")
        if s.get("magicka") is not None and not 0 <= int(s["magicka"]) <= 12:
            errors.append(f"mode {m['slug']}: {side} magicka must be 0..12")
        if s.get("runes") is not None and not 0 <= int(s["runes"]) <= 5:
            errors.append(f"mode {m['slug']}: {side} runes must be 0..5")
    errors += check_ai(m.get("ai"), f"mode {m['slug']}")
    return errors


def check_ai(ref, where: str) -> list[str]:
    """An AI opponent reference "<mod>/<slug>" must name an opponent of an existing mod."""
    if not ref:
        return []
    from . import opponents
    from .mods import all_mod_ids
    if "/" not in ref or ref.split("/", 1)[0] not in all_mod_ids():
        return [f"{where}: AI opponent '{ref}' should be '<mod>/<opponent>'"]
    if ref not in opponents.keys([ref.split("/", 1)[0]]):
        return [f"{where}: no AI opponent '{ref}'"]
    return []


def check(mod_id: str) -> list[str]:
    from . import api
    try:
        game = api._game()
    except Exception:
        game = None
    errors = []
    for m in _read(mod_id)["modes"]:
        errors += check_entry(game, mod_id, m)
    return errors
