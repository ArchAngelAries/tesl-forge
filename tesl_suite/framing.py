"""Card art framing: where a mod card's art sits in the card's art window.

The game places card art with three fields of the card (ImageScale, ImageOffsetX, ImageOffsetY). Measured in TESL:
Everlasting's own card renderer (2026-11-10, a position-coded gradient image), the part of a square art image that the
card's art window shows, in image fractions (x right, y down from the top), is:

    width  = 0.537 * scale            height = 0.645 * scale
    centre x = 0.503 + 0.505 * (scale - 1) + ImageOffsetX
    centre y = 0.432 - 0.566 * (scale - 1) - ImageOffsetY

So scale above 1 shows more of the picture (the art looks smaller), +X shows more of the right side, +Y more of the
top. When the window runs past the picture's edge the game smears the edge pixels, so a good frame keeps the window
inside the picture. The top of the window sits under the card's name plate.
"""
from __future__ import annotations

import json
from pathlib import Path

from .fsutil import atomic_write
from .mods import mod_dir, read_mod

W0, H0 = 0.537, 0.645
CX0, CX1 = 0.503, 0.505
CY0, CY1 = 0.432, -0.566
NAME_PLATE = 0.06          # share of the window height hidden under the name/type plates
MAX_SCALE = 1.5            # the window's height stays inside the picture up to about 1.55


def window(scale: float, x: float = 0.0, y: float = 0.0) -> tuple[float, float, float, float]:
    """(left, top, right, bottom) of the visible window, in image fractions."""
    w, h = W0 * scale, H0 * scale
    cx = CX0 + CX1 * (scale - 1) + x
    cy = CY0 + CY1 * (scale - 1) - y
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def offsets(scale: float, cx: float, cy: float) -> tuple[float, float]:
    """ImageOffsetX/Y that centre the window on (cx, cy) at this scale."""
    return round(cx - (CX0 + CX1 * (scale - 1)), 3), round((CY0 + CY1 * (scale - 1)) - cy, 3)


def visible_inside(scale: float, x: float, y: float, tolerance: float = 0.01) -> bool:
    l, t, r, b = window(scale, x, y)
    return l >= -tolerance and t >= -tolerance and r <= 1 + tolerance and b <= 1 + tolerance


def fit(keep: tuple[float, float, float, float], start_scale: float = 1.05, max_scale: float = 1.25) -> dict:
    """The gentlest frame that shows the `keep` box (x0, y0, x1, y1 in image fractions: a head with a little hair and
    chin) below the name plate: first shift the window to the head (scale `start_scale`, a slight step back), and step
    back further only while the head still doesn't fit inside the picture, up to `max_scale`."""
    x0, y0, x1, y1 = keep
    scale = start_scale
    while True:
        w, h = W0 * scale, H0 * scale
        plate = NAME_PLATE * h + 0.02 * h
        cy = (y0 - plate) + h / 2                        # head top just below the name plate
        cy = min(max(cy, h / 2), 1 - h / 2)              # window stays inside the picture
        cx = min(max((x0 + x1) / 2, w / 2), 1 - w / 2)
        top = cy - h / 2 + plate
        fits = y0 >= top - 0.005 and y1 <= cy + h / 2 - 0.25 * h and x0 >= cx - w / 2 and x1 <= cx + w / 2
        if fits or scale >= max_scale:
            break
        scale = round(scale + 0.02, 2)
    x, y = offsets(scale, cx, cy)
    return {"scale": round(scale, 2), "x": x, "y": y, "window": [round(v, 3) for v in window(scale, x, y)]}


def top_frame(scale: float = 1.12, top: float = 0.0) -> dict:
    """A slight step back with the window anchored at the top of the picture and centred across it: generated card
    art puts the subject's head in its upper part, so this shows the whole head without running past the edges."""
    w, h = W0 * scale, H0 * scale
    cy = min(top + h / 2, 1 - h / 2)
    x, y = offsets(scale, 0.5, cy)
    return {"scale": scale, "x": x, "y": y, "window": [round(v, 3) for v in window(scale, x, y)]}


