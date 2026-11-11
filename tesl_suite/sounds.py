"""Sound effects and voices: replace any of the game's sounds, and give mod cards their own voice lines.

The game's sounds, labelled (`catalog`): card voices ("Fiery Imp - attacks"), card sound effects, emote lines, board
and story dialogue, the arena announcer, cinematics and interface/effect sounds. A sound can have several takes
(variations, e.g. ..._01, ..._02); a replacement covers all of them and all languages. Give several files to have the
game pick one at random each time.

Mod card voice lines (`card_voice`): Play (enters play), Attack, Death (last gasp), Hit, Success, Failure. A line you
don't set keeps the voice of the card the mod card was made from.

Layout: mods/<id>/audio/audio.json {"format":1,"replace":[{"sound","target","files","volume"}]} + audio files;
card lines in the card's json: "audio": {"Play": "audio/cards/<slug>-play.ogg"}.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
import re
from pathlib import Path

from .game import GameInstall
from .mods import mod_dir, read_mod, slugify
from .music import _to_ogg

SLOTS = {"Play": "enters play", "Attack": "attacks", "Death": "last gasp", "Hit": "is hit", "Success": "success", "Failure": "failure"}
# A shout card's own clip for each shout level (level 1 = first word ... level 3 = all three). The engine plays it in place
# of the level sound of the shout effect the card uses (e.g. unrelenting_force_02 at level 2), for that card only.
SHOUT_SLOTS = {"Shout1": "shout level 1", "Shout2": "shout level 2", "Shout3": "shout level 3"}
ALL_SLOTS = {**SLOTS, **SHOUT_SLOTS}
CATEGORIES = [("card-voice", "Card voice"), ("card-sfx", "Card sound effect"), ("emote", "Emote line"), ("board-dialogue", "Board dialogue"),
              ("story", "Story dialogue"), ("announcer", "Arena announcer"), ("cinematic", "Cinematic"), ("ui", "Interface & effects")]
_LABEL = dict(CATEGORIES)
_CATALOG: list[dict] | None = None


def _workspace() -> Path:
    from .game import SUITE_ROOT
    return Path(SUITE_ROOT) / "workspace"


ABBREV = {"amb": "ambience", "lp": "loop", "sfx": "sound", "btn": "button", "vo": "voice", "fx": "effect", "lrg": "large", "sml": "small",
          "db": "deck builder", "iom": "Isle of Madness", "cwc": "story", "esl": "", "ui": "interface", "mus": "music"}


def _human(name: str) -> str:
    words = re.sub(r"\s+", " ", name.replace("_", " ").replace("-", " ")).strip().split(" ")
    words = [ABBREV.get(w.lower(), w) for w in words]
    text = " ".join(w for w in words if w)
    return text[:1].upper() + text[1:] if text else name

EMOTE_KINDS = ["good_game", "thank_you", "nice_play", "hello", "implore", "taunt", "oops", "sorry", "greeting", "threaten", "wow", "well_played"]
PACKS = {"IOM": "Isle of Madness", "HOM": "Houses of Morrowind", "AW": "Alliance War", "ELS": "Moons of Elsweyr", "OC": "Forgotten Hero"}


def _texts(game: GameInstall) -> dict[str, str]:
    """The game's English text by lower-case key (many dialogue clips are named after the line they speak)."""
    from . import assets
    out = _workspace() / "cache" / "loc"
    f = out / "data.json"
    if not f.is_file() and game is not None:
        assets.export(game, [{"bundle": "appbase/en_us", "path": "Assets/AppBase/Localization/Text/en_US/data.json", "kind": "text"}], out)
    if not f.is_file():
        return {}
    return {k.lower(): v for k, v in json.loads(f.read_text(encoding="utf-8")).items() if isinstance(v, str)}


def _quote(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text).replace("\n", " ").strip()
    return "\u201c" + (text if len(text) <= 70 else text[:67].rstrip() + "...") + "\u201d"


