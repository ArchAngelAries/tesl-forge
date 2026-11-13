"""Stories: DLC-sized story campaigns played from the offline game's Story menu.

A story has acts; an act has chapters (episodes); a chapter has a map picture with events placed on it (location
discs). An event is dialogue (lines with a speaker, portrait, optional voice file and up to three choices; a choice
can give a card or gold) and/or a battle. Battles use the game-mode setup (lanes, each side's health, magicka, runes,
deck and starting cards, first player, turn rules, board, music, gold) plus the opponent's name and portrait, a
briefing shown before the match and lines the opponent says when beaten. Events can require earlier events or
choices ("requires"), so stories branch; an event can hold several battles, picked by the choice made in its intro.
Rewards per event: gold, cards, packs, XP, gems.
Master difficulty (unlocked after Normal, as the game's own stories): every battle also has a Master version, by default
the same battle against an Expert AI; a battle's "master" object changes anything for Master (e.g. {"opponent": {"health": 30}}),
an event's "master_rewards" replaces its rewards on Master, and "master": false on the story turns Master off.
A chapter's "coin" is the picture for its lines without a portrait (the narrator).

Layout: mods/<id>/stories/<slug>/story.json plus its images and voice files. Images are files in that folder or
"asset:<installed image path>" (any installed map, disc or portrait, or the game's own story art: story tiles and banners,
act and chapter pictures). Pictures: the story's "icon" (picker tile) and "banner", each act's and chapter's "icon". Map positions x/y are fractions of the map
picture from its top-left corner.
In the game: Play > Story, then the story's tile.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash
from .settings import find_tool as _tool

import json
import shutil
import subprocess
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

TEMPLATES = {"DBH": "The Fall of the Dark Brotherhood", "CWC": "Return to Clockwork City", "IOM": "Isle of Madness"}
SKINS = ["template", "none", "DBH", "CWC", "IOM"]
IMAGE_TYPES = {".png", ".jpg", ".jpeg"}
VOICE_TYPES = {".wav", ".ogg", ".mp3", ".flac", ".m4a"}
REWARDS = {"gold": "gold", "card": "a card (name)", "pack": "a card pack (core, skyrim, morrowind, alliancewar, elsweyr, oblivion)", "xp": "experience", "gems": "gems"}
PACKS = ["core", "skyrim", "morrowind", "alliancewar", "elsweyr", "oblivion"]


def _root(mod_id: str) -> Path:
    return mod_dir(mod_id) / "stories"


def story_dir(mod_id: str, story: str) -> Path:
    d = _root(mod_id) / slugify(story)
    if not (d / "story.json").is_file():
        raise ValueError(f"{mod_id} has no story '{story}'")
    return d


def read_story(mod_id: str, story: str) -> dict:
    return json.loads((story_dir(mod_id, story) / "story.json").read_text(encoding="utf-8"))


def _write(d: Path, data: dict) -> None:
    d.mkdir(parents=True, exist_ok=True)
    atomic_write((d / "story.json"), json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def list_stories(mod_id: str) -> dict:
    read_mod(mod_id)
    out = []
    if _root(mod_id).is_dir():
        for f in sorted(_root(mod_id).glob("*/story.json")):
            s = json.loads(f.read_text(encoding="utf-8"))
            chapters = [c for a in s.get("acts", []) for c in a.get("chapters", [])]
            out.append({"slug": s.get("slug", f.parent.name), "name": s.get("name", f.parent.name), "description": s.get("description", ""),
                        "acts": len(s.get("acts", [])), "chapters": len(chapters), "events": sum(len(c.get("events", [])) for c in chapters),
                        "battles": sum(1 for c in chapters for e in c.get("events", []) if e.get("battle") or e.get("battles"))})
    return {"mod": mod_id, "stories": out}


def new_story(mod_id: str, name: str, description: str = "", template: str = "DBH") -> dict:
    """A new story with one act, one chapter, a dialogue event and a battle, ready to edit."""
    read_mod(mod_id)
    if template not in TEMPLATES:
        raise ValueError(f"template must be one of {', '.join(TEMPLATES)}")
    slug = slugify(name)
    d = _root(mod_id) / slug
    if (d / "story.json").exists():
        raise ValueError(f"{mod_id} already has a story '{slug}'")
    data = {"format": 1, "slug": slug, "name": name, "description": description, "template": template, "acts": [
        {"slug": "act1", "name": "Act 1", "chapters": [
            {"slug": "chapter1", "name": "Chapter 1", "intro": [{"speaker": "Narrator", "text": "Our story begins."}], "events": [
                {"slug": "meeting", "name": "A Meeting", "x": 0.35, "y": 0.45,
                 "intro": [{"speaker": "Stranger", "text": "Will you help me?", "choices": [{"text": "Yes"}, {"text": "For a price", "gold": 25}]}]},
                {"slug": "first-battle", "name": "First Battle", "x": 0.6, "y": 0.4, "requires": [{"event": "meeting"}],
                 "intro": [{"speaker": "Stranger", "text": "Here they come!"}],
                 "battle": {"player": {"deck": "own"}, "opponent": {"deck": "practice"}, "difficulty": "Novice", "opponent_name": "Bandit"},
                 "rewards": [{"gold": 50}]}]}]}]}
    _write(d, data)
    return {"mod": mod_id, "story": data, "dir": str(d)}


def save_story(mod_id: str, data: dict, game=None) -> dict:
    """Validate and write a whole story document (the app and agents edit the full tree)."""
    read_mod(mod_id)
    if not isinstance(data, dict) or not data.get("name"):
        raise ValueError("a story needs a name")
    data = dict(data)
    data["slug"] = slugify(data.get("slug") or data["name"])
    data.setdefault("format", 1)
    d = _root(mod_id) / data["slug"]
    errors = check_story(mod_id, data, d, game)
    if errors:
        raise ValueError("; ".join(errors[:20]) + (f" (and {len(errors) - 20} more)" if len(errors) > 20 else ""))
    _write(d, data)
    return {"mod": mod_id, "story": data["slug"], "summary": next(s for s in list_stories(mod_id)["stories"] if s["slug"] == data["slug"])}


def remove_story(mod_id: str, story: str) -> dict:
    d = story_dir(mod_id, story)
    trash(d, mod_id)
    return {"mod": mod_id, "removed": d.name}


def add_file(mod_id: str, story: str, file: str, name: str | None = None) -> dict:
    """Copy an image (PNG/JPG) or a voice line (WAV/OGG, or MP3/FLAC/M4A converted to OGG) into the story folder."""
    d = story_dir(mod_id, story)
    src = Path(file)
    if not src.is_file():
        raise ValueError(f"no file {file}")
    ext = src.suffix.lower()
    base = slugify(name or src.stem)
    if ext in IMAGE_TYPES:
        if ext == ".png":
            out = d / (base + ".png")
            shutil.copyfile(src, out)
        else:
            from PIL import Image
            out = d / (base + ".png")
            Image.open(src).convert("RGBA").save(out)
        return {"mod": mod_id, "story": d.name, "file": out.name, "kind": "image"}
    if ext in VOICE_TYPES:
        if ext in (".wav", ".ogg"):
            out = d / (base + ext)
            shutil.copyfile(src, out)
        else:
            out = d / (base + ".ogg")
            ffmpeg = _tool("ffmpeg")
            if not ffmpeg:
                raise ValueError("converting MP3/FLAC/M4A needs ffmpeg (not found); add a WAV or OGG file instead")
            subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-c:a", "libvorbis", "-q:a", "6", str(out)], check=True)
        return {"mod": mod_id, "story": d.name, "file": out.name, "kind": "voice"}
    raise ValueError("images: PNG or JPG; voice: WAV, OGG, MP3, FLAC or M4A")


def files(mod_id: str, story: str) -> dict:
    d = story_dir(mod_id, story)
    return {"images": sorted(p.name for p in d.iterdir() if p.suffix.lower() in (".png",)),
            "voices": sorted(p.name for p in d.iterdir() if p.suffix.lower() in (".wav", ".ogg"))}


def _events(data: dict):
    for a in data.get("acts", []):
        for c in a.get("chapters", []):
            for e in c.get("events", []):
                yield a, c, e


def _choices_of(event: dict, when: str) -> int:
    lines = event.get(when) or []
    return max([len(l.get("choices") or []) for l in lines] + [0])


def check_story(mod_id: str, data: dict, d: Path, game=None) -> list[str]:
    from . import modes
    errors: list[str] = []
    name = data.get("slug", "?")
    if data.get("template", "DBH") not in TEMPLATES:
        errors.append(f"{name}: template must be one of {', '.join(TEMPLATES)}")
    if data.get("skin", "template") not in SKINS:
        errors.append(f"{name}: skin must be one of {', '.join(SKINS)}")

    def img(v, where):
        if v and not str(v).startswith("asset:") and not (d / v).is_file():
            errors.append(f"{where}: image file '{v}' is not in the story folder")

    img(data.get("icon"), name); img(data.get("banner"), name)
    if not data.get("acts"):
        errors.append(f"{name}: a story needs at least one act")
    index: dict[str, dict] = {}
    for a in data.get("acts", []):
        a.setdefault("slug", slugify(a.get("name") or "act"))
        if not a.get("chapters"):
            errors.append(f"{name}/{a['slug']}: an act needs at least one chapter")
        img(a.get("icon"), f"{name}/{a['slug']}")
        for c in a.get("chapters", []):
            c.setdefault("slug", slugify(c.get("name") or "chapter"))
            img(c.get("map"), f"{a['slug']}/{c['slug']}")
            img(c.get("coin"), f"{a['slug']}/{c['slug']}")
            img(c.get("icon"), f"{a['slug']}/{c['slug']}")
            for e in c.get("events", []):
                e.setdefault("slug", slugify(e.get("name") or "event"))
                key = f"{a['slug']}/{c['slug']}/{e['slug']}"
                if key in index:
                    errors.append(f"{key}: two events share this slug")
                index[key] = e
    card_names = None

    def card_ok(n, where):
        nonlocal card_names
        if card_names is None:
            card_names = modes._card_names(game, mod_id) if game is not None else set()
        if card_names and n.lower() not in card_names:
            errors.append(f"{where}: no card named '{n}'")

    def resolve(req, a, c, where):
        parts = str(req.get("event", "")).split("/")
        full = "/".join(([a["slug"], c["slug"]] + parts)[-3:]) if len(parts) < 3 else "/".join(parts)
        if len(parts) == 2:
            full = f"{a['slug']}/{parts[0]}/{parts[1]}"
        target = index.get(full)
        if target is None:
            errors.append(f"{where}: requires unknown event '{req.get('event')}'")
            return
        ch = int(req.get("choice") or 0)
        when = req.get("when", "intro")
        if when not in ("intro", "ending"):
            errors.append(f"{where}: 'when' must be intro or ending")
        if ch and not 1 <= ch <= max(1, _choices_of(target, when)):
            errors.append(f"{where}: event '{req.get('event')}' has no {when} choice {ch}")

    def lines(ls, a, c, where):
        for i, l in enumerate(ls or []):
            w = f"{where} line {i + 1}"
            if not l.get("text"):
                errors.append(f"{w}: no text")
            img(l.get("portrait"), w)
            if l.get("voice") and not (d / l["voice"]).is_file():
                errors.append(f"{w}: voice file '{l['voice']}' is not in the story folder")
            if len(l.get("choices") or []) > 3:
                errors.append(f"{w}: at most 3 choices")
            for r in l.get("requires") or []:
                resolve(r, a, c, w)
            for o in l.get("choices") or []:
                if not o.get("text"):
                    errors.append(f"{w}: a choice has no text")
                if o.get("card"):
                    card_ok(o["card"], w)
                for r in o.get("requires") or []:
                    resolve(r, a, c, w)

    for a in data.get("acts", []):
        for c in a.get("chapters", []):
            lines(c.get("intro"), a, c, f"{a['slug']}/{c['slug']} intro")
            lines(c.get("ending"), a, c, f"{a['slug']}/{c['slug']} ending")
            for e in c.get("events", []):
                where = f"{a['slug']}/{c['slug']}/{e['slug']}"
                for k in ("x", "y"):
                    if e.get(k) is not None and not 0 <= float(e[k]) <= 1:
                        errors.append(f"{where}: {k} must be between 0 and 1 (fraction of the map picture)")
                img(e.get("coin"), where)
                for r in e.get("requires") or []:
                    resolve(r, a, c, where)
                lines(e.get("intro"), a, c, where + " intro")
                lines(e.get("ending"), a, c, where + " ending")
                battles = ([e["battle"]] if e.get("battle") else []) + list(e.get("battles") or [])
                if not battles and not e.get("intro"):
                    errors.append(f"{where}: an event needs intro dialogue or a battle")
                for b in battles:
                    entry = dict(b, slug=e["slug"])
                    errors += [x.replace(f"mode {e['slug']}", where) for x in modes.check_entry(game, mod_id, entry)]
                    if b.get("master") is not None:
                        if not isinstance(b["master"], dict):
                            errors.append(f"{where}: master must be an object of battle settings for Master difficulty")
                        else:
                            merged = {k: v for k, v in b.items() if k != "master"}
                            for k, v in b["master"].items():
                                merged[k] = {**merged.get(k, {}), **v} if isinstance(v, dict) and isinstance(merged.get(k), dict) else v
                            errors += [x.replace(f"mode {e['slug']}", where + " (master)") for x in modes.check_entry(game, mod_id, dict(merged, slug=e["slug"]))]
                    for l in b.get("lanes") or []:
                        if l.get("type") not in modes.LANES:
                            errors.append(f"{where}: lane type {l.get('type')} is not playable offline")
                        if int(l.get("size", 4)) not in (2, 4, 6):
                            errors.append(f"{where}: lane size must be 2, 4 or 6")
                    if len(b.get("lanes") or []) > 2:
                        errors.append(f"{where}: at most 2 lanes")
                    p = b.get("opponent_portrait")
                    if p and not str(p).startswith(("asset:", "ai:")):
                        img(p, where)
                    for r in b.get("requires") or []:
                        resolve(r, a, c, where)
                    for v in b.get("victory_lines") or []:
                        img(v.get("portrait"), where)
                if len(battles) > 1 and any(not b.get("requires") for b in battles[:-1]):
                    errors.append(f"{where}: with several battles, each but the last needs 'requires' (the intro choice that picks it)")
                if e.get("master_rewards") is not None and not isinstance(e.get("master_rewards"), list):
                    errors.append(f"{where}: master_rewards must be a list like rewards")
                for r in (e.get("rewards") or []) + (e.get("master_rewards") or []):
                    if not any(k in r for k in REWARDS):
                        errors.append(f"{where}: reward must be one of {', '.join(REWARDS)}")
                    if r.get("card"):
                        card_ok(r["card"], where)
                    if r.get("pack") and str(r["pack"]).lower().replace("cardpack_", "") not in PACKS:
                        errors.append(f"{where}: pack must be one of {', '.join(PACKS)}")
    return errors


def check(mod_id: str) -> list[str]:
    from . import api
    try:
        game = api._game()
    except Exception:
        game = None
    errors = []
    if _root(mod_id).is_dir():
        for f in sorted(_root(mod_id).glob("*/story.json")):
            try:
                errors += check_story(mod_id, json.loads(f.read_text(encoding="utf-8")), f.parent, game)
            except json.JSONDecodeError as e:
                errors.append(f"{f.parent.name}: story.json is not valid JSON ({e})")
    return errors


def options(game=None, mod_id: str | None = None) -> dict:
    """What a story can use: templates, skins, installed story maps / discs / portraits, reward kinds, battle options."""
    from . import modes
    maps, discs, portraits, story_art = [], [], [], []
    # the game's own campaign pictures, named from the game's data (asset-labels: Campaign/Act/Chapter DisplayIcon/Banner)
    art_names: dict[str, str] = {}
    try:
        from . import catalog
        what = {("Campaign", "DisplayIcon"): "story tile", ("Campaign", "DisplayBanner"): "story banner",
                ("Act", "DisplayIcon"): "act picture", ("Chapter", "DisplayIcon"): "chapter picture"}
        for line in catalog.DATA.read_text(encoding="utf-8").splitlines()[1:]:
            parts = line.split("\t")
            if len(parts) >= 4 and (parts[1], parts[2]) in what:
                label = parts[3].split("<br>")[0].strip() or parts[0].rsplit("/", 1)[-1]
                kind = what[(parts[1], parts[2])]
                prev = art_names.get(parts[0])
                art_names[parts[0]] = f"{label} ({kind})" if not prev else prev if label in prev else f"{prev}; {label} ({kind})"
    except Exception:
        pass
    try:
        from . import catalog
        for e in catalog.build(game):
            p = e.get("path", "")
            if not p.startswith("Assets/") or "_Mask" in p:
                continue
            asset = "asset:" + p[len("Assets/"):].rsplit(".", 1)[0]
            row = {"asset": asset, "label": e.get("label") or p.rsplit("/", 1)[-1], "preview": p}
            key = p[len("Assets/"):].rsplit(".", 1)[0]
            if key in art_names:
                story_art.append({**row, "label": art_names[key]})
            if "/CampaignMaps/" in p:
                maps.append(row)
            elif "/CampaignCoins/" in p:
                discs.append(row)
            elif "/AIPortraits/" in p:
                portraits.append(row)
    except Exception:
        pass
    story_art.sort(key=lambda r: r["label"].lower())
    return {"templates": TEMPLATES, "skins": SKINS, "rewards": REWARDS, "packs": PACKS, "maps": maps, "discs": discs, "portraits": portraits,
            "story_art": story_art,
            "lanes": modes.lanes(), "decks": modes.decks(game, mod_id) if mod_id else [], "difficulties": modes.DIFFICULTIES, "rules": modes.RULES, "zones": modes.ZONES}