def head_cut(face: tuple[float, float, float, float], scale: float, x: float, y: float) -> bool:
    """True when the face itself (not just hair) reaches above the name plate or past a side of the window."""
    l, t, r, b = window(scale, x, y)
    return face[1] < t + NAME_PLATE * H0 * scale or face[0] < l or face[2] > r


def default_frame(scale: float = 1.2) -> dict:
    """For art with no head to find (items, creatures, scenes): a slight step back, centred a little high so the name
    plate doesn't cover the subject's top."""
    w, h = W0 * scale, H0 * scale
    cy = max(h / 2, 0.47)
    x, y = offsets(scale, 0.5, min(cy, 1 - h / 2))
    return {"scale": scale, "x": x, "y": y, "window": [round(v, 3) for v in window(scale, x, y)]}


def _card_path(mod_id: str, card: str) -> Path:
    d = mod_dir(mod_id) / "cards"
    for f in sorted(d.glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if card.lower() in (f.stem.lower(), str(c.get("Name", "")).lower(), str(c["ResourceId"]["Id"])):
            return f
    raise ValueError(f"{mod_id} has no card '{card}'")


def current(mod_id: str, card: str) -> dict:
    c = json.loads(_card_path(mod_id, card).read_text(encoding="utf-8"))
    s, x, y = float(c.get("ImageScale") or 1.0), float(c.get("ImageOffsetX") or 0.0), float(c.get("ImageOffsetY") or 0.0)
    return {"scale": s, "x": x, "y": y, "window": [round(v, 3) for v in window(s, x, y)]}


def set_frame(mod_id: str, card: str, scale: float, x: float, y: float) -> dict:
    """Write a card's art frame (ImageScale/ImageOffsetX/ImageOffsetY). The art file itself is not touched."""
    read_mod(mod_id)
    if not 0.5 <= scale <= 2.0:
        raise ValueError("scale must be between 0.5 and 2.0")
    path = _card_path(mod_id, card)
    c = json.loads(path.read_text(encoding="utf-8"))
    before = {"scale": c.get("ImageScale"), "x": c.get("ImageOffsetX"), "y": c.get("ImageOffsetY")}
    c["ImageScale"], c["ImageOffsetX"], c["ImageOffsetY"] = round(scale, 3), round(x, 3), round(y, 3)
    atomic_write(path, json.dumps(c, indent=1, ensure_ascii=False))
    return {"mod": mod_id, "card": c.get("Name"), "before": before, "after": {"scale": c["ImageScale"], "x": c["ImageOffsetX"], "y": c["ImageOffsetY"]},
            "inside_picture": visible_inside(scale, x, y)}


def small_frames(focus: float = 0.15, hanger_scale: float = 1.0, history_scale: float = 1.75) -> dict:
    """Framing of the small views (deck list row, history log, hover strip) for art whose subject's face or centre sits at
    height `focus` (0 = top). Measured with the game's own deck-list row (2026-11-13): at ListImageScale 1 the row shows an
    18%-tall band whose top is at 0.41 + ListImageOffsetY, so the band is centred on the focus; ListImageOffsetX 0.12 moves a
    centred face right of the card name (the art centre otherwise sits at 66% of the row, under longer names). History and hover views
    shift towards the focus only as far as the art still fills their frame. Generated portraits have faces near 0.12-0.17."""
    def clamp(v, lo, hi):
        return max(lo, min(hi, v))
    out = {"ListImageScale": 1.0, "ListImageOffsetX": 0.12, "ListImageOffsetY": round(clamp(focus - 0.50, -0.41, 0.41), 3)}
    for pre, s in (("HangerImage", hanger_scale), ("HistoryLogItemImage", history_scale)):
        room = max(0.0, (s - 1.0) / 2.0)
        out[pre + "Scale"], out[pre + "OffsetX"], out[pre + "OffsetY"] = s, 0.0, round(clamp((focus - 0.5) * s, -room, room), 3)
    return out
