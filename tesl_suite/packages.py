"""Mod packages: export a mod as a shareable .zip, install mods from a .zip, a folder or an https link, uninstall.

A package is a zip with one folder <mod-id>/ (the mod, as in mods/<mod-id>/) and package.json at the root:
{"format": 1, "id", "name", "version", "requires_engine", "class", "fingerprint", "features"} - what a community index or a
server needs to know (the fingerprint is compat.fingerprint of the mod folder).
Installing only accepts content files (data, images, audio, 3D models, text); programs and scripts are refused, as are paths
that would leave the mod folder. An installed older version is moved to workspace/backups first; uninstalled mods go to
workspace/trash (recoverable). Installed mods are validated and checked for compatibility but not enabled unless asked.
"""
from __future__ import annotations

import datetime
import json
import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from . import compat
from .game import workspace
from .mods import ID_RE, MODS, mod_dir, read_mod, set_enabled

ALLOWED = {".json", ".png", ".jpg", ".jpeg", ".ogg", ".wav", ".mp3", ".flac", ".m4a", ".obj", ".mtl", ".glb", ".gltf", ".bin",
           ".txt", ".md", ".tsv", ".csv"}
MAX_FILES, MAX_BYTES = 20000, 4 * 1024 ** 3


def _stamp() -> str:
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def export_mod(mod_id: str, out: str | None = None) -> dict:
    meta = read_mod(mod_id)
    compat.stamp(mod_id)
    feats = compat.features(mod_id)
    info = {"format": 1, "id": mod_id, "name": meta.get("name", mod_id), "version": meta.get("version") or "1.0.0",
            "requires_engine": compat.required_engine(feats), "class": compat.multiplayer_class(feats),
            "fingerprint": compat.fingerprint(mod_id), "features": feats,
            "dependencies": compat.manifest(mod_id)["dependencies"], "conflicts": compat.manifest(mod_id)["conflicts"]}
    target = Path(out) if out else workspace() / "exports" / f"{mod_id}-{info['version']}.zip"
    target.parent.mkdir(parents=True, exist_ok=True)
    root = mod_dir(mod_id)
    from . import details
    info["description"] = meta.get("description", ""); info["author"] = meta.get("author", "")
    info["changelog"] = (meta.get("changelog") or [])[:20]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("package.json", json.dumps(info, indent=1, ensure_ascii=False))
        z.writestr("README.md", details.readme(mod_id, feats, info["class"], info["requires_engine"]))
        z.writestr("CHANGELOG.md", details.changelog_md(mod_id))
        if meta.get("preview") and (root / meta["preview"]).is_file():
            z.write(root / meta["preview"], "preview.png")
        for p in sorted(x for x in root.rglob("*") if x.is_file()):
            z.write(p, f"{mod_id}/{p.relative_to(root).as_posix()}")
    return {"mod": mod_id, "file": str(target), "bytes": target.stat().st_size, "package": info}


def _check_names(names: list[str]) -> list[str]:
    bad = []
    for n in names:
        p = PurePosixPath(n.replace("\\", "/"))
        if n.endswith("/"):
            continue
        if p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
            bad.append(f"{n}: path leaves the mod folder")
        elif p.suffix.lower() not in ALLOWED:
            bad.append(f"{n}: file type {p.suffix or '(none)'} is not allowed in mods")
    return bad


def _mod_root(folder: Path) -> Path:
    """The folder holding mod.json (the folder itself or its only mod subfolder)."""
    if (folder / "mod.json").is_file():
        return folder
    found = [p.parent for p in folder.glob("*/mod.json")]
    if len(found) != 1:
        raise ValueError("the package must contain exactly one mod (a folder with mod.json)")
    return found[0]


def install(source: str, enable: bool = False, force: bool = False) -> dict:
    """Install a mod from a .zip, a folder or an https:// link to a .zip."""
    work = Path(tempfile.mkdtemp(prefix="tesl-install-"))
    try:
        src = source
        if source.lower().startswith("https://"):
            dest = work / "download.zip"
            with urllib.request.urlopen(source, timeout=60) as r, open(dest, "wb") as f:
                shutil.copyfileobj(r, f, length=1 << 20)
            src = str(dest)
        elif source.lower().startswith("http://"):
            raise ValueError("only https links are accepted")
        path = Path(src)
        if path.is_dir():
            names = [p.relative_to(path).as_posix() for p in path.rglob("*") if p.is_file()]
            bad = _check_names(names)
            if bad:
                raise ValueError("refused: " + "; ".join(bad[:10]))
            unpacked = work / "mod"
            shutil.copytree(path, unpacked)
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if len(infos) > MAX_FILES or sum(i.file_size for i in infos) > MAX_BYTES:
                    raise ValueError("refused: the package is too large")
                bad = _check_names([i.filename for i in infos if i.filename != "package.json"])
                if bad:
                    raise ValueError("refused: " + "; ".join(bad[:10]))
                unpacked = work / "mod"
                z.extractall(unpacked)
                (unpacked / "package.json").unlink(missing_ok=True)
        else:
            raise ValueError(f"not a mod folder or .zip: {source}")
        root = _mod_root(unpacked)
        meta = json.loads((root / "mod.json").read_text(encoding="utf-8"))
        mod_id = meta.get("id") or ""
        if not ID_RE.match(mod_id):
            raise ValueError(f"mod.json has an invalid id: {mod_id!r}")
        version = meta.get("version") or "1.0.0"
        target = MODS / mod_id
        replaced = None
        if target.exists():
            old = read_mod(mod_id).get("version") or "1.0.0"
            if compat._parse(version) <= compat._parse(old) and not force:
                raise ValueError(f"{mod_id} {old} is already installed (this is {version}); use force to replace it")
            backup = workspace() / "backups" / f"{mod_id}-{old}-{_stamp()}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(target), str(backup))
            replaced = {"version": old, "backup": str(backup)}
        shutil.copytree(root, target)
        from .mods import validate
        from . import api
        try:
            game = api._game()
        except Exception:
            game = None
        valid = validate(game, mod_id) if game is not None else {"valid": None, "errors": []}
        check = compat.check_enable(mod_id)
        result = {"mod": mod_id, "version": version, "installed": str(target), "replaced": replaced,
                  "valid": valid.get("valid"), "errors": valid.get("errors", [])[:20], "compatibility": check["blocked"]}
        if enable:
            result["enabled"] = set_enabled(mod_id, True, force)["enabled"]
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)


def uninstall(mod_id: str) -> dict:
    read_mod(mod_id)
    try:
        set_enabled(mod_id, False)
    except Exception:
        pass
    trash = workspace() / "trash" / f"{mod_id}-{_stamp()}"
    trash.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(mod_dir(mod_id)), str(trash))
    return {"mod": mod_id, "moved_to": str(trash)}