def _nice_label(cat: str, base: str, clips: list[str], texts: dict[str, str]) -> str:
    line = next((texts[c.lower()] for c in [base] + clips if c.lower() in texts), None)
    m = re.match(r"(?i)^(IOM|HOM|AW|ELS|OC)_(PlaymatDialogue|UIDialogue|AvatarEmote)_(.*)$", base)
    if m:
        rest = m.group(3).split("_")
        speaker = next((rest[i + 1] for i, w in enumerate(rest[:-1]) if re.search(r"(MALE|FEMALE)$", w)), rest[-2] if len(rest) > 1 else "")
        ep = next((w.replace("Episode", "episode ") for w in rest if w.startswith("Episode")), "")
        num = rest[-1].lstrip("0") if rest and rest[-1].isdigit() else ""
        where = " ".join(x for x in [PACKS.get(m.group(1).upper(), m.group(1)), ep] if x)
        head = f"{where}: {speaker.title()}" + (f" (line {num})" if num else "")
        return head + (" - " + _quote(line) if line else "")
    if cat == "emote":
        kind = next((k for k in EMOTE_KINDS if base.lower().endswith("_" + k)), None)
        if kind:
            who = base[: -len(kind) - 1].split("_")
            if len(who) >= 3 and who[-2] in ("male", "female"):
                return f"{_human(' '.join(who[:-2]))} {who[-2]} voice {who[-1].upper()} - {_human(kind)}"
            return f"{_human(' '.join(who))} - {_human(kind)}"
    if cat == "announcer":
        for prefix in ("feature_match", "select", "lane", "scenario", "victory", "defeat", "round"):
            if base.lower().startswith(prefix + "_"):
                return f"{_human(prefix)}: {_human(base[len(prefix) + 1:])}"
    if line:
        return _quote(line)
    return _human(base)


def _category(path: str) -> tuple[str, str] | None:
    """(category, language folder) for an audio asset path, or None for other languages."""
    parts = path.split("/")
    lang = parts[-2] if len(parts) >= 3 and parts[-3] == "Clips" else ""
    if lang and lang not in ("en_US", "SFX"):
        return None
    low = path.lower()
    if "/cards/audio/" in low:
        return ("card-sfx" if lang == "SFX" else "card-voice"), lang
    for key, cat in (("/audio/useremote/", "emote"), ("/audio/scenarioemote/", "board-dialogue"), ("/audio/storydialogue/", "story"),
                     ("/audio/arenavo/", "announcer"), ("/videos/", "cinematic")):
        if key in low:
            return cat, lang
    return "ui", lang


def catalog(game: GameInstall, refresh: bool = False) -> list[dict]:
    """Every original sound with a plain label. Cached in the workspace."""
    global _CATALOG
    cache = _workspace() / "sound-catalog.json"
    if _CATALOG is not None and not refresh:
        return _CATALOG
    if cache.is_file() and not refresh:
        _CATALOG = json.loads(cache.read_text(encoding="utf-8"))
        return _CATALOG
    from . import assets
    from .cards import load_sets
    voice = {}
    for s in load_sets(game):
        for c in s.get("Cards") or []:
            if not c:
                continue
            for slot, what in SLOTS.items():
                ev = c.get(f"{slot}CardVO")
                if ev:
                    voice.setdefault(ev.lower(), f"{c.get('Name')} - {what}")
    texts = _texts(game)
    groups: dict[str, dict] = {}
    for e in assets.load_index(game)["entries"]:
        if e["kind"] != "audio":
            continue
        cat = _category(e["path"])
        if cat is None:
            continue
        clip = Path(e["path"]).stem
        base = re.sub(r"[ _]\d{1,2}$", "", clip)
        key = f"{cat[0]}:{base.lower()}"
        g = groups.get(key)
        if g is None:
            label = voice.get(base.lower()) or voice.get(clip.lower())
            if not label and cat[0] in ("card-voice", "card-sfx"):
                stem = re.sub(r"_(enter_play|attack|last_gasp|hit|exalt|pilfer|slay|summon)(_.*)?$", "", base)
                action = base[len(stem):].strip("_")
                label = _human(stem) + (" - " + action.replace("_", " ") if action else "")
            g = groups[key] = {"id": key, "category": cat[0], "category_label": _LABEL[cat[0]], "label": label, "base": base,
                               "clips": [], "preview": e["path"]}
        if clip not in g["clips"]:
            g["clips"].append(clip)
    names: dict[str, list[dict]] = {}
    for g in groups.values():
        for c in g["clips"]:
            names.setdefault(c.lower(), []).append(g)
    for g in groups.values():
        shared = {o["id"] for c in g["clips"] for o in names[c.lower()] if o is not g}
        if shared:
            g["shares_with"] = sorted(shared)     # same clip names: the game can't tell them apart, so both change
    for g in groups.values():
        if not g["label"]:
            g["label"] = _nice_label(g["category"], g["base"], g["clips"], texts)
        del g["base"]
    _CATALOG = sorted(groups.values(), key=lambda g: (g["category"], g["label"].lower()))
    cache.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(cache, json.dumps(_CATALOG, ensure_ascii=False), encoding="utf-8")
    return _CATALOG


