"""The game's assets with plain labels: what each one is, what it belongs to, and how a mod can change it.

Sources, best first:
  - the game configuration (data/asset-labels.tsv, exported by the offline engine's audit): avatars, AI opponents,
    quest banners and givers, story locations, deck art, card backs, lanes, cinematics, card effects;
  - the card data: every file in a card's art folder belongs to that card;
  - the sounds catalog (tesl_suite.sounds) for audio;
  - readable rules from the folder and file name (boards, packs, interface, effects...).

Each entry: path (as in the asset index), kind, category, category_label, label, owner (the card/avatar/board...),
part (art, premium mask, normal map...), change (how a mod can change it: "remaster", "sounds", "cardback", "board", or
"" when not yet).
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import csv
import json
import re
from pathlib import Path

from .game import GameInstall

CATEGORIES = [
    ("card-art", "Card art"), ("card-effect", "Card effects"), ("avatar", "Avatars"), ("ai-portrait", "AI opponents"),
    ("deck-art", "Deck art"), ("card-back", "Card backs"), ("story", "Story & campaigns"), ("quest", "Quests"),
    ("board", "Boards"), ("lane", "Lanes"), ("pack", "Card packs"), ("interface", "Interface"), ("music", "Music"),
    ("sound", "Sounds"), ("sound-loader", "Sound loaders (internal)"), ("font", "Fonts"), ("shader", "Shaders"),
    ("text", "Text"), ("other", "Other"),
]
_CAT = dict(CATEGORIES)
BOARD_OF = {"AppBase": "Original", "ContentPack001": "Isle of Madness", "ContentPack003": "Alliance War",
            "ContentPack007": "Elsweyr", "ContentPack010": "Realms of Oblivion"}
MAP_PARTS = [("_mask", "mask"), ("_n", "normal map"), ("_ny", "normal map"), ("_s", "specular map"), ("_e", "glow map"),
             ("_d", "colour"), ("_diffuse", "colour"), ("_anim", "animation material"), ("_premium", "premium version")]
_CACHE: list[dict] | None = None
DATA = Path(__file__).parent / "data" / "asset-labels.tsv"
TYPE_PART = {"LaneDisplayData": "lane icon", "CardBackData": "card back"}
TYPE_CATEGORY = {"AvatarData": "avatar", "AiOpponent": "ai-portrait", "DeckArtData": "deck-art", "CardBackData": "card-back",
                 "QuestUi": "quest", "StoryDialogueModal": "story", "ChapterEvent": "story", "Chapter": "story", "Campaign": "story",
                 "Act": "story", "CinematicData": "story", "MatchDialogueData": "story", "LaneDisplayData": "lane",
                 "CardFxDefinition": "card-effect", "MenuBackgroundData": "interface"}


def _workspace() -> Path:
    from .game import SUITE_ROOT
    return Path(SUITE_ROOT) / "workspace"


def _norm(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("Assets/"):
        p = p[7:]
    return re.sub(r"\.[A-Za-z0-9]{2,8}$", "", p).lower()


def _human(name: str) -> str:
    name = re.sub(r"(?i)(^|_)(crdl|tesl)_\d\d_[a-z]?\d+(_|$)", r"\1", name)
    name = re.sub(r"(?i)_(png|tga|psd)$", "", name)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    words = [w for w in re.split(r"[_\-\s]+", name) if w and not re.fullmatch(r"\d{1,2}", w)]
    text = " ".join(words).strip()
    return text[:1].upper() + text[1:] if text else name


def _part(stem: str) -> tuple[str, str]:
    """(base name, part) from a file stem, e.g. 'ELS_MoonSugarBowl_01_N' -> ('ELS_MoonSugarBowl', 'normal map')."""
    low = stem.lower()
    for suffix, part in MAP_PARTS:
        if low.endswith(suffix):
            return re.sub(r"_\d{1,2}$", "", stem[: -len(suffix)]), part
    return re.sub(r"_\d{1,2}$", "", stem), ""


def _labels() -> dict[str, tuple[str, str, str]]:
    """normalised path -> (type, field, label) from the engine's export."""
    out = {}
    if DATA.is_file():
        with DATA.open(encoding="utf-8") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                key = _norm(r["path"])
                for k in (key, "stem:" + key.rsplit("/", 1)[-1]):
                    if k not in out or (r["label"] and not out[k][2]):
                        out[k] = (r["type"], r["field"], r["label"])
    return out


FIELD_PART = {"Image": "portrait", "CircularImage": "round portrait", "LargeImagePath": "large art", "CroppedImagePath": "tile art",
              "BannerImage": "banner", "GiverPortraitImage": "quest giver", "CoinImage": "location disc", "VisualAsset": "card back",
              "MainParticleSystem": "effect", "OpponentParticleSystem": "effect (opponent side)"}


def _avatar_name(unique: str) -> str:
    m = re.match(r"Avatar([A-Za-z]+?)(\d*)$", unique)
    if not m:
        return _human(unique)
    race = re.sub(r"([a-z])([A-Z])", r"\1 \2", m.group(1))
    return f"{race} avatar {m.group(2)}".strip()


