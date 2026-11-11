"""Safe file operations shared by every module, and the per-mod undo history.

atomic_write: writes a temporary file next to the target, then replaces it in one step, so a crash or power loss never
leaves a half-written mod.json, story.json or manifest (which would stop the whole mod from loading).
trash: deletes by moving into workspace/trash/<time>-<name>, so removed stories, images, sounds and boards can be restored.
History: inside `operation(label)` (every change from the app, the CLI or an MCP tool) each atomic_write remembers the file's
earlier text and each trash remembers where the file went. The operation is saved per mod in workspace/history/<mod>/;
undo(mod) puts the files back as they were (and saves what it replaced as a redo step), redo(mod) re-applies it.
Binary files copied in place (art, audio) are not versioned; deletes of them are (through the trash).
"""
from __future__ import annotations

import contextlib
import datetime
import json
import os
import shutil
import threading
from pathlib import Path

_local = threading.local()
MAX_STEPS = 200          # history kept per mod
MAX_TEXT = 8 << 20       # larger text files are not versioned


def _suite() -> Path:
    from .game import SUITE_ROOT
    return SUITE_ROOT


def _history_root() -> Path:
    from .game import workspace
    return workspace() / "history"


def _mod_of(path: Path) -> str:
    try:
        rel = path.resolve().relative_to((_suite() / "mods").resolve())
        return rel.parts[0]
    except ValueError:
        return "_suite"


@contextlib.contextmanager
def operation(label: str):
    """Group the file changes of one user action into one undo step (nested calls join the outer one)."""
    if getattr(_local, "op", None) is not None:
        yield _local.op
        return
    _local.op = {"label": label, "time": datetime.datetime.now().isoformat(timespec="seconds"), "files": []}
    try:
        yield _local.op
    finally:
        op, _local.op = _local.op, None
        if op["files"]:
            _save(op, "undo")
            for mod in {f["mod"] for f in op["files"]}:   # a new change clears that mod's redo steps
                shutil.rmtree(_history_root() / mod / "redo", ignore_errors=True)


def _record(entry: dict) -> None:
    op = getattr(_local, "op", None)
    if op is None or getattr(_local, "replaying", False):
        return
    if entry["kind"] == "text" and any(f["kind"] == "text" and f["path"] == entry["path"] for f in op["files"]):
        return   # the first state of a file within one operation is the one to restore
    op["files"].append(entry)


def _save(op: dict, stack: str) -> None:
    by_mod: dict[str, list] = {}
    for f in op["files"]:
        by_mod.setdefault(f["mod"], []).append(f)
    for mod, files in by_mod.items():
        d = _history_root() / mod / stack
        d.mkdir(parents=True, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        _plain_write(d / f"{stamp}.json", json.dumps({"label": op["label"], "time": op["time"], "files": files}, ensure_ascii=False))
        steps = sorted(d.glob("*.json"))
        for old in steps[:-MAX_STEPS]:
            old.unlink(missing_ok=True)


def _plain_write(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding=encoding, newline="") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def atomic_write(path, text: str, encoding: str = "utf-8") -> None:
    path = Path(path)
    if getattr(_local, "op", None) is not None:
        before = None
        if path.is_file() and path.stat().st_size <= MAX_TEXT:
            try:
                with open(path, encoding=encoding, newline="") as fh:   # exactly as on disk (keeps Windows line endings)
                    before = fh.read()
            except (UnicodeDecodeError, OSError):
                before = None
        if not path.is_file() or before is not None:
            _record({"kind": "text", "mod": _mod_of(path), "path": str(path.resolve()), "before": before})
    _plain_write(path, text, encoding)


def trash(path, label: str = "") -> Path | None:
    from .game import workspace
    path = Path(path)
    if not path.exists():
        return None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    target = workspace() / "trash" / f"{stamp}-{label + '-' if label else ''}{path.name}"
    target.parent.mkdir(parents=True, exist_ok=True)
    original = str(path.resolve())
    shutil.move(str(path), str(target))
    _record({"kind": "trash", "mod": _mod_of(Path(original)), "path": original, "trashed": str(target)})
    return target


# ---- undo / redo -----------------------------------------------------------------------------------------------------
def history(mod: str, limit: int = 30) -> dict:
    out = {}
    for stack in ("undo", "redo"):
        d = _history_root() / mod / stack
        steps = sorted(d.glob("*.json"), reverse=True) if d.is_dir() else []
        out[stack] = []
        for p in steps[:limit]:
            try:
                s = json.loads(p.read_text(encoding="utf-8"))
                out[stack].append({"id": p.stem, "label": s["label"], "time": s["time"], "files": len(s["files"])})
            except (OSError, json.JSONDecodeError):
                continue
    return {"mod": mod, **out}


def _apply(step: dict) -> list[dict]:
    """Puts each file back as the step remembers it; returns entries describing what it replaced (the opposite step)."""
    inverse = []
    _local.replaying = True
    try:
        for f in reversed(step["files"]):
            path = Path(f["path"])
            if f["kind"] == "text":
                now = None
                if path.is_file():
                    with open(path, encoding="utf-8", newline="") as fh:
                        now = fh.read()
                inverse.append({"kind": "text", "mod": f["mod"], "path": f["path"], "before": now})
                if f["before"] is None:
                    if path.is_file():
                        path.unlink()
                else:
                    _plain_write(path, f["before"])
            elif f["kind"] == "trash":
                trashed = Path(f["trashed"])
                if trashed.exists():
                    if path.exists():   # something new took its place: keep it in the trash too
                        target = trashed.with_name(trashed.name + "-replaced-" + datetime.datetime.now().strftime("%H%M%S%f"))
                        shutil.move(str(path), str(target))
                    path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(trashed), str(path))
                    inverse.append({"kind": "untrash", "mod": f["mod"], "path": f["path"], "trashed": f["trashed"]})
            elif f["kind"] == "untrash":   # redo of a restored delete: delete it again
                if path.exists():
                    Path(f["trashed"]).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(path), f["trashed"])
                    inverse.append({"kind": "trash", "mod": f["mod"], "path": f["path"], "trashed": f["trashed"]})
    finally:
        _local.replaying = False
    return list(reversed(inverse))


def _step(mod: str, frm: str, to: str) -> dict:
    d = _history_root() / mod / frm
    steps = sorted(d.glob("*.json")) if d.is_dir() else []
    if not steps:
        raise ValueError(f"nothing to {'undo' if frm == 'undo' else 'redo'} for {mod}")
    p = steps[-1]
    step = json.loads(p.read_text(encoding="utf-8"))
    inverse = _apply(step)
    p.unlink()
    if inverse:
        _save({"label": step["label"], "time": step["time"], "files": inverse}, to)
    return {"mod": mod, ("undone" if frm == "undo" else "redone"): step["label"], "files": len(step["files"])}


def undo(mod: str) -> dict:
    return _step(mod, "undo", "redo")


def redo(mod: str) -> dict:
    return _step(mod, "redo", "undo")
