"""Mod packages: new cards and decks in the game's original card JSON shape, art import, validation, enable/disable.

Layout of a mod folder (mods/<mod-id>/):
  mod.json             id, name, version, author, description
  cards/<slug>.json    one card in the original FullSerializer card JSON form (the shape of data/original-rules)
  art/<slug>.png       card art, square, imported at 1024 x 1024 (the original art size)
  decks/<slug>.json    {"name", "description", "art_card", "cards": [{"id", "name", "count"}]}
The offline engine loads enabled mods from deploy/active-mods.json at startup (OfflineMods.cs); no game file changes.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import copy
import os
import datetime
import json
import re
from pathlib import Path

from .cards import load_sets
from .game import GameInstall, SUITE_ROOT

MODS = SUITE_ROOT / "mods"
DEPLOY = SUITE_ROOT / "deploy" / "active-mods.json"
ART_SIZE = 1024
RULE_FIELDS = ("TriggeredEffects", "Auras", "ActionPlayInformation", "ActivatedAbility", "PlayRequirements",
               "BetrayRequirements", "StrongHintRequirements", "PlayWeight", "HuntTypes", "UpgradesInto",
               "MobilizeRecruitId", "ArenaDraftSubtypes", "CardFxRelations", "AttackRequirements")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,40}$")


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or "card"


def fnv32(text: str) -> int:
    h = 0x811C9DC5
    for b in text.encode("utf-8"):
        h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
    return h - (1 << 32) if h & 0x80000000 else h


def mod_dir(mod_id: str) -> Path:
    if not isinstance(mod_id, str) or not ID_RE.match(mod_id):
        raise ValueError(f"invalid mod id: {mod_id!r}")
    return MODS / mod_id


def new_mod(mod_id: str, name: str, author: str = "", description: str = "") -> dict:
    if not ID_RE.match(mod_id):
        raise ValueError("Mod id: 2-41 lowercase letters, digits or '-', e.g. 'skyrim-heroes'.")
    root = mod_dir(mod_id)
    if (root / "mod.json").exists():
        raise FileExistsError(f"Mod already exists: {root}")
    for sub in ("cards", "art", "decks"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    meta = {"id": mod_id, "name": name, "version": "1.0.0", "author": author, "description": description,
            "format": 1, "created": datetime.date.today().isoformat()}
    atomic_write((root / "mod.json"), json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"mod": meta, "path": str(root)}


def read_mod(mod_id: str) -> dict:
    path = mod_dir(mod_id) / "mod.json"
    if not path.is_file():
        raise FileNotFoundError(f"No mod '{mod_id}' (run: tesl mod new {mod_id} --name ...)")
    return json.loads(path.read_text(encoding="utf-8"))


_ORIGINALS: dict = {}


def _original_cards(game: GameInstall) -> dict[int, dict]:
    sets = load_sets(game)
    if _ORIGINALS.get("sets") is not sets:
        _ORIGINALS.clear()
        _ORIGINALS["sets"] = sets
        _ORIGINALS["by_id"] = {c["ResourceId"]["Id"]: c for s in sets for c in s.get("Cards") or [] if c and c.get("ResourceId")}
    return _ORIGINALS["by_id"]


def mod_cards(mod_id: str) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted((mod_dir(mod_id) / "cards").glob("*.json"))]


def all_mod_ids() -> list[str]:
    return sorted(p.parent.name for p in MODS.glob("*/mod.json") if ID_RE.match(p.parent.name)) if MODS.is_dir() else []


def find_card(game: GameInstall, ref: str, originals: dict[int, dict] | None = None) -> dict:
    """A card by id, exact name (collectible printing first) or 'mod:<mod>/<slug>'."""
    originals = originals if originals is not None else _original_cards(game)
    if re.fullmatch(r"-?\d+", ref.strip()):
        card = originals.get(int(ref))
        if card:
            return card
        for mid in all_mod_ids():
            for c in mod_cards(mid):
                if c["ResourceId"]["Id"] == int(ref):
                    return c
    for mid in all_mod_ids():
        for c in mod_cards(mid):
            if c["Name"].lower() == ref.strip().lower() or f"mod:{mid}/{c['ResourceId']['UniqueName']}" == ref.strip():
                return c
    named = [c for c in originals.values() if (c.get("Name") or "").lower() == ref.strip().lower()]
    if not named:
        raise KeyError(f"No card named '{ref}'")
    named.sort(key=lambda c: (not (c.get("Production") and c.get("ExportCode")), c["ResourceId"]["Id"]))
    return named[0]


def collectible(card: dict) -> bool:
    """Deck-legal: an original card with a deck export code (production), or any mod card."""
    return bool(card.get("Production") and card.get("ExportCode"))


ATTRIBUTES = ("Strength", "Intelligence", "Willpower", "Agility", "Endurance")


def deck_rules(cards: list[tuple[dict, int]]) -> list[str]:
    """TESL constructed-deck rules as the game client checks them (SparkleServices Inventory.Deck.UpdateValidity):
    50-70 cards with one or two attributes; three attributes need 75-100 cards and at least one three-attribute card
    (Houses/Alliances); at most 3 copies (1 if unique); collectible cards only. Neutral is not an attribute."""
    problems = []
    total = sum(n for _, n in cards)
    attrs = sorted({a for c, _ in cards for a in (c.get("Subtypes") or []) if a in ATTRIBUTES})
    tri = any(len([a for a in (c.get("Subtypes") or []) if a in ATTRIBUTES]) == 3 for c, _ in cards)
    if len(attrs) > 3:
        problems.append(f"{len(attrs)} attributes {attrs} (at most 3)")
    elif len(attrs) == 3:
        if total < 75 or total > 100:
            problems.append(f"three attributes {attrs} need 75-100 cards (has {total})")
        if not tri:
            problems.append(f"three attributes {attrs} need at least one three-attribute card")
    elif total < 50 or total > 70:
        problems.append(f"{total} cards (decks need 50-70)")
    for c, n in cards:
        limit = 1 if c.get("Unique") else int(c.get("MaxCopies") or 3)
        if n > limit:
            problems.append(f"{c['Name']} x{n} (limit {limit})")
        if not collectible(c):
            problems.append(f"{c['Name']} is not collectible (token)")
    return problems


def deck_art(src: Path, mod_root: Path, slug: str) -> dict:
    """The two crops original decks use: a 512x128 tile banner (deck lists) and a 256x512 portrait (deck view),
    centred on the upper part of the art where faces usually are."""
    from PIL import Image
    img = Image.open(src).convert("RGBA")
    w, h = img.size
    out = {}
    for kind, (tw, th), centre in (("tile", (512, 128), 0.38), ("large", (256, 512), 0.5)):
        scale = max(tw / w, th / h)
        rw, rh = round(w * scale), round(h * scale)
        r = img.resize((rw, rh), Image.LANCZOS)
        left = (rw - tw) // 2
        top = min(max(0, round(rh * centre - th / 2)), rh - th)
        dest = mod_root / "art" / f"{slug}-deck-{kind}.png"
        r.crop((left, top, left + tw, top + th)).save(dest)
        out[kind] = dest.name
    return out


def _set_attr(card: dict, name: str, value) -> None:
    for a in card.setdefault("EntityAttributes", []):
        if a.get("Name") == name:
            a["Value"] = value
            return
    card["EntityAttributes"].append({"Value": value, "Name": name, "$type": "SPTESL.IntAttribute"})


def import_art(src: Path, dest: Path) -> dict:
    """Square-crop (centre) and resize to the original 1024 x 1024 card-art size; PNG, alpha kept."""
    from PIL import Image
    img = Image.open(src)
    img = img.convert("RGBA") if img.mode not in ("RGB", "RGBA") else img
    w, h = img.size
    side = min(w, h)
    left, top = (w - side) // 2, (h - side) // 2
    img = img.crop((left, top, left + side, top + side)).resize((ART_SIZE, ART_SIZE), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return {"source": str(src), "file": str(dest), "source_size": [w, h], "cropped_to": side, "size": [ART_SIZE, ART_SIZE]}


def new_card(game: GameInstall, mod_id: str, name: str, template: str, cost=None, attack=None, health=None,
             text: str | None = None, rarity: str | None = None, art: str | None = None, rules_from: str | None = None,
             no_rules: bool = False, unique: bool | None = None, abilities: list | None = None, keywords: dict | None = None) -> dict:
    """abilities/keywords: the no-code rule editor (tesl_suite.rules): abilities copied from any cards with their
    parameters changed, plus keyword toggles. When given, abilities replace the template's rules."""
    meta = read_mod(mod_id)
    originals = _original_cards(game)
    base = find_card(game, template, originals)
    card = copy.deepcopy(base)
    slug = slugify(name)
    path = mod_dir(mod_id) / "cards" / f"{slug}.json"
    if path.exists():
        raise FileExistsError(f"Card already exists in {mod_id}: {path.name}")
    taken = set(originals) | {c["ResourceId"]["Id"] for m in all_mod_ids() for c in mod_cards(m)}
    salt, cid = 0, fnv32(f"tesl-mod:{mod_id}/{slug}")
    while cid in taken or cid in (0, -1):
        salt += 1
        cid = fnv32(f"tesl-mod:{mod_id}/{slug}#{salt}")
    card["ResourceId"] = {"Id": cid, "UniqueName": slug, "CompletionType": "Complete"}
    card["Name"] = name
    card["NameKey"] = {"RawKey": f"mod.{mod_id}.{slug}.title"}
    card["DescriptionKey"] = {"RawKey": f"mod.{mod_id}.{slug}.text"}
    card["AdditionalSearchTokensKey"] = {"RawKey": ""}
    card["Image"] = f"Mods/{mod_id}/{slug}"
    card["Production"] = True
    card["ExportCode"] = "~" + format(cid & 0xFFFFFFFF, "x")
    card["AlternateOfCard"] = {"resourceId": 0}
    card["UpgradesInto"] = []
    card["DoubleCardReferences"] = []
    card["SeasonId"] = 0
    card["ContentPackIndex"] = 0
    card["IsPremiumOnly"] = False
    card["Source"] = "Normal"
    if rarity:
        card["Rarity"] = rarity
    if unique is not None:
        card["Unique"] = unique
        card["MaxCopies"] = 1 if unique else 3
    for attr, value in (("ManaCost", cost), ("Attack", attack), ("MaxHealth", health)):
        if value is not None:
            _set_attr(card, attr, int(value))
    if rules_from:
        donor = find_card(game, rules_from, originals)
        for field in RULE_FIELDS:
            if field in donor:
                card[field] = copy.deepcopy(donor[field])
        card["MechanicsEntries"] = copy.deepcopy(donor.get("MechanicsEntries") or [])   # tooltips follow the rules, not the template
        if text is None:
            text = donor.get("Description")
    if no_rules:
        card["MechanicsEntries"] = []
        for field in ("TriggeredEffects", "Auras", "ActionPlayInformation"):
            card[field] = []
        card["ActivatedAbility"] = {"TargetingType": "NoTarget", "TargetSelectors": [], "AbilityGroups": []}
    composed = None
    if abilities is not None or keywords:
        from . import rules
        composed = rules.compose(card, abilities, keywords, lambda ref: find_card(game, ref, originals))
        if text is None and composed["text"] is not None:
            text = composed["text"]
    card["Description"] = text if text is not None else base.get("Description") or ""
    card["_mod"] = {"mod": mod_id, "template": base["ResourceId"]["Id"], "template_name": base.get("Name"),
                    "rules_from": rules_from, "abilities": abilities, "keywords": keywords,
                    "created": datetime.datetime.now().isoformat(timespec="seconds")}
    # The template's art framing fits the template's own picture; new art gets a slight step back anchored at the top of
    # the picture, so heads aren't cut off (tesl card frame changes it).
    from .framing import top_frame
    frame = top_frame()
    card["ImageScale"], card["ImageOffsetX"], card["ImageOffsetY"] = frame["scale"], frame["x"], frame["y"]
    art_info = None
    if art:
        art_info = import_art(Path(art), mod_dir(mod_id) / "art" / f"{slug}.png")
    atomic_write(path, json.dumps(card, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"mod": meta["id"], "card": {"id": cid, "slug": slug, "name": name, "file": str(path), "template": base.get("Name"),
            "rules_from": rules_from or base.get("Name"), "text": card["Description"],
            "notes": composed["notes"] if composed else []}, "art": art_info}


def deck_entries(game: GameInstall, cards_spec, originals: dict | None = None) -> list[tuple[dict, int]]:
    """Cards of a deck list: a list, or text with entries separated by ";", new lines or commas ("Name x3"). Names that contain
    commas ("Miraak, Dragonborn") are found by joining neighbouring pieces when the joined text is a card."""
    originals = originals if originals is not None else _original_cards(game)
    if isinstance(cards_spec, list):
        pieces = [str(p).strip() for p in cards_spec]
    elif ";" in cards_spec or "\n" in cards_spec:
        pieces = [p.strip() for p in re.split(r"[;\n]", cards_spec)]
    else:
        raw, pieces, i = [p.strip() for p in cards_spec.split(",")], [], 0
        while i < len(raw):
            if i + 1 < len(raw):
                joined = raw[i] + ", " + raw[i + 1]
                m = re.fullmatch(r"(.+?)\s*[x*]\s*(\d+)", joined)
                try:
                    find_card(game, m.group(1) if m else joined, originals)
                    pieces.append(joined); i += 2; continue
                except ValueError:
                    pass
            pieces.append(raw[i]); i += 1
    out = []
    for part in [p for p in pieces if p]:
        m = re.fullmatch(r"(.+?)\s*[x*]\s*(\d+)", part)
        ref, count = (m.group(1), int(m.group(2))) if m else (part, 1)
        out.append((find_card(game, ref, originals), count))
    if not out:
        raise ValueError("the deck list is empty")
    return out


def new_deck(game: GameInstall, mod_id: str, name: str, cards_spec, art_card: str | None = None, description: str = "") -> dict:
    read_mod(mod_id)
    originals = _original_cards(game)
    entries = []
    for card, count in deck_entries(game, cards_spec, originals):
        if not collectible(card):
            raise ValueError(f"'{card['Name']}' is a token or other non-collectible card; the game marks decks containing it as invalid.")
        entries.append({"id": card["ResourceId"]["Id"], "name": card["Name"], "count": count})
    slug = slugify(name)
    problems = deck_rules([(find_card(game, str(e["id"]), originals), e["count"]) for e in entries])
    if problems:
        raise ValueError("Deck breaks the game's deck rules: " + "; ".join(problems))
    art = find_card(game, art_card, originals) if art_card else find_card(game, entries[0]["name"], originals)
    deck = {"name": name, "description": description, "art_card": art["ResourceId"]["Id"], "cards": entries,
            "type_name": f"mod.{mod_id}.deck.{slug}", "type_hash": fnv32(f"tesl-mod-deck:{mod_id}/{slug}")}
    art_src = mod_dir(mod_id) / "art" / f"{art['ResourceId']['UniqueName']}.png"
    if art.get("_mod") and art_src.is_file():
        deck["deck_art"] = deck_art(art_src, mod_dir(mod_id), slug)
    path = mod_dir(mod_id) / "decks" / f"{slug}.json"
    atomic_write(path, json.dumps(deck, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"mod": mod_id, "deck": {**deck, "file": str(path), "total_cards": sum(e["count"] for e in entries)}}


_TYPES: dict = {}


def known_types(game: GameInstall) -> set[str]:
    raw = Path(game.original_rules)
    key = (str(raw), raw.stat().st_mtime)
    if key not in _TYPES:
        import gzip
        with gzip.open(raw, "rt", encoding="utf-8") as f:
            _TYPES.clear()
            _TYPES[key] = set(re.findall(r'"\$type"\s*:\s*"([A-Za-z0-9_.+]+)"', f.read()))
    return _TYPES[key]


# Keywords the game prints by itself from the card's attributes (original cards never repeat them in their text).
KEYWORD_LINES = {"Guard": "Taunt", "Breakthrough": "Breakthrough", "Charge": "Charge", "Drain": "Drain", "Lethal": "Deathtouch",
                 "Regenerate": "Regenerate", "Ward": "Ward"}


def validate(game: GameInstall, mod_id: str) -> dict:
    meta = read_mod(mod_id)
    errors, warnings = [], []
    originals = _original_cards(game)
    types = known_types(game)
    ids = {}
    for c in mod_cards(mod_id):
        slug = c.get("ResourceId", {}).get("UniqueName", "?")
        cid = c.get("ResourceId", {}).get("Id")
        if cid in originals:
            errors.append(f"{slug}: id {cid} collides with an original card")
        if cid in ids:
            errors.append(f"{slug}: id {cid} duplicates {ids[cid]}")
        ids[cid] = slug
        for field in ("Name", "Definition", "Image", "EntityAttributes"):
            if not c.get(field):
                errors.append(f"{slug}: missing {field}")
        unknown = set(re.findall(r'"\$type"\s*:\s*"([A-Za-z0-9_.+]+)"', json.dumps(c))) - types
        if unknown:
            errors.append(f"{slug}: rule types the game does not have: {sorted(unknown)}")
        on = {a.get("Name") for a in c.get("EntityAttributes") or [] if a.get("Value") not in (0, False, None)}
        lines = [re.sub(r"<[^>]+>", "", x).strip().rstrip(".") for x in re.split(r"<br\s*/?>|\n", c.get("Description") or "")]
        for word, attr in KEYWORD_LINES.items():
            if attr in on and word in lines:
                warnings.append(f"{slug}: the text has a '{word}' line, but the game already shows {word} for cards that have it; remove it from the text so it is not shown twice")
        if not (mod_dir(mod_id) / "art" / f"{slug}.png").is_file():
            warnings.append(f"{slug}: no art (art/{slug}.png); the card shows a blank picture")
    mod_ids = set(ids)
    for p in sorted((mod_dir(mod_id) / "decks").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        for e in d.get("cards", []):
            if e["id"] not in originals and e["id"] not in mod_ids:
                errors.append(f"deck {p.stem}: card {e.get('name')} ({e['id']}) not found")
        resolved = []
        for e in d.get("cards", []):
            card = originals.get(e["id"]) or next((c for c in mod_cards(mod_id) if c["ResourceId"]["Id"] == e["id"]), None)
            if card:
                resolved.append((card, e["count"]))
        for problem in deck_rules(resolved):
            errors.append(f"deck {p.stem}: {problem}")
        if not d.get("deck_art"):
            warnings.append(f"deck {p.stem}: no deck art crops (use a mod card with art as --art-card)")
    from . import replace
    from . import avatars
    rerr, rwarn = replace.check(mod_id)
    errors += rerr; warnings += rwarn
    aerr, awarn = avatars.check(mod_id)
    errors += aerr; warnings += awarn
    errors += avatars.check_extras(mod_id)
    from . import modes
    errors += modes.check(mod_id)
    from . import stories
    errors += stories.check(mod_id)
    from . import translations
    terr, twarn = translations.check(mod_id)
    errors += terr; warnings += twarn
    from . import packs
    perr, pwarn = packs.check(game, mod_id)
    errors += perr; warnings += pwarn
    from . import opponents
    oerr, owarn = opponents.check(mod_id)
    errors += oerr; warnings += owarn
    from . import cardbacks
    cerr, cwarn = cardbacks.check(mod_id)
    errors += cerr; warnings += cwarn
    from . import boards
    berr, bwarn = boards.check(mod_id)
    errors += berr; warnings += bwarn
    from . import music
    merr, mwarn = music.check(mod_id)
    errors += merr; warnings += mwarn
    from . import sounds
    serr, swarn = sounds.check(mod_id)
    errors += serr; warnings += swarn
    mine = {x["asset"].lower() for x in replace.list_replacements(mod_id)["images"]}
    active = set(_active())
    for other in all_mod_ids():
        if other != mod_id and str(mod_dir(other).resolve()) in active:
            both = mine & {x["asset"].lower() for x in replace.list_replacements(other)["images"]}
            if both:
                warnings.append(f"also replaced by enabled mod {other} (the mod later in the list wins): {sorted(both)[:5]}")
    story_slugs = [s["slug"] for s in stories.list_stories(mod_id)["stories"]]
    issues = [{"severity": sev, "text": t, **locate(t, set(ids.values()), story_slugs)} for sev, msgs in (("error", errors), ("warning", warnings)) for t in msgs]
    names = {c.get("ResourceId", {}).get("UniqueName"): c.get("Name") for c in mod_cards(mod_id)}
    for x in issues:
        if x["view"] == "cards":
            x["item"] = names.get(x["item"]) or x["item"]
    return {"mod": meta["id"], "cards": len(ids), "decks": len(list((mod_dir(mod_id) / "decks").glob("*.json"))),
            "replacements": len(mine), "avatars": len(avatars.list_avatars(mod_id)["avatars"]),
            "cardbacks": len(cardbacks.list_cardbacks(mod_id)["cardbacks"]), "valid": not errors, "errors": errors, "warnings": warnings,
            "issues": issues}


_LOCATE = [   # message start -> (app page, item group)
    (r"deck ([^:\s]+):", "decks"), (r"AI opponent ([^:]+):", "opponents"), (r"(?:extra emote [^/]+/|avatar )([^:\s]+):", "avatars"),
    (r"board ([^:\s]+):", "boards"), (r"card back ([^:\s]+):", "cardbacks"), (r"music ([^:\s]+):", "music"),
    (r"sound ([^:]+):", "sounds"), (r"card ([^:]+): .*(?:voice|line)", "sounds"), (r"mode ([^:\s]+):", "modes"),
    (r"replacement for ([^:]+):", "remaster"), (r"pack ([^:\s]+):", "packs"), (r"translation ([^:\s]+):", "translations"), (r"also replaced by enabled mod", "remaster"),
]


def locate(text: str, card_slugs=(), story_slugs=()) -> dict:
    """Which app page (and item) a validation message is about, so the app can link straight to it."""
    for pattern, view in _LOCATE:
        m = re.match(pattern, text)
        if m:
            return {"view": view, "item": m.group(1).strip() if m.groups() else None}
    head = re.split(r"[:/]", text, 1)[0].strip()
    if head in story_slugs:
        return {"view": "stories", "item": head}
    if head in card_slugs:
        return {"view": "cards", "item": head}
    return {"view": "overview", "item": None}


def _active() -> list[str]:
    """Enabled mod folders (absolute) in load order. The file stores paths relative to deploy/ (the engine resolves them the
    same way), so moving the whole suite folder keeps mods enabled; older absolute entries still work."""
    if DEPLOY.is_file():
        out = []
        for p in json.loads(DEPLOY.read_text(encoding="utf-8")).get("mods", []):
            path = Path(p) if Path(p).is_absolute() else (DEPLOY.parent / p)
            out.append(str(path.resolve()))
        return out
    return []


def write_active(paths: list[str]) -> list[str]:
    rel = []
    for p in paths:
        try:
            rel.append(Path(os.path.relpath(Path(p).resolve(), DEPLOY.parent.resolve())).as_posix())
        except ValueError:   # another drive: keep absolute
            rel.append(str(p))
    atomic_write(DEPLOY, json.dumps({"format": 1, "mods": rel}, indent=1))
    return rel


def set_enabled(mod_id: str, enabled: bool, force: bool = False) -> dict:
    """Enable (at the end of the load order) or disable a mod. Enabling checks compatibility first (compat.check_enable):
    a mod that would be skipped (missing dependency, declared conflict, newer engine, duplicate, clashing ids) is refused
    unless force=True. Its required engine level is recorded in mod.json."""
    read_mod(mod_id)
    if enabled:
        from . import compat
        compat.stamp(mod_id)
        check = compat.check_enable(mod_id)
        if check["blocked"] and not force:
            raise ValueError("not enabled: " + "; ".join(check["blocked"]) + " (enable anyway with force)")
    path = str(mod_dir(mod_id).resolve())
    mods = [m for m in _active() if m != path]
    if enabled:
        mods.append(path)
    write_active(mods)
    return {"mod": mod_id, "enabled": enabled, "active": mods, "deploy": str(DEPLOY)}


def list_mods() -> list[dict]:
    active = set(_active())
    out = []
    for mid in all_mod_ids():
        meta = read_mod(mid)
        out.append({"id": mid, "name": meta.get("name"), "version": meta.get("version"),
                    "cards": len(mod_cards(mid)), "decks": len(list((mod_dir(mid) / "decks").glob("*.json"))),
                    "enabled": str(mod_dir(mid).resolve()) in active})
    return out