def build(game: GameInstall, refresh: bool = False) -> list[dict]:
    global _CACHE
    cache = _workspace() / "asset-catalog.json"
    if _CACHE is not None and not refresh:
        return _CACHE
    if cache.is_file() and not refresh and cache.stat().st_mtime >= DATA.stat().st_mtime:
        _CACHE = json.loads(cache.read_text(encoding="utf-8"))
        return _CACHE
    from . import assets, sounds
    from .cards import load_sets
    card_dirs: dict[str, list[str]] = {}
    for s in load_sets(game):
        for c in s.get("Cards") or []:
            if c and c.get("Image") and "/Cards/Visuals/" in c["Image"]:
                folder = _norm(c["Image"]).rsplit("/", 1)[0]
                names = card_dirs.setdefault(folder, [])
                if c.get("Name") and c["Name"] not in names:
                    names.append(c["Name"])
    sound_by_clip = {}
    for snd in sounds.catalog(game):
        for clip in snd["clips"]:
            sound_by_clip.setdefault(clip.lower(), snd)
    labels = _labels()
    out = []
    for e in assets.load_index(game)["entries"]:
        out.append(_entry(e, labels, card_dirs, sound_by_clip))
    order = {k: i for i, (k, _) in enumerate(CATEGORIES)}
    out.sort(key=lambda r: (order[r["category"]], r["label"].lower()))
    cache.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(cache, json.dumps(out, ensure_ascii=False), encoding="utf-8")
    _CACHE = out
    return out


def _entry(e: dict, labels: dict, card_dirs: dict, sound_by_clip: dict) -> dict:
    path, kind = e["path"], e["kind"]
    key = _norm(path)
    parts = path.split("/")
    pack = parts[1] if len(parts) > 1 else ""
    stem = Path(path).stem
    low = path.lower()
    cat, owner, part, change = "other", "", "", ""
    hit = labels.get(key) or labels.get("stem:" + stem.lower())
    if hit and not hit[2].strip():
        hit = None                                   # named nowhere in the configuration: fall back to the rules
    # 1. a card's art folder
    folder = next((key[: i] for i in [len(key)] + [m.start() for m in re.finditer("/", key)][::-1] if key[:i] in card_dirs), None)
    if "/audio/music/" in low:
        cat, owner, part, change = "music", _human(re.sub(r"(?i)^bgm_(plymt_)?", "", stem)), "music playlist", "music"
    elif "/cards/visuals/" in low and folder:
        cat, owner = "card-art", " / ".join(card_dirs[folder][:3])
        base, part = _part(stem)
        if "/premium/" in low and not part.startswith("premium"):
            part = "premium " + (part or "animation")
        part = part or ("art" if kind == "texture" else kind)
        change = "remaster" if kind == "texture" and "/premium/" not in low else ""
    # 2. named by the game configuration
    elif hit:
        typ, field, lab = hit
        cat = TYPE_CATEGORY.get(typ, "other")
        lab = re.sub(r"<[^>]+>", "", re.sub(r"(?i)<br>.*$", "", lab)).strip()
        owner = _avatar_name(lab) if typ == "AvatarData" or re.match(r"Avatar[A-Z]", lab) else (lab.title() if lab.isupper() else lab)
        if "_" in owner:
            owner = _human(re.sub(r"(?i)^card_", "", owner))
        part = TYPE_PART.get(typ) or FIELD_PART.get(field, _human(field).lower())
        if cat in ("avatar", "ai-portrait", "deck-art", "quest", "story", "lane") and kind == "texture" and "/images/" in low:
            change = "remaster"
    elif kind == "audio":
        snd = sound_by_clip.get(stem.lower())
        cat, change = "sound", "sounds"
        owner = snd["label"] if snd else _human(stem)
        part = snd["category_label"] if snd else ""
    elif "/audio/music/" in low:
        cat, owner, part, change = "music", _human(re.sub(r"(?i)^bgm_(plymt_)?", "", stem)), "music playlist", "music"
    elif kind == "prefab" and "/audio/" in low and ("audio loader" in low or "/prefabs/" in low):
        cat, owner, part = "sound-loader", _human(re.sub(r"(?i)\s*audio loader.*$", "", stem)), "sound loader"
    elif "/cardbacks/" in low:
        m = re.search(r"CB_([A-Za-z0-9]+)", path)
        cat, owner = "card-back", _human(m.group(1)) if m else _human(stem)
        part = ("premium " if "/premium/" in low else "") + (_part(stem)[1] or kind)
        change = "cardback"
    elif "gameboard" in low or "/cdgameboard/" in low or "/fx/board/" in low:
        cat = "board"
        board = BOARD_OF.get(pack, "Original" if pack in ("AppBase", "Common000") else pack)
        base, part = _part(stem)
        obj = _human(re.sub(r"(?i)^(iom|aw|els|oc|playmat)_", "", base)) or "board"
        owner = f"{board} board - {obj}"
        part = part or kind
        change = "board" if kind == "texture" else ""
    elif "/cards/animations/" in low or "statuseffects" in low:
        cat, owner, part = "card-effect", _human(re.sub(r"^\[\w+\]", "", stem)), "card animation"
    elif "/fx/" in low or "/textures/fx/" in low or "/materials/fx/" in low or "/animation/card_" in low or "premiumcards" in low:
        cat = "card-effect"
        owner = _human(re.sub(r"(?i)^fx_(card_|mesh_)?", "", stem))
        part = "premium card texture" if "premiumcards" in low else kind
    elif "/images/avatars/" in low:
        cat, owner, part, change = "avatar", _human(stem), kind, "remaster" if kind == "texture" else ""
    elif "/images/aiportraits/" in low:
        cat, owner, part, change = "ai-portrait", _human(stem), "portrait", "remaster" if kind == "texture" else ""
    elif "/images/deckart" in low:
        cat, owner, part, change = "deck-art", _human(stem), "deck art", "remaster" if kind == "texture" else ""
    elif any(x in low for x in ("/images/campaign", "/images/chapter", "/images/cinematics", "/images/puzzles", "/images/questgiver")):
        cat, owner, part, change = "story", _human(stem), _human(parts[3]).lower() if len(parts) > 3 else "", "remaster" if kind == "texture" else ""
    elif "/images/questbanners" in low:
        cat, owner, part, change = "quest", _human(stem), "banner", "remaster" if kind == "texture" else ""
    elif "/images/laneicons" in low:
        cat, owner, part, change = "lane", _human(stem.replace("_lanerules", "")), "lane icon", "remaster" if kind == "texture" else ""
    elif "cardpack" in low:
        cat, owner, part = "pack", _human(_part(stem)[0]), _part(stem)[1] or kind
    elif "/ui/" in low or "/images/" in low or "/cards/textures/" in low:
        cat = "interface"
        sub = [p for p in parts[2:-1] if p.lower() not in ("ui", "sprites", "textures", "images", "core", "prefabs")]
        owner = _human(stem)
        part = " / ".join(_human(p) for p in sub[:2]) or kind
        change = "remaster" if kind == "texture" and ("/ui/sprites/" in low or "/images/" in low) else ""
    elif kind in ("font", "shader", "text"):
        cat, owner, part = kind, _human(stem), kind
    else:
        owner, part = _human(stem), kind
    label = owner + (f" - {part}" if part and part != owner else "")
    return {"path": path, "kind": kind, "bundle": e["bundle"], "category": cat, "category_label": _CAT[cat], "label": label,
            "owner": owner, "part": part, "change": change}


