"""Game previews: cards, card backs, deck banners and boards drawn by the game itself (TESL: Everlasting's render mode),
exactly as players will see them.

render() starts the game hidden with --tesl-render-cards=<folder> and --tesl-mods-list=<folder>/list.json (the enabled mods
plus this one, so cards that need other mods work), waits for it to finish (about half a minute plus a few seconds per card)
and keeps the pictures in workspace/renders/<mod>/cards/<card slug>.png, and the others in .../cards/backs|decks|boards/<slug>.png
(card backs need engine level 56). The game must not be running; the player's profile, saves and enabled-mod list are not used or
changed.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path

from .game import GameInstall, workspace
from .mods import _active, mod_cards, mod_dir, read_mod

EXE = "The Elder Scrolls Legends.exe"
KINDS = ("backs", "decks", "boards")
_UNSAFE = '<>:"/\\|?*'


def _file_safe(key: str) -> str:
    """The engine's file name for a key (Path.GetInvalidFileNameChars -> '_')."""
    return "".join("_" if (ch in _UNSAFE or ord(ch) < 32) else ch for ch in key)


def extras(mod_id: str) -> list[tuple[str, str, str, str]]:
    """[(cards.txt line, kind, slug, engine file name)] for the mod's card backs, decks and boards."""
    from . import boards, cardbacks
    root = mod_dir(mod_id)
    out = []
    for c in cardbacks.list_cardbacks(mod_id)["cardbacks"]:
        key = f"mod.{mod_id}.cardback.{c['slug']}"
        out.append((f"back:{key}", "backs", c["slug"], f"back_{_file_safe(key)}.png"))
    for p in sorted((root / "decks").glob("*.json")):
        try:
            name = json.loads(p.read_text(encoding="utf-8")).get("type_name")
        except (OSError, ValueError):
            name = None
        if name:
            out.append((f"deck:{name}", "decks", p.stem, f"deck_{_file_safe(name)}.png"))
    for b in boards.list_boards(mod_id)["boards"]:
        key = f"{mod_id}/{b['slug']}"
        out.append((f"board:{key}", "boards", b["slug"], f"board_{_file_safe(key)}.png"))
    return out


def preview_url(mod_id: str, kind: str, slug: str) -> str | None:
    """URL of a card back / deck / board game preview, or None."""
    p = folder(mod_id) / kind / f"{slug}.png"
    return f"/api/mods/{mod_id}/previews/{kind}/{slug}.png?t={int(p.stat().st_mtime)}" if p.is_file() else None
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def folder(mod_id: str) -> Path:
    return workspace() / "renders" / mod_id / "cards"


def existing(mod_id: str) -> dict:
    """{card unique name: file name} for previews already made."""
    f = folder(mod_id)
    return {p.stem: p.name for p in sorted(f.glob("*.png"))} if f.is_dir() else {}


def status(mod_id: str) -> dict:
    with _lock:
        job = dict(_jobs.get(mod_id) or {"state": "idle"})
    job["previews"] = existing(mod_id)
    return job


def _run(game: GameInstall, mod_id: str, ids: dict[int, str], more: list | None = None) -> None:
    from . import playtest
    job = _jobs[mod_id]
    work = workspace() / "renders" / mod_id / "job"
    try:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True)
        mods_list = list(_active())
        mine = str(mod_dir(mod_id).resolve())
        if mine not in mods_list:
            mods_list.append(mine)
        (work / "list.json").write_text(json.dumps({"format": 1, "mods": mods_list}), encoding="utf-8")
        more = more or []
        (work / "cards.txt").write_text("\n".join([str(i) for i in ids] + [e[0] for e in more]), encoding="utf-8")
        total = len(ids) + len(more)
        exe = Path(game.root) / EXE
        args = [str(exe), "--tesl-offline-native", f"--tesl-render-cards={work}", f"--tesl-mods-list={work / 'list.json'}",
                "-batchmode", "-screen-width", "1280", "-screen-height", "720", "-logFile", str(work / "unity.log")]
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        proc = subprocess.Popen(args, cwd=game.root, creationflags=flags)
        limit = 150 + 8 * total
        start = time.time()
        while proc.poll() is None and time.time() - start < limit:
            done = len(list(work.glob("*.png")))
            job["message"] = f"The game is drawing: {done} of {total}" if done else "Starting the game in the background..."
            time.sleep(1)
        if proc.poll() is None:
            proc.kill()
            raise RuntimeError("the game took too long; try fewer cards or check that TESL: Everlasting is installed")
        result = (work / "done.txt").read_text(encoding="utf-8") if (work / "done.txt").is_file() else ""
        if not result:
            raise RuntimeError("the game closed without drawing (is TESL: Everlasting level 55 or newer installed?)")
        out = folder(mod_id)
        out.mkdir(parents=True, exist_ok=True)
        made = 0
        for cid, slug in ids.items():
            src = work / f"{cid}.png"
            if src.is_file():
                shutil.copyfile(src, out / f"{slug}.png"); made += 1
        labels = {}
        for line, kind, slug, name in more:
            labels[line] = f"{kind[:-1]} {slug}"
            src = work / name
            if src.is_file():
                (out / kind).mkdir(exist_ok=True)
                shutil.copyfile(src, out / kind / f"{slug}.png"); made += 1
        problems = []
        if (work / "render-log.tsv").is_file():
            for line in (work / "render-log.tsv").read_text(encoding="utf-8").splitlines():
                parts = line.split("\t")
                if len(parts) > 1 and parts[1] != "ok" and parts[0] not in ("boards", "camera", "plane"):
                    who = labels.get(parts[0]) or ids.get(int(parts[0]) if parts[0].lstrip('-').isdigit() else 0, parts[0])
                    problems.append(f"{who}: {parts[1]}")
        job.update(state="done", message=f"{made} of {total} drawn by the game", problems=problems, finished=time.time())
    except Exception as e:
        job.update(state="failed", message=str(e), finished=time.time())
    finally:
        for leftover in ("render-player-state.json", "render-player-state.json.bak"):
            (work / leftover).unlink(missing_ok=True)


def render(game: GameInstall, mod_id: str, cards: list[str] | None = None, wait: bool = False, kinds: list[str] | None = None) -> dict:
    """Start drawing the mod's cards (all, or the given unique names) and, unless only some cards were asked for, its card
    backs, deck banners and boards (or just the given kinds: "cards", "backs", "decks", "boards"). Returns at once unless wait=True."""
    from . import playtest
    read_mod(mod_id)
    if playtest.running():
        raise ValueError("the game is running: close it first (previews start it hidden in the background)")
    wanted = set(kinds) if kinds else ({"cards"} if cards else {"cards", *KINDS})
    ids = {c["ResourceId"]["Id"]: c["ResourceId"]["UniqueName"] for c in mod_cards(mod_id)
           if not cards or c["ResourceId"]["UniqueName"] in cards or c.get("Name") in cards} if "cards" in wanted else {}
    more = [e for e in extras(mod_id) if e[1] in wanted]
    if not ids and not more:
        raise ValueError("this mod has nothing the game can preview (cards, card backs, decks or boards)")
    with _lock:
        if (_jobs.get(mod_id) or {}).get("state") == "running":
            return status(mod_id)
        _jobs[mod_id] = {"state": "running", "message": "Starting the game in the background...", "cards": len(ids) + len(more), "started": time.time()}
    t = threading.Thread(target=_run, args=(game, mod_id, ids, more), daemon=True)
    t.start()
    if wait:
        t.join()
    return status(mod_id)
