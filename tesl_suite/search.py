"""Search across every mod: cards, decks, avatars, AI opponents, card backs, boards, music, sounds, game modes, stories and
replaced game images. Answers "which mod has X?" and "which mods replace this asset?" (the later one in load order wins).
"""
from __future__ import annotations

import json

from .mods import all_mod_ids, list_mods, mod_dir


def _items(mod_id: str):
    from . import avatars, boards, cardbacks, modes, music, opponents, replace, sounds, stories
    from .mods import mod_cards
    for c in mod_cards(mod_id):
        yield "cards", c.get("Name") or "", c.get("Description") or "", "cards"
    for f in sorted((mod_dir(mod_id) / "decks").glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        yield "decks", d.get("name") or f.stem, " ".join(e.get("name", "") for e in d.get("cards", [])), "decks"
    for a in avatars.list_avatars(mod_id)["avatars"]:
        yield "avatars", a["name"], "", "avatars"
    for o in opponents.list_opponents(mod_id)["opponents"]:
        yield "AI opponents", o["name"], o.get("title", ""), "opponents"
    for c in cardbacks.list_cardbacks(mod_id)["cardbacks"]:
        yield "card backs", c["name"], "", "cardbacks"
    for b in boards.list_boards(mod_id)["boards"]:
        yield "boards", b["name"], f"{b.get('base', '')} {b.get('mode', '')}", "boards"
    for t in music.list_tracks(mod_id)["tracks"]:
        yield "music", t["name"], " ".join(t.get("contexts") or []), "music"
    for s in sounds.list_replacements(mod_id)["sounds"]:
        yield "sounds", s["label"], " ".join(s["targets"]), "sounds"
    for m in modes.list_modes(mod_id)["modes"]:
        yield "game modes", m["name"], m.get("description", ""), "modes"
    for s in stories.list_stories(mod_id)["stories"]:
        yield "stories", s["name"], s.get("description", ""), "stories"
    for r in replace.list_replacements(mod_id)["images"]:
        yield "replaced images", r["asset"], r.get("file", ""), "remaster"


def search(query: str, limit: int = 200) -> dict:
    q = (query or "").strip().lower()
    if len(q) < 2:
        raise ValueError("type at least 2 letters")
    words = q.split()
    order = [m["id"] for m in list_mods() if m["enabled"]]
    hits = []
    for mod_id in all_mod_ids():
        try:
            for kind, name, extra, view in _items(mod_id):
                text = f"{name} {extra}".lower()
                if all(w in text for w in words):
                    hits.append({"mod": mod_id, "kind": kind, "name": name, "view": view, "enabled": mod_id in order,
                                 "exact": name.lower() == q})
        except Exception:   # one broken mod never stops the search
            continue
    hits.sort(key=lambda h: (not h["exact"], h["kind"], h["name"].lower(), h["mod"]))
    # Who wins a replaced image: the enabled mod latest in load order.
    winners = {}
    for h in hits:
        if h["kind"] == "replaced images" and h["enabled"]:
            cur = winners.get(h["name"].lower())
            if cur is None or order.index(h["mod"]) > order.index(cur):
                winners[h["name"].lower()] = h["mod"]
    for h in hits:
        if h["kind"] == "replaced images":
            w = winners.get(h["name"].lower())
            h["note"] = ("shown in game" if w == h["mod"] else f"overridden by {w}") if h["enabled"] and w else "mod not enabled"
    return {"query": query, "total": len(hits), "results": hits[:limit]}
