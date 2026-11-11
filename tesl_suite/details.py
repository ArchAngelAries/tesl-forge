"""A mod's details: name, author, description, version, what it needs or clashes with, load-order hints, a changelog and a
preview picture. Kept in mod.json; exported packages carry them as README.md, CHANGELOG.md and preview.png.

dependencies: [{"id": "other-mod", "version": ">=1.2"}] (version ranges: * 1.2 >=1.2 <2 ^1.2 ~1.2.3 or several, space-separated)
conflicts / load_after / load_before: lists of mod ids.
changelog: [{"version": "1.1.0", "date": "2026-11-05", "notes": "..."}], newest first.
"""
from __future__ import annotations

import datetime
import json
import re
import shutil
from pathlib import Path

from .fsutil import atomic_write
from .mods import ID_RE, mod_dir, read_mod

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
RANGE_RE = re.compile(r"^(\*|((>=|<=|>|<|\^|~|=)?\d+(\.\d+){0,2})([ ,]+(>=|<=|>|<|\^|~|=)?\d+(\.\d+){0,2})*)$")


def _write(mod_id: str, meta: dict) -> None:
    atomic_write(mod_dir(mod_id) / "mod.json", json.dumps(meta, indent=1, ensure_ascii=False), encoding="utf-8")


def get(mod_id: str) -> dict:
    m = read_mod(mod_id)
    p = m.get("preview")
    return {"id": mod_id, "name": m.get("name", mod_id), "author": m.get("author", ""), "description": m.get("description", ""),
            "version": m.get("version") or "1.0.0", "dependencies": [d if isinstance(d, dict) else {"id": d, "version": "*"} for d in m.get("dependencies") or []],
            "conflicts": m.get("conflicts") or [], "load_after": m.get("load_after") or [], "load_before": m.get("load_before") or [],
            "changelog": m.get("changelog") or [], "preview": p, "preview_url": f"/mod-file/{mod_id}/{p}" if p else None,
            "website": m.get("website", "")}


def _ids(values, field: str, mod_id: str) -> list[str]:
    out = []
    for v in values or []:
        v = str(v).strip()
        if not v:
            continue
        if not ID_RE.match(v):
            raise ValueError(f"{field}: '{v}' is not a mod id (lowercase letters, digits, dashes)")
        if v == mod_id:
            raise ValueError(f"{field}: a mod cannot name itself")
        if v not in out:
            out.append(v)
    return out


def update(mod_id: str, fields: dict) -> dict:
    """Change any of: name, author, description, website, version, dependencies, conflicts, load_after, load_before."""
    meta = read_mod(mod_id)
    for k in ("name", "author", "description", "website"):
        if k in fields and fields[k] is not None:
            meta[k] = str(fields[k]).strip()
    if not meta.get("name"):
        raise ValueError("a mod needs a name")
    if fields.get("version") is not None:
        v = str(fields["version"]).strip()
        if not VERSION_RE.match(v):
            raise ValueError("version must look like 1.2.3")
        meta["version"] = v
    if "dependencies" in fields and fields["dependencies"] is not None:
        deps = []
        for d in fields["dependencies"]:
            d = {"id": d} if isinstance(d, str) else d
            i = (d.get("id") or "").strip()
            if not i:
                continue
            rng = (d.get("version") or "*").strip() or "*"
            if not RANGE_RE.match(rng):
                raise ValueError(f"dependency {i}: version '{rng}' is not a range (e.g. * or >=1.2 or ^1.0)")
            deps.append({"id": _ids([i], "dependencies", mod_id)[0], "version": rng})
        meta["dependencies"] = deps
    for k in ("conflicts", "load_after", "load_before"):
        if k in fields and fields[k] is not None:
            vals = fields[k].replace(",", " ").split() if isinstance(fields[k], str) else fields[k]
            meta[k] = _ids(vals, k, mod_id)
    both = set(meta.get("conflicts") or []) & {d["id"] for d in meta.get("dependencies") or []}
    if both:
        raise ValueError(f"a mod cannot both need and conflict with {', '.join(sorted(both))}")
    _write(mod_id, meta)
    return get(mod_id)


def bump(version: str, part: str) -> str:
    a, b, c = (int(x) for x in (version if VERSION_RE.match(version or "") else "1.0.0").split("."))
    return {"major": f"{a + 1}.0.0", "minor": f"{a}.{b + 1}.0", "patch": f"{a}.{b}.{c + 1}"}[part]


def add_change(mod_id: str, notes: str, part: str = "minor", version: str | None = None) -> dict:
    """Record a release: the version goes up (major/minor/patch, or the version given) and the notes join the changelog."""
    meta = read_mod(mod_id)
    if not (notes or "").strip():
        raise ValueError("write what changed")
    new = version.strip() if version else bump(meta.get("version") or "1.0.0", part)
    if not VERSION_RE.match(new):
        raise ValueError("version must look like 1.2.3")
    log = meta.get("changelog") or []
    if any(e.get("version") == new for e in log):
        raise ValueError(f"the changelog already has {new}")
    meta["version"] = new
    meta["changelog"] = [{"version": new, "date": datetime.date.today().isoformat(), "notes": notes.strip()}] + log
    _write(mod_id, meta)
    return get(mod_id)


def set_preview(mod_id: str, image: str) -> dict:
    from PIL import Image
    src = Path(image)
    if not src.is_file():
        raise ValueError(f"Image not found: {image}")
    img = Image.open(src).convert("RGB")
    img.thumbnail((1280, 720))
    img.save(mod_dir(mod_id) / "preview.png")
    meta = read_mod(mod_id)
    meta["preview"] = "preview.png"
    _write(mod_id, meta)
    return get(mod_id)


def readme(mod_id: str, features: list[str], cls: str, engine: int) -> str:
    d = get(mod_id)
    lines = [f"# {d['name']}", "", d["description"] or "", "", f"- Version: {d['version']}", f"- Author: {d['author'] or 'unknown'}",
             f"- Adds: {', '.join(features) or 'nothing yet'}",
             f"- Needs TESL: Everlasting engine level {engine} or newer",
             "- Multiplayer: " + {"local": "local-only changes (art, sound, music, boards); fine in online play",
                                  "cosmetic": "cosmetic; shown only to you",
                                  "gameplay": "changes gameplay; offline play, or servers where everyone has the same mods"}.get(cls, cls)]
    if d["dependencies"]:
        lines.append("- Needs: " + ", ".join(f"{x['id']} ({x['version']})" for x in d["dependencies"]))
    if d["conflicts"]:
        lines.append("- Does not work with: " + ", ".join(d["conflicts"]))
    if d["website"]:
        lines.append(f"- Website: {d['website']}")
    lines += ["", "Install with TESL Forge (Load order > Install a mod) or unzip the folder into TESL Forge's mods folder.", ""]
    return "\n".join(lines)


def changelog_md(mod_id: str) -> str:
    d = get(mod_id)
    out = [f"# {d['name']} changelog", ""]
    for e in d["changelog"]:
        out += [f"## {e['version']} ({e.get('date', '')})", "", e.get("notes", ""), ""]
    if not d["changelog"]:
        out.append("No releases recorded yet.")
    return "\n".join(out) + "\n"
