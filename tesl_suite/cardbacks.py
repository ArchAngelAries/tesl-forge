"""New card backs. Any number per mod; each is selectable in the collection's card back view, and can be free or sold for
gold in the offline store (Special Offers).

The game draws a card back from a 1024 x 1024 texture whose visible card is the rectangle (276, 87)-(752, 925), 476 x 838
(the layout of the original card backs, e.g. Houses of Morrowind, whose material the engine copies). `new` cover-crops the
image into that rectangle and fills the margin with the image's edge colour; it also saves the card on its own as store art.

Layout: mods/<id>/cardbacks/cardbacks.json + <slug>.png (texture) + <slug>-store.png.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

CARD_RECT = (276, 87, 752, 925)   # in a 1024 texture
TEXTURE = 1024


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "cardbacks" / "cardbacks.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "cardbacks": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def make_texture(src: Path, dest: Path, store: Path, size: int = TEXTURE) -> dict:
    from PIL import Image, ImageStat
    img = Image.open(src).convert("RGB")
    s = size / TEXTURE
    x0, y0, x1, y1 = (round(v * s) for v in CARD_RECT)
    cw, ch = x1 - x0, y1 - y0
    w, h = img.size
    scale = max(cw / w, ch / h)
    r = img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
    left, top = (r.width - cw) // 2, (r.height - ch) // 2
    card = r.crop((left, top, left + cw, top + ch))
    edge = Image.new("RGB", (cw, ch))
    edge.paste(card)
    border = card.crop((0, 0, cw, 8))
    colour = tuple(int(v) for v in ImageStat.Stat(border).mean)
    tex = Image.new("RGB", (size, size), colour)
    # A few pixels of the card's own edge beyond the rectangle, so filtering never shows the fill colour at the border.
    pad = max(2, round(6 * s))
    bleed = card.resize((cw + 2 * pad, ch + 2 * pad), Image.LANCZOS)
    tex.paste(bleed, (x0 - pad, y0 - pad))
    tex.paste(card, (x0, y0))
    dest.parent.mkdir(parents=True, exist_ok=True)
    tex.save(dest)
    card.save(store)
    return {"size": size, "card": [cw, ch]}


def new_cardback(mod_id: str, name: str, image: str, price: int = 0, unlock: str | None = None, size: int = TEXTURE) -> dict:
    read_mod(mod_id)
    src = Path(image)
    if not src.is_file():
        raise ValueError(f"Image not found: {image}")
    if price < 0:
        raise ValueError("price must be 0 (free) or more gold")
    if size not in (1024, 2048):
        raise ValueError("size must be 1024 or 2048")
    slug = slugify(name)
    root = mod_dir(mod_id) / "cardbacks"
    info = make_texture(src, root / f"{slug}.png", root / f"{slug}-store.png", size)
    manifest = _read(mod_id)
    entry = {"slug": slug, "name": name, "image": f"{slug}.png", "store": f"{slug}-store.png", "price": price}
    if unlock:
        entry["unlock"] = unlock
    manifest["cardbacks"] = [c for c in manifest["cardbacks"] if c["slug"] != slug] + [entry]
    _write(mod_id, manifest)
    return {"mod": mod_id, "cardback": {**entry, **info, "game_key": f"mod.{mod_id}.cardback.{slug}"}, "total": len(manifest["cardbacks"])}


def list_cardbacks(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "cardbacks": _read(mod_id)["cardbacks"]}


def remove(mod_id: str, name: str) -> dict:
    manifest = _read(mod_id)
    slug = slugify(name)
    gone = [c for c in manifest["cardbacks"] if c["slug"] in (slug, name)]
    if not gone:
        raise ValueError(f"{mod_id} has no card back '{name}'")
    manifest["cardbacks"] = [c for c in manifest["cardbacks"] if c not in gone]
    for c in gone:
        for k in ("image", "store"):
            f = mod_dir(mod_id) / "cardbacks" / c.get(k, "")
            if c.get(k) and f.is_file():
                trash(f, mod_id)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(manifest["cardbacks"])}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for c in _read(mod_id)["cardbacks"]:
        for k in ("image", "store"):
            if c.get(k) and not (mod_dir(mod_id) / "cardbacks" / c[k]).is_file():
                errors.append(f"card back {c['slug']}: missing {k} file")
        if int(c.get("price", 0)) < 0:
            errors.append(f"card back {c['slug']}: negative price")
    return errors, warnings
