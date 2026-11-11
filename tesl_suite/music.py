"""Custom soundtracks. A track plays in the moments and on the boards you pick ("contexts"):
  - game moments: MainMenuState, PlayState, StoryState, StoreState, DeckEditorState, PackOpenState, SoloArenaState,
    VersusArenaState, PlayerProfileState, AvatarPickerState, RewardsState, EndGameWin, EndGameLose, LevelUp,
    MatchStartIntro, MatchOngoing, MatchHalfHealth, MatchStartBoss, ...;
  - boards: Board:Original, Board:IsleOfMadness, Board:AllianceWar, Board:Elsweyr, Board:RealmsOfOblivion, or a mod
    board Board:<mod>/<board>.
mode "replace" plays your track(s) instead of the game's music there; "rotation" mixes the game's music in.
The game's music volume and mute apply. Audio is stored as OGG (converted with ffmpeg) or WAV.

Layout: mods/<id>/music/music.json + the audio files.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
import shutil
import subprocess
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

MOMENTS = ["InitializationState", "MainMenuState", "PlayState", "StoryState", "StoreState", "SoloArenaState", "VersusArenaState",
           "DeckEditorState", "PackOpenState", "PlayerProfileState", "AvatarPickerState", "RewardsState", "IntroOnboardingState",
           "EndGameWin", "EndGameLose", "LevelUp", "SeasonsRolloverState", "MatchStartIntro", "MatchOngoing", "MatchHalfHealth", "MatchStartBoss"]
BOARDS = ["Original", "IsleOfMadness", "AllianceWar", "Elsweyr", "RealmsOfOblivion"]
BOARD_LABELS = {"Original": "Original board", "IsleOfMadness": "Isle of Madness", "AllianceWar": "Alliance War", "Elsweyr": "Elsweyr",
                "RealmsOfOblivion": "Realms of Oblivion"}
LABELS = {"MainMenuState": "Main menu", "PlayState": "Play menu", "StoryState": "Story map", "StoreState": "Store", "DeckEditorState": "Collection & deck builder",
          "PackOpenState": "Opening packs", "SoloArenaState": "Solo arena", "VersusArenaState": "Versus arena", "PlayerProfileState": "Profile",
          "AvatarPickerState": "Avatar picker", "RewardsState": "Rewards", "EndGameWin": "Victory", "EndGameLose": "Defeat", "LevelUp": "Level up",
          "MatchStartIntro": "Match intro", "MatchOngoing": "Match (default)", "MatchHalfHealth": "Match (low health)", "MatchStartBoss": "Boss match",
          "InitializationState": "Start-up", "IntroOnboardingState": "First run", "SeasonsRolloverState": "Season change"}


def contexts(mod_id: str | None = None) -> list[dict]:
    out = [{"context": m, "label": LABELS.get(m, m), "group": "Moments"} for m in MOMENTS]
    out += [{"context": f"Board:{b}", "label": BOARD_LABELS[b], "group": "Boards"} for b in BOARDS]
    if mod_id:
        from . import boards
        for b in boards.list_boards(mod_id)["boards"]:
            out.append({"context": f"Board:{mod_id}/{b['slug']}", "label": b["name"], "group": "This mod's boards"})
        from . import modes
        for m in modes.list_modes(mod_id)["modes"]:
            out.append({"context": f"Mode:{mod_id}/{m['slug']}", "label": m["name"] + " (whole match)", "group": "This mod's game modes"})
    return out


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "music" / "music.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "tracks": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _to_ogg(src: Path, dest: Path) -> tuple[float, Path]:
    """OGG Vorbis for the game (OGG is kept as it is; WAV is kept only without ffmpeg). Returns the duration in seconds and the stored file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = shutil.which("ffmpeg")
    if src.suffix.lower() == ".ogg" or (src.suffix.lower() == ".wav" and not ffmpeg):
        dest = dest.with_suffix(src.suffix.lower())
        shutil.copyfile(src, dest)
    else:
        if not ffmpeg:
            raise ValueError(f"{src.name}: only OGG or WAV can be used without ffmpeg installed")
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-vn", "-c:a", "libvorbis", "-q:a", "6", str(dest)], check=True)
    seconds = 0.0
    if ffmpeg:
        probe = shutil.which("ffprobe")
        if probe:
            r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(dest)], capture_output=True, text=True)
            try:
                seconds = float(r.stdout.strip())
            except ValueError:
                pass
    return seconds, dest


def add_track(mod_id: str, name: str, file: str, contexts_: list[str], mode: str = "replace", volume: float = 1.0) -> dict:
    read_mod(mod_id)
    src = Path(file)
    if not src.is_file():
        raise ValueError(f"Audio not found: {file}")
    if mode not in ("replace", "rotation"):
        raise ValueError("mode must be replace or rotation")
    if not contexts_:
        raise ValueError("give at least one context (tesl music contexts)")
    known = {c["context"] for c in contexts(mod_id)}
    bad = [c for c in contexts_ if c not in known and not c.startswith(("Board:", "Mode:"))]
    if bad:
        raise ValueError(f"Unknown context(s) {bad}: see tesl music contexts")
    slug = slugify(name)
    seconds, dest = _to_ogg(src, mod_dir(mod_id) / "music" / f"{slug}.ogg")
    manifest = _read(mod_id)
    entry = {"slug": slug, "name": name, "file": dest.name, "contexts": list(dict.fromkeys(contexts_)), "mode": mode, "volume": float(volume)}
    manifest["tracks"] = [t for t in manifest["tracks"] if t["slug"] != slug] + [entry]
    _write(mod_id, manifest)
    return {"mod": mod_id, "track": {**entry, "seconds": round(seconds, 1)}, "total": len(manifest["tracks"])}


def list_tracks(mod_id: str) -> dict:
    read_mod(mod_id)
    return {"mod": mod_id, "tracks": _read(mod_id)["tracks"]}


def remove(mod_id: str, name: str) -> dict:
    manifest = _read(mod_id)
    slug = slugify(name)
    gone = [t for t in manifest["tracks"] if t["slug"] in (slug, name)]
    if not gone:
        raise ValueError(f"{mod_id} has no track '{name}'")
    manifest["tracks"] = [t for t in manifest["tracks"] if t not in gone]
    for t in gone:
        f = mod_dir(mod_id) / "music" / t["file"]
        if f.is_file():
            trash(f, mod_id)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(manifest["tracks"])}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for t in _read(mod_id)["tracks"]:
        if not (mod_dir(mod_id) / "music" / t.get("file", "")).is_file():
            errors.append(f"music {t['slug']}: missing audio file")
        if not t.get("contexts"):
            warnings.append(f"music {t['slug']}: no contexts, it never plays")
    return errors, warnings