def search(game: GameInstall, q: str | None = None, category: str | None = None, limit: int = 100) -> dict:
    rows = catalog(game)
    if category:
        rows = [r for r in rows if r["category"] == category]
    if q:
        words = q.lower().split()
        rows = [r for r in rows if all(w in (r["label"] + " " + r["id"]).lower() for w in words)]
    return {"total": len(rows), "sounds": rows[:limit], "categories": [{"id": k, "label": v} for k, v in CATEGORIES]}


def find_sound(game: GameInstall, ref: str) -> dict:
    rows = catalog(game)
    low = ref.lower()
    hit = next((r for r in rows if r["id"].lower() == low), None) or next((r for r in rows if low in [c.lower() for c in r["clips"]]), None)
    if hit is None:
        exact = [r for r in rows if r["label"].lower() == low]
        hit = exact[0] if len(exact) == 1 else None
    if hit is None:
        raise ValueError(f"No game sound '{ref}': search with `tesl sound search <words>`")
    return hit


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "audio" / "audio.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "replace": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def replace_sound(game: GameInstall, mod_id: str, sound: str, files: list[str], volume: float = 1.0) -> dict:
    read_mod(mod_id)
    s = find_sound(game, sound)
    if not files:
        raise ValueError("give at least one audio file")
    slug = slugify(s["id"].split(":", 1)[1])
    stored, seconds = [], []
    for i, f in enumerate(files):
        src = Path(f)
        if not src.is_file():
            raise ValueError(f"Audio not found: {f}")
        secs, dest = _to_ogg(src, mod_dir(mod_id) / "audio" / f"{slug}-{i + 1}.ogg")
        stored.append(dest.name)
        seconds.append(round(secs, 1))
    manifest = _read(mod_id)
    old = {Path(f).name for r in manifest["replace"] if r.get("sound") == s["id"] for f in r["files"]}
    manifest["replace"] = [r for r in manifest["replace"] if r.get("sound") != s["id"]]
    manifest["replace"] += [{"sound": s["id"], "label": s["label"], "target": clip, "files": stored, "volume": float(volume)} for clip in s["clips"]]
    for name in old - set(stored):
        (mod_dir(mod_id) / "audio" / name).unlink(missing_ok=True)
    _write(mod_id, manifest)
    return {"mod": mod_id, "sound": s["id"], "label": s["label"], "takes": len(s["clips"]), "files": stored, "seconds": seconds}


def list_replacements(mod_id: str) -> dict:
    read_mod(mod_id)
    out: dict[str, dict] = {}
    for r in _read(mod_id)["replace"]:
        g = out.setdefault(r.get("sound") or r["target"], {"sound": r.get("sound") or r["target"], "label": r.get("label") or r["target"],
                                                         "files": r["files"], "volume": r.get("volume", 1.0), "targets": []})
        g["targets"].append(r["target"])
    return {"mod": mod_id, "sounds": list(out.values())}


def remove_replacement(mod_id: str, sound: str) -> dict:
    manifest = _read(mod_id)
    gone = [r for r in manifest["replace"] if sound in (r.get("sound"), r["target"])]
    if not gone:
        raise ValueError(f"{mod_id} does not replace '{sound}'")
    manifest["replace"] = [r for r in manifest["replace"] if r not in gone]
    keep = {f for r in manifest["replace"] for f in r["files"]}
    for f in {f for r in gone for f in r["files"]} - keep:
        (mod_dir(mod_id) / "audio" / f).unlink(missing_ok=True)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0].get("sound") or sound}


