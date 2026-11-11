"""Image replacement (remastering): a mod swaps original images the game loads by asset path (card art, avatars, deck
banners, arena and profile images) without touching game files. The offline engine serves the new image in place of the
original and keeps its on-screen size, so a higher-resolution remaster drops in.

Layout: mods/<id>/replace/replace.json + the PNG files beside it. Each entry records the game's asset path (as the game
asks for it: 'ContentPack000/Cards/Visuals/x/x', no 'Assets/' prefix, no extension) and the original sprite's size,
pixels-per-unit, pivot and 9-slice border, read from the bundle when the replacement is added.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
from pathlib import Path

from . import assets
from .game import GameInstall
from .mods import find_card, mod_dir, read_mod

MAX_SIDE = 4096


def game_path(index_path: str) -> str:
    """'Assets/ContentPack000/.../x.png' -> 'ContentPack000/.../x' (the path the game loads)."""
    p = index_path
    if p.lower().startswith("assets/"):
        p = p[7:]
    stem, dot, ext = p.rpartition(".")
    return stem if dot and "/" not in ext else p


def resolve(game: GameInstall, asset: str | None = None, card: str | None = None) -> dict:
    """Find the texture entry for an asset path (game or bundle form) or a card's art."""
    if card:
        c = find_card(game, card)
        asset = c.get("Image")
        if not asset:
            raise ValueError(f"{c['Name']} has no art path")
        if asset.startswith("Mods/"):
            raise ValueError(f"{c['Name']} is a mod card: replace its art in its own mod instead")
    if not asset:
        raise ValueError("give --asset or --card")
    want = game_path(asset).lower()
    for e in assets.load_index(game)["entries"]:
        if e["kind"] == "texture" and game_path(e["path"]).lower() == want:
            return e
    raise ValueError(f"No texture asset '{asset}' in the game's bundles (search with: tesl assets list --kind texture --contains ...)")


def original_info(game: GameInstall, entry: dict) -> dict:
    """Size of the original texture, plus its sprite's rectangle, pixels-per-unit, pivot and border if it has one."""
    import UnityPy
    env = UnityPy.load(str(Path(game.streaming_assets) / entry["bundle"]))
    key = entry["path"].lower()
    info = {}
    for path, obj in env.container.items():
        if path.lower() != key:
            continue
        d = obj.read()
        if obj.type.name == "Texture2D":
            info.update(width=d.m_Width, height=d.m_Height)
        elif obj.type.name == "Sprite":
            r, pv, b = d.m_Rect, d.m_Pivot, d.m_Border
            info.update(sprite_rect=[round(r.x), round(r.y), round(r.width), round(r.height)], ppu=float(d.m_PixelsToUnits),
                        pivot=[float(pv.x), float(pv.y)], border=[float(b.x), float(b.y), float(b.z), float(b.w)])
    if "sprite_rect" in info:
        # The game loads this path as a Sprite (possibly cut from a shared sprite sheet): the replacement stands in for
        # the whole sprite, so the sprite's own rectangle is the size to match.
        info["texture_size"] = [info.get("width"), info.get("height")]
        info["width"], info["height"] = info["sprite_rect"][2], info["sprite_rect"][3]
    if not info.get("width"):
        raise ValueError(f"{entry['path']} is not a readable texture")
    return info


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "replace" / "replace.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "images": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    manifest["images"].sort(key=lambda x: x["asset"].lower())
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def fit(src: Path, dest: Path, width: int, height: int, mode: str = "crop") -> tuple[int, int]:
    """Match the original's aspect ratio. Keeps the new image's resolution (a remaster may be larger), never smaller than
    the original, at most MAX_SIDE. crop = cover and centre-crop; stretch = resize to the aspect."""
    from PIL import Image
    img = Image.open(src).convert("RGBA")
    aspect = width / height
    w, h = img.size
    if mode == "crop":
        if w / h > aspect:
            nw = round(h * aspect); img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = round(w / aspect); img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
    scale = max(width / img.width, height / img.height, 1.0) if mode == "crop" else max(width / w, 1.0)
    tw = max(width, round(img.width * scale)) if mode == "crop" else max(width, w)
    tw = min(tw, MAX_SIDE if aspect >= 1 else round(MAX_SIDE * aspect))
    th = round(tw / aspect)
    img = img.resize((tw, th), Image.LANCZOS)
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return tw, th


def add(game: GameInstall, mod_id: str, image: str, asset: str | None = None, card: str | None = None, mode: str = "crop") -> dict:
    read_mod(mod_id)
    src = Path(image)
    if not src.is_file():
        raise ValueError(f"Image not found: {image}")
    entry = resolve(game, asset, card)
    info = original_info(game, entry)
    gp = game_path(entry["path"])
    name = gp.replace("/", "__") + ".png"
    w, h = fit(src, mod_dir(mod_id) / "replace" / name, info["width"], info["height"], mode)
    record = {"asset": gp, "file": name, "width": w, "height": h, "bundle_path": entry["path"],
              "original": {k: info[k] for k in ("width", "height", "ppu", "pivot", "border") if k in info}}
    manifest = _read(mod_id)
    manifest["images"] = [x for x in manifest["images"] if x["asset"].lower() != gp.lower()] + [record]
    _write(mod_id, manifest)
    return {"mod": mod_id, "replaced": record, "total": len(manifest["images"])}


def remove(mod_id: str, asset: str) -> dict:
    manifest = _read(mod_id)
    gp = game_path(asset).lower()
    gone = [x for x in manifest["images"] if x["asset"].lower() == gp]
    if not gone:
        raise ValueError(f"{mod_id} does not replace '{asset}'")
    manifest["images"] = [x for x in manifest["images"] if x["asset"].lower() != gp]
    for x in gone:
        f = mod_dir(mod_id) / "replace" / x["file"]
        if f.is_file():
            trash(f, mod_id)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0]["asset"], "total": len(manifest["images"])}


def list_replacements(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "images": _read(mod_id)["images"]}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    """(errors, warnings) for mod validate."""
    errors, warnings = [], []
    for x in _read(mod_id)["images"]:
        f = mod_dir(mod_id) / "replace" / x["file"]
        if not f.is_file():
            errors.append(f"replacement for {x['asset']}: missing file {x['file']}")
        o = x.get("original", {})
        if o.get("width") and abs(x["width"] / x["height"] - o["width"] / o["height"]) > 0.01:
            warnings.append(f"replacement for {x['asset']}: aspect differs from the original")
    return errors, warnings