LANGUAGE_NAMES = {"en_US": "English", "de_DE": "German", "fr_FR": "French", "es_ES": "Spanish (Spain)", "es_MX": "Spanish (Mexico)",
                  "it_IT": "Italian", "pl_PL": "Polish", "pt_BR": "Portuguese (Brazil)", "ru_RU": "Russian", "ja_JP": "Japanese",
                  "zh_CN": "Chinese (Simplified)", "zh_TW": "Chinese (Traditional)", "ko_KR": "Korean", "tr_TR": "Turkish"}
_LANG = re.compile(r"[/\[]([a-z]{2}_[A-Z]{2})[/\]]")


def language_of(path: str) -> str:
    """The language folder or tag of an asset ("en_US", "de_DE", ...), or "" for language-neutral assets."""
    m = _LANG.search(path)
    return m.group(1) if m else ""


def search(game: GameInstall, q: str | None = None, category: str | None = None, kind: str | None = None, changeable: bool = False,
           limit: int = 100, offset: int = 0, include_internal: bool = False, language: str | None = None) -> dict:
    rows = build(game)
    if category:
        rows = [r for r in rows if r["category"] == category]
    elif not include_internal:
        # browsing everything leaves out the ~38,000 sound clips (pick Sounds to see them); a search includes them
        hidden = ("sound-loader",) if q else ("sound-loader", "sound")
        rows = [r for r in rows if r["category"] not in hidden]
    if language:
        rows = [r for r in rows if language_of(r["path"]) == ("" if language == "none" else language)]
    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if changeable:
        rows = [r for r in rows if r["change"]]
    if q:
        words = q.lower().split()
        rows = [r for r in rows if all(w in (r["label"] + " " + r["path"]).lower() for w in words)]
    counts: dict[str, int] = {}
    for r in build(game):
        counts[r["category"]] = counts.get(r["category"], 0) + 1
    langs = sorted({language_of(r["path"]) for r in build(game)} - {""})
    return {"total": len(rows), "assets": rows[offset: offset + limit],
            "categories": [{"id": k, "label": v, "count": counts.get(k, 0)} for k, v in CATEGORIES],
            "languages": [{"id": l, "label": f"{LANGUAGE_NAMES.get(l, l)} ({l})"} for l in langs]}