def _card_file(mod_id: str, card: str) -> Path:
    d = mod_dir(mod_id) / "cards"
    for f in sorted(d.glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if card.lower() in (f.stem.lower(), str(c.get("Name", "")).lower(), str(c["ResourceId"]["Id"])):
            return f
    raise ValueError(f"{mod_id} has no card '{card}'")


def _slot(name: str) -> str:
    slot = next((s for s in ALL_SLOTS if s.lower() == name.lower() or ALL_SLOTS[s] == name.lower()), None)
    if slot is None:
        raise ValueError(f"Unknown voice line '{name}': one of {', '.join(ALL_SLOTS)}")
    return slot


def card_voice(mod_id: str, card: str, line: str, file: str) -> dict:
    """The mod card's own line (Play, Attack, Death, Hit, Success or Failure), or a shout card's clip for a shout
    level (Shout1, Shout2, Shout3)."""
    read_mod(mod_id)
    f = _card_file(mod_id, card)
    slot = _slot(line)
    c = json.loads(f.read_text(encoding="utf-8"))
    slug = c["ResourceId"]["UniqueName"]
    src = Path(file)
    if not src.is_file():
        raise ValueError(f"Audio not found: {file}")
    secs, dest = _to_ogg(src, mod_dir(mod_id) / "audio" / "cards" / f"{slug}-{slot.lower()}.ogg")
    c.setdefault("audio", {})[slot] = f"audio/cards/{dest.name}"
    if slot in SLOTS and not c.get(f"{slot}CardVO"):
        c[f"{slot}CardVO"] = f"mod_{slug}_{slot.lower()}"          # the template has no such line: an event of its own
    atomic_write(f, json.dumps(c, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"mod": mod_id, "card": c.get("Name"), "line": slot, "file": c["audio"][slot], "seconds": round(secs, 1)}


def is_shout(card: dict) -> bool:
    """A shout card: its text tracks a shout level (DynamicTextAssignments Method "ShoutLevel")."""
    return any((d or {}).get("Method") == "ShoutLevel" for d in card.get("DynamicTextAssignments") or [])


def card_voices(mod_id: str) -> dict:
    read_mod(mod_id)
    out = []
    for f in sorted((mod_dir(mod_id) / "cards").glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        out.append({"card": c.get("Name"), "slug": c["ResourceId"]["UniqueName"], "voice_of": (c.get("_mod") or {}).get("template_name") or c.get("template_name"),
                    "shout": is_shout(c),
                    "lines": {s: (c.get("audio") or {}).get(s) for s in ALL_SLOTS}})
    return {"mod": mod_id, "cards": out, "slots": ALL_SLOTS}


def remove_card_voice(mod_id: str, card: str, line: str) -> dict:
    f = _card_file(mod_id, card)
    slot = _slot(line)
    c = json.loads(f.read_text(encoding="utf-8"))
    rel = (c.get("audio") or {}).pop(slot, None)
    if rel is None:
        raise ValueError(f"{c.get('Name')} has no own {slot} line")
    (mod_dir(mod_id) / rel).unlink(missing_ok=True)
    if slot in SLOTS and str(c.get(f"{slot}CardVO") or "").startswith("mod_"):
        c[f"{slot}CardVO"] = None
    if not c["audio"]:
        del c["audio"]
    atomic_write(f, json.dumps(c, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"mod": mod_id, "card": c.get("Name"), "removed": slot}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors = []
    for r in _read(mod_id)["replace"]:
        for f in r["files"]:
            if not (mod_dir(mod_id) / "audio" / f).is_file():
                errors.append(f"sound {r.get('label') or r['target']}: missing {f}")
    for f in sorted((mod_dir(mod_id) / "cards").glob("*.json")) if (mod_dir(mod_id) / "cards").is_dir() else []:
        c = json.loads(f.read_text(encoding="utf-8"))
        for slot, rel in (c.get("audio") or {}).items():
            if slot not in ALL_SLOTS:
                errors.append(f"card {c.get('Name')}: unknown voice line {slot}")
            elif not (mod_dir(mod_id) / rel).is_file():
                errors.append(f"card {c.get('Name')}: {slot} line file missing")
    return errors, []
