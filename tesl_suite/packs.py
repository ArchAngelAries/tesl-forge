"""Card packs: sold for gold in TESL: Everlasting's offline store and opened with the game's own pack screens.

Each pack: name, description, price (gold), art (a picture, cropped to the game's pack shape), cards per pack (1-12) and a
drop table, either
- rarity slots from a pool ("mod" = this mod's cards, "all" = every collectible card, or a list of card sets), with odds
  per rarity for every slot and for the last ("guaranteed") slot; or
- a hand-picked list of cards with weights (a weight-6 card turns up six times as often as a weight-1 card).
premium: the chance (percent) of each card being premium. Cards below their max copies are preferred, like the game.

Layout: mods/<id>/packs/packs.json + <slug>.png.
"""
from __future__ import annotations

import json
from pathlib import Path

from .fsutil import atomic_write, trash
from .mods import mod_dir, read_mod, slugify

RARITIES = ("common", "rare", "epic", "legendary")
SETS = {"0_Core": "Core Set", "Dark_Brotherhood": "Dark Brotherhood", "Skyrim": "Heroes of Skyrim", "Clockwork_City": "Return to Clockwork City",
        "Morrowind": "Houses of Morrowind", "Isles_Of_Madness": "Isle of Madness", "Alliance_War": "Alliance War", "Sage": "Moons of Elsweyr",
        "Crisis": "Jaws of Oblivion", "Monthlies": "Monthly cards"}
ART = (476, 838)   # the store art shape of the game's packs/card backs
DEFAULT_ODDS = {"common": 79, "rare": 15, "epic": 4.5, "legendary": 1.5}
DEFAULT_LAST = {"common": 0, "rare": 80, "epic": 15, "legendary": 5}


def _path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "packs" / "packs.json"


def _read(mod_id: str) -> dict:
    p = _path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "packs": []}


def _write(mod_id: str, data: dict) -> None:
    p = _path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def list_packs(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "packs": _read(mod_id)["packs"]}


def options() -> dict:
    return {"sets": [{"set": k, "label": v} for k, v in SETS.items()], "rarities": list(RARITIES), "odds": DEFAULT_ODDS, "last_slot": DEFAULT_LAST}


def _card_names(game, mod_id: str) -> set[str]:
    from . import modes
    try:
        return modes._card_names(game, mod_id)
    except Exception:
        return set()


def _odds_ok(o) -> bool:
    return isinstance(o, dict) and all(k in RARITIES and isinstance(v, (int, float)) and v >= 0 for k, v in o.items()) and sum(o.values()) > 0


def problems(game, mod_id: str, p: dict) -> list[str]:
    out = []
    if not p.get("name"):
        out.append("a name is needed")
    if not isinstance(p.get("price", 100), int) or p.get("price", 100) < 0:
        out.append("price must be 0 or more gold")
    if not isinstance(p.get("cards", 6), int) or not 1 <= p.get("cards", 6) <= 12:
        out.append("cards per pack must be 1-12")
    for k in ("odds", "last_slot"):
        if k in p and not _odds_ok(p[k]):
            out.append(f"{k}: give each rarity (common, rare, epic, legendary) a chance of 0 or more, not all 0")
    if not 0 <= float(p.get("premium", 5)) <= 100:
        out.append("premium chance must be 0-100 percent")
    pool = p.get("pool", "mod")
    if isinstance(pool, list):
        bad = [s for s in pool if s not in SETS]
        if bad:
            out.append(f"unknown card sets: {', '.join(bad)}")
        if not pool and not p.get("cards_list"):
            out.append("choose at least one card set")
    elif pool not in ("mod", "all"):
        out.append("pool must be mod, all or a list of card sets")
    if p.get("cards_list"):
        known = _card_names(game, mod_id) if game is not None else set()
        for c in p["cards_list"]:
            if not c.get("card"):
                out.append("a card in the list has no name")
            elif known and c["card"].lower() not in known:
                out.append(f"no card named '{c['card']}'")
            if not isinstance(c.get("weight", 1), (int, float)) or c.get("weight", 1) <= 0:
                out.append(f"{c.get('card')}: weight must be more than 0")
    if pool == "mod" and not p.get("cards_list") and not any((mod_dir(mod_id) / "cards").glob("*.json")):
        out.append("this mod has no cards yet: add cards, pick card sets, or list cards by hand")
    art = p.get("art")
    if art and not (mod_dir(mod_id) / "packs" / art).is_file():
        out.append(f"art file missing: {art}")
    return out


def _art(src: Path, dest: Path) -> None:
    from PIL import Image
    img = Image.open(src).convert("RGB")
    w, h = img.size
    scale = max(ART[0] / w, ART[1] / h)
    r = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (r.width - ART[0]) // 2, (r.height - ART[1]) // 2
    dest.parent.mkdir(parents=True, exist_ok=True)
    r.crop((left, top, left + ART[0], top + ART[1])).save(dest)


def save_pack(game, mod_id: str, fields: dict, image: str | None = None) -> dict:
    """Create or change a pack (by slug, else by name). image: a picture for its store art."""
    read_mod(mod_id)
    data = _read(mod_id)
    slug = fields.get("slug") or slugify(fields.get("name") or "")
    if not slug:
        raise ValueError("a name is needed")
    old = next((x for x in data["packs"] if x["slug"] == slug), None)
    p = dict(old or {"slug": slug, "price": 100, "cards": 6, "pool": "mod", "premium": 5})
    for k in ("name", "description", "price", "cards", "pool", "odds", "last_slot", "premium", "cards_list"):
        if k in fields and fields[k] is not None:
            p[k] = fields[k]
    for k in ("price", "cards"):
        if k in p:
            p[k] = int(p[k])
    if p.get("cards_list") == []:
        p.pop("cards_list")
    if image:
        src = Path(image)
        if not src.is_file():
            raise ValueError(f"Image not found: {image}")
        _art(src, mod_dir(mod_id) / "packs" / f"{slug}.png")
        p["art"] = f"{slug}.png"
    errs = problems(game, mod_id, p)
    if errs:
        raise ValueError(f"pack {p.get('name') or slug}: " + "; ".join(errs))
    data["packs"] = [x for x in data["packs"] if x["slug"] != slug] + [p]
    _write(mod_id, data)
    return {"mod": mod_id, "pack": p, "store_key": f"modpack:{mod_id}/{slug}", "total": len(data["packs"]), "created": old is None}


def remove(mod_id: str, name: str) -> dict:
    data = _read(mod_id)
    slug = slugify(name)
    gone = [x for x in data["packs"] if x["slug"] in (slug, name) or x.get("name") == name]
    if not gone:
        raise ValueError(f"{mod_id} has no pack '{name}'")
    data["packs"] = [x for x in data["packs"] if x not in gone]
    for x in gone:
        art = x.get("art")
        if art and (mod_dir(mod_id) / "packs" / art).is_file() and not any(y.get("art") == art for y in data["packs"]):
            trash(mod_dir(mod_id) / "packs" / art, mod_id)
    _write(mod_id, data)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(data["packs"])}


def check(game, mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    seen = set()
    for p in _read(mod_id)["packs"]:
        if p["slug"] in seen:
            errors.append(f"pack {p['slug']}: listed twice")
        seen.add(p["slug"])
        errors += [f"pack {p['slug']}: {e}" for e in problems(game, mod_id, p)]
        if not p.get("art"):
            warnings.append(f"pack {p['slug']}: no art; the store shows it without a picture")
    return errors, warnings
