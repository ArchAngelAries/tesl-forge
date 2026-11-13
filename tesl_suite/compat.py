"""Mod compatibility: load order, dependencies, declared conflicts, overlaps between mods, multiplayer class, fingerprints.

The enabled list (deploy/active-mods.json) is the load order. Where two mods change the same thing the later one wins.
The offline engine applies the same rules as plan() here (OfflineCompat.cs), so what the suite shows is what loads:
  - a mod enabled twice loads once; a mod needing a newer engine ("requires_engine") is skipped;
  - "conflicts": [ids]: the later of two conflicting enabled mods is skipped;
  - "dependencies": [{"id", "version"}]: a mod whose dependency is missing, disabled or the wrong version is skipped;
    dependencies load first; "load_after" / "load_before": [ids] order hints.
Overlaps (both load, one wins): replaced images, replaced sounds, a base board's replacement; shared: music tracks
replacing the same moment play in turn. Clashes (the later item is skipped): deck ids, card ids. Name doubles (card,
story) are warnings: names are used to look cards up.
Multiplayer class: "local" (only what the player sees or hears: remastered images, music, sounds, board skins),
"cosmetic" (others would see it: avatars, card backs, emotes), "gameplay" (cards, decks, rules, modes, stories).
The fingerprint (SHA-256 over every file) lets a server check that all players have identical mods.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import hashlib
import json
from pathlib import Path

from .mods import DEPLOY, _active, all_mod_ids, mod_dir, mod_cards, read_mod

ENGINE_LEVEL = 56          # OfflineCompat.ApiLevel of the engine this suite was made with
# The engine checkpoint that added each kind of mod content (a mod needs the highest one it uses).
FEATURE_LEVELS = {"cards": 29, "decks": 29, "image replacements": 31, "avatars": 32, "emotes": 33, "card backs": 35,
                  "boards": 41, "board edits": 45, "music": 42, "sounds": 43, "card voices": 43, "game modes": 46,
                  "stories": 48, "master difficulty": 49, "AI opponents": 53, "card packs": 54}
LOCAL = {"image replacements", "music", "sounds", "boards", "board edits"}
COSMETIC = {"avatars", "card backs", "emotes", "card voices"}


def _json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
    except (OSError, json.JSONDecodeError):
        return None


def manifest(mod_id: str) -> dict:
    m = read_mod(mod_id)
    deps = []
    for d in m.get("dependencies") or []:
        deps.append({"id": d, "version": "*"} if isinstance(d, str) else {"id": d.get("id"), "version": d.get("version") or "*"})
    return {"id": m.get("id", mod_id), "name": m.get("name", mod_id), "version": m.get("version") or "1.0.0",
            "requires_engine": int(m.get("requires_engine") or 0), "dependencies": deps,
            "conflicts": list(m.get("conflicts") or []), "load_after": list(m.get("load_after") or []), "load_before": list(m.get("load_before") or [])}


def features(mod_id: str) -> list[str]:
    root = mod_dir(mod_id)
    out = []
    if any((root / "cards").glob("*.json")) if (root / "cards").is_dir() else False:
        out.append("cards")
        if any(any((c.get("audio") or {}).values()) for c in mod_cards(mod_id)):
            out.append("card voices")
    if (root / "decks").is_dir() and any((root / "decks").glob("*.json")):
        out.append("decks")
    if ((_json(root / "replace" / "replace.json") or {}).get("images")):
        out.append("image replacements")
    if ((_json(root / "avatars" / "avatars.json") or {}).get("avatars")):
        out.append("avatars")
    if (root / "emotes" / "emotes.json").is_file():
        out.append("emotes")
    if ((_json(root / "cardbacks" / "cardbacks.json") or {}).get("cardbacks")):
        out.append("card backs")
    boards = (_json(root / "boards" / "boards.json") or {}).get("boards") or []
    if boards:
        out.append("boards")
        if any(b.get("edits") for b in boards):
            out.append("board edits")
    if ((_json(root / "music" / "music.json") or {}).get("tracks")):
        out.append("music")
    if ((_json(root / "audio" / "audio.json") or {}).get("replace")):
        out.append("sounds")
    if ((_json(root / "modes" / "modes.json") or {}).get("modes")):
        out.append("game modes")
    if ((_json(root / "opponents" / "opponents.json") or {}).get("opponents")):
        out.append("AI opponents")
    if ((_json(root / "packs" / "packs.json") or {}).get("packs")):
        out.append("card packs")
    stories = list((root / "stories").glob("*/story.json")) if (root / "stories").is_dir() else []
    if stories:
        out.append("stories")
        if any((_json(s) or {}).get("master", True) is not False for s in stories):
            out.append("master difficulty")
    return out


def required_engine(feats: list[str]) -> int:
    return max([FEATURE_LEVELS.get(f, 0) for f in feats] + [0])


def multiplayer_class(feats: list[str]) -> str:
    if any(f not in LOCAL and f not in COSMETIC for f in feats):
        return "gameplay"
    return "cosmetic" if any(f in COSMETIC for f in feats) else "local"


_FP_CACHE: dict = {}      # mod folder -> (signature, fingerprint)


def _fp_cache_file():
    from .game import workspace
    return workspace() / "cache" / "fingerprints.json"


def fingerprint(mod_id: str) -> str:
    """SHA-256 over every file of a mod (names and bytes). Hashing is skipped when no file changed: the result is remembered
    with a signature of every file's relative path, size and modification time (also between runs, in
    workspace/cache/fingerprints.json), so a second call only has to look at the folder."""
    root = mod_dir(mod_id)
    files = sorted(x for x in root.rglob("*") if x.is_file())
    sig = hashlib.sha256()
    for p in files:
        st = p.stat()
        sig.update(f"{p.relative_to(root).as_posix()}\0{st.st_size}\0{st.st_mtime_ns}\n".encode("utf-8"))
    signature = sig.hexdigest()
    key = str(root.resolve())
    hit = _FP_CACHE.get(key)
    if hit is None:
        try:
            hit = tuple(json.loads(_fp_cache_file().read_text(encoding="utf-8")).get(key) or ()) or None
        except (OSError, ValueError, AttributeError):
            hit = None
    if hit and hit[0] == signature:
        _FP_CACHE[key] = tuple(hit)
        return hit[1]
    h = hashlib.sha256()
    for p in files:
        h.update(p.relative_to(root).as_posix().encode("utf-8") + b"\0")
        h.update(p.read_bytes())
    digest = h.hexdigest()
    _FP_CACHE[key] = (signature, digest)
    try:
        f = _fp_cache_file()
        try:
            saved = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
        saved[key] = [signature, digest]
        f.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(f, json.dumps(saved), encoding="utf-8")
    except OSError:
        pass
    return digest


def stamp(mod_id: str) -> dict:
    """Record requires_engine in mod.json from the features the mod uses (the engine skips it on an older engine)."""
    path = mod_dir(mod_id) / "mod.json"
    meta = json.loads(path.read_text(encoding="utf-8"))
    level = required_engine(features(mod_id))
    if meta.get("requires_engine") != level:
        meta["requires_engine"] = level
        atomic_write(path, json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")
    return {"mod": mod_id, "requires_engine": level}


# ---- versions (as OfflineCompat.Satisfies) -------------------------------------------------------------------------
def _parse(v: str) -> tuple[int, int, int]:
    parts = (v or "0").strip().split(".")
    out = []
    for i in range(3):
        digits = ""
        for c in parts[i] if i < len(parts) else "":
            if not c.isdigit():
                break
            digits += c
        out.append(int(digits) if digits else 0)
    return tuple(out)


def satisfies(version: str, rng: str) -> bool:
    if not rng or rng.strip() == "*":
        return True
    v = _parse(version)
    for r in rng.replace(",", " ").split():
        if r.startswith(">="):
            ok = v >= _parse(r[2:])
        elif r.startswith("<="):
            ok = v <= _parse(r[2:])
        elif r.startswith(">"):
            ok = v > _parse(r[1:])
        elif r.startswith("<"):
            ok = v < _parse(r[1:])
        elif r.startswith("^"):
            w = _parse(r[1:]); ok = v[0] == w[0] and v >= w
        elif r.startswith("~"):
            w = _parse(r[1:]); ok = v[:2] == w[:2] and v >= w
        else:
            w = _parse(r.lstrip("=")); n = min(3, len(r.lstrip("=").split("."))); ok = v[:n] == w[:n]
        if not ok:
            return False
    return True


# ---- the plan (as OfflineCompat.Plan) -------------------------------------------------------------------------------
def _id_of(path: str) -> str | None:
    try:
        return json.loads((Path(path) / "mod.json").read_text(encoding="utf-8")).get("id")
    except (OSError, json.JSONDecodeError):
        return None


def plan(order: list[str] | None = None) -> dict:
    """What loads and in which order, for a list of mod ids (default: the enabled list), with every skip explained."""
    ids = order if order is not None else [i for i in (_id_of(p) for p in _active()) if i]
    problems, kept, seen = [], [], set()
    for mid in ids:
        if mid.lower() in seen:
            problems.append({"mod": mid, "severity": "error", "text": f"{mid}: enabled twice; only the first copy loads"}); continue
        seen.add(mid.lower())
        try:
            m = manifest(mid)
        except Exception as e:
            problems.append({"mod": mid, "severity": "error", "text": f"{mid}: mod.json unreadable ({e}); skipped"}); continue
        if m["requires_engine"] > ENGINE_LEVEL:
            problems.append({"mod": mid, "severity": "error", "text": f"{mid}: needs a newer TESL: Everlasting (level {m['requires_engine']}, this is {ENGINE_LEVEL}); skipped"}); continue
        kept.append(m)
    i = 0
    while i < len(kept):
        earlier = next((k for k in kept[:i] if k["id"].lower() in [c.lower() for c in kept[i]["conflicts"]] or kept[i]["id"].lower() in [c.lower() for c in k["conflicts"]]), None)
        if earlier:
            problems.append({"mod": kept[i]["id"], "severity": "error", "text": f"{kept[i]['id']}: conflicts with {earlier['id']} (enabled earlier); skipped"})
            kept.pop(i)
        else:
            i += 1
    changed = True
    while changed:
        changed = False
        for m in list(kept):
            for d in m["dependencies"]:
                found = next((k for k in kept if k["id"].lower() == (d["id"] or "").lower()), None)
                why = f"needs {d['id']}, which is not enabled" if found is None else (None if satisfies(found["version"], d["version"]) else f"needs {d['id']} {d['version']} (enabled: {found['version']})")
                if why:
                    problems.append({"mod": m["id"], "severity": "error", "text": f"{m['id']}: {why}; skipped"})
                    kept.remove(m); changed = True
                    break
            if changed:
                break
    before = {m["id"].lower(): [] for m in kept}
    for m in kept:
        for d in m["dependencies"]:
            if d["id"].lower() in before: before[m["id"].lower()].append(d["id"].lower())
        for a in m["load_after"]:
            if a.lower() in before: before[m["id"].lower()].append(a.lower())
        for b in m["load_before"]:
            if b.lower() in before: before[b.lower()].append(m["id"].lower())
    ordered, left, placed = [], list(kept), set()
    while left:
        nxt = next((m for m in left if all(x in placed for x in before[m["id"].lower()])), None)
        if nxt is None:
            nxt = left[0]
            problems.append({"mod": nxt["id"], "severity": "warning", "text": f"{nxt['id']}: load order hints form a loop; kept in list order"})
        ordered.append(nxt); placed.add(nxt["id"].lower()); left.remove(nxt)
    return {"order": [m["id"] for m in ordered], "problems": problems}


# ---- overlaps -------------------------------------------------------------------------------------------------------
def touches(mod_id: str) -> dict[str, set]:
    """What a mod changes that another mod could change too."""
    root = mod_dir(mod_id)
    t: dict[str, set] = {"image": set(), "sound": set(), "board base": set(), "music moment": set(), "card id": set(),
                         "card name": set(), "deck": set(), "story name": set()}
    for i in (_json(root / "replace" / "replace.json") or {}).get("images") or []:
        t["image"].add(i.get("asset"))
    for s in (_json(root / "audio" / "audio.json") or {}).get("replace") or []:
        t["sound"].add(s.get("target"))
    for b in (_json(root / "boards" / "boards.json") or {}).get("boards") or []:
        if b.get("mode") == "replace":
            t["board base"].add(b.get("base"))
    for tr in (_json(root / "music" / "music.json") or {}).get("tracks") or []:
        if tr.get("mode", "replace") == "replace":
            t["music moment"].update(c for c in tr.get("contexts") or [] if not c.startswith(("Board:" + mod_id + "/", "Mode:" + mod_id + "/")))
    for c in mod_cards(mod_id):
        t["card id"].add((c.get("ResourceId") or {}).get("Id"))
        if c.get("Name"):
            t["card name"].add(c["Name"].lower())
    for f in (root / "decks").glob("*.json") if (root / "decks").is_dir() else []:
        d = _json(f) or {}
        t["deck"].add(d.get("type_name"))
    for f in (root / "stories").glob("*/story.json") if (root / "stories").is_dir() else []:
        n = (_json(f) or {}).get("name")
        if n:
            t["story name"].add(n.lower())
    return {k: {x for x in v if x is not None} for k, v in t.items()}


RULES = {"image": ("overlap", "the later mod's image is used"), "sound": ("overlap", "the later mod's sound is used"),
         "board base": ("overlap", "the later mod's board replaces that base"),
         "music moment": ("shared", "their tracks play in turn there"),
         "card id": ("clash", "the later mod's card is skipped"), "deck": ("clash", "the later mod's deck is skipped"),
         "card name": ("warning", "names look cards up; give one a different name"),
         "story name": ("warning", "two stories with the same title on the story picker")}


def overlaps(order: list[str]) -> list[dict]:
    seen: dict[tuple[str, str], list[str]] = {}
    for mid in order:
        for kind, items in touches(mid).items():
            for item in items:
                seen.setdefault((kind, str(item)), []).append(mid)
    out = []
    for (kind, item), mods in sorted(seen.items()):
        if len(mods) < 2:
            continue
        what, effect = RULES[kind]
        severity = {"overlap": "info", "shared": "info", "clash": "error", "warning": "warning"}[what]
        winner = mods[-1] if what == "overlap" else mods[0] if what == "clash" else None
        out.append({"kind": kind, "target": item, "mods": mods, "result": what, "winner": winner, "severity": severity,
                    "text": f"{kind} {item}: {', '.join(mods)} - {effect}" + (f" ({winner} wins)" if winner and what == "overlap" else "")})
    return out


def report(order: list[str] | None = None) -> dict:
    """Everything about the enabled mods: load plan, skips, overlaps, and per mod its class, features and fingerprint."""
    p = plan(order)
    mods = []
    for mid in p["order"]:
        feats = features(mid)
        m = manifest(mid)
        mods.append({"id": mid, "name": m["name"], "version": m["version"], "features": feats, "class": multiplayer_class(feats),
                     "requires_engine": max(m["requires_engine"], required_engine(feats)), "fingerprint": fingerprint(mid)[:16],
                     "dependencies": m["dependencies"], "conflicts": m["conflicts"]})
    ov = overlaps(p["order"])
    errors = [x for x in p["problems"] + ov if x["severity"] == "error"]
    return {"order": p["order"], "requested": order if order is not None else [i for i in (_id_of(x) for x in _active()) if i],
            "mods": mods, "problems": p["problems"], "overlaps": ov, "ok": not errors, "engine_level": ENGINE_LEVEL}


def set_order(ids: list[str]) -> dict:
    """Write the enabled list in this order (ids must be installed mods; ids left out are disabled)."""
    installed = set(all_mod_ids())
    unknown = [i for i in ids if i not in installed]
    if unknown:
        raise ValueError(f"not installed: {', '.join(unknown)}")
    paths = [str(mod_dir(i).resolve()) for i in ids]
    from .mods import write_active
    write_active(paths)
    return report(ids)


def auto_order() -> dict:
    """Sort the enabled list the way the engine will load it (dependencies and hints applied; skipped mods kept last)."""
    current = report()["requested"]
    p = plan(current)
    rest = [i for i in current if i not in p["order"]]
    return set_order(p["order"] + rest)


def check_enable(mod_id: str) -> dict:
    """The report as it would be with this mod enabled at the end of the list; its own errors block enabling."""
    current = report()["requested"]
    rep = report([i for i in current if i != mod_id] + [mod_id])
    mine = [x for x in rep["problems"] if x["mod"] == mod_id] + [x for x in rep["overlaps"] if x["severity"] == "error" and mod_id in x["mods"]]
    return {"mod": mod_id, "blocked": [x["text"] for x in mine if x["severity"] == "error"], "report": rep}
