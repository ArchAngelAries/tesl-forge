"""Translations of a mod's text for TESL: Everlasting.

Mod text is written in English. A translation file, mods/<id>/locale/<language>.json {"strings": {"<English>": "<translation>"}},
gives the text shown when the game runs in that language (the engine looks strings up by their English text). `strings`
collects every piece of text the mod shows (card names and text, decks, avatars, AI opponents, packs, modes, stories ...), so
translators only fill in the blanks; CSV export/import lets them work in a spreadsheet.
"""
from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path

from .fsutil import atomic_write
from .mods import mod_dir, mod_cards, read_mod

LANGUAGES = {"de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "ru": "Russian", "pl": "Polish", "pt": "Portuguese",
             "ja": "Japanese", "zh": "Chinese", "ko": "Korean"}
TEXT_FIELDS = {"name", "title", "description", "text", "briefing", "label", "opponent_name", "line", "notes_ingame"}
SKIP_DIRS = {"locale", "history", "trash"}
LANG_RE = re.compile(r"^[a-z]{2}(-[a-z]{2,4})?$")


def _walk(value, out: list):
    if isinstance(value, dict):
        for k, v in value.items():
            if k in TEXT_FIELDS and isinstance(v, str) and v.strip() and not re.fullmatch(r"[a-z0-9-]+", v):
                out.append(v.strip())
            else:
                _walk(v, out)
    elif isinstance(value, list):
        for v in value:
            _walk(v, out)


def strings(mod_id: str) -> list[str]:
    """Every English text the mod shows, in a stable order, without duplicates."""
    meta = read_mod(mod_id)
    out = [meta.get("name", mod_id)]
    for c in mod_cards(mod_id):
        for k in ("Name", "Description"):
            v = (c.get(k) or "").strip()
            if v:
                out.append(v)
    root = mod_dir(mod_id)
    for p in sorted(root.rglob("*.json")):
        rel = p.relative_to(root)
        if rel.parts[0] in SKIP_DIRS or rel.parts[0] == "cards" or p.name == "mod.json":
            continue
        try:
            _walk(json.loads(p.read_text(encoding="utf-8")), out)
        except (OSError, ValueError):
            continue
    seen, uniq = set(), []
    for s in out:
        if s not in seen:
            seen.add(s); uniq.append(s)
    return uniq


def _path(mod_id: str, lang: str) -> Path:
    return mod_dir(mod_id) / "locale" / f"{lang}.json"


def _read(mod_id: str, lang: str) -> dict:
    p = _path(mod_id, lang)
    return json.loads(p.read_text(encoding="utf-8")).get("strings", {}) if p.is_file() else {}


def languages(mod_id: str) -> dict:
    read_mod(mod_id)
    total = strings(mod_id)
    out = []
    for p in sorted((mod_dir(mod_id) / "locale").glob("*.json")) if (mod_dir(mod_id) / "locale").is_dir() else []:
        tr = _read(mod_id, p.stem)
        out.append({"language": p.stem, "label": LANGUAGES.get(p.stem, p.stem), "done": sum(1 for s in total if tr.get(s)), "total": len(total)})
    return {"mod": mod_id, "languages": out, "known": [{"language": k, "label": v} for k, v in LANGUAGES.items()], "total": len(total)}


def table(mod_id: str, lang: str) -> dict:
    _lang(lang)
    tr = _read(mod_id, lang)
    rows = [{"english": s, "translation": tr.get(s, "")} for s in strings(mod_id)]
    stale = [k for k in tr if k not in {r["english"] for r in rows}]
    return {"mod": mod_id, "language": lang, "rows": rows, "unused": stale}


def _lang(lang: str) -> str:
    if not LANG_RE.match(lang or ""):
        raise ValueError("language: a code like de, fr, es, pt-br")
    return lang


def save(mod_id: str, lang: str, values: dict, merge: bool = True) -> dict:
    """values: {English: translation}. Empty translations are removed. merge=False replaces the whole table."""
    read_mod(mod_id)
    _lang(lang)
    tr = _read(mod_id, lang) if merge else {}
    for k, v in values.items():
        if not isinstance(k, str) or not k.strip():
            continue
        if v is None or not str(v).strip():
            tr.pop(k, None)
        else:
            tr[k] = str(v)
    p = _path(mod_id, lang)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps({"format": 1, "language": lang, "strings": tr}, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"mod": mod_id, "language": lang, "strings": len(tr)}


def export_csv(mod_id: str, lang: str) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["english", lang])
    for r in table(mod_id, lang)["rows"]:
        w.writerow([r["english"], r["translation"]])
    return buf.getvalue()


def import_csv(mod_id: str, lang: str, text: str) -> dict:
    """A two-column CSV (English, translation), with or without a header row."""
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    if rows and rows[0] and rows[0][0].strip().lower() == "english":
        rows = rows[1:]
    values = {r[0]: (r[1] if len(r) > 1 else "") for r in rows if r and r[0].strip()}
    known = set(strings(mod_id))
    unknown = [k for k in values if k not in known]
    res = save(mod_id, lang, values)
    return {**res, "imported": len(values), "not_in_mod": unknown[:20]}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    folder = mod_dir(mod_id) / "locale"
    if not folder.is_dir():
        return errors, warnings
    total = set(strings(mod_id))
    for p in sorted(folder.glob("*.json")):
        try:
            tr = json.loads(p.read_text(encoding="utf-8")).get("strings")
        except (OSError, ValueError):
            errors.append(f"translation {p.stem}: not valid JSON"); continue
        if not isinstance(tr, dict):
            errors.append(f"translation {p.stem}: no \"strings\""); continue
        missing = len([s for s in total if not tr.get(s)])
        if missing:
            warnings.append(f"translation {p.stem}: {missing} of {len(total)} texts not translated yet (they show in English)")
    return errors, warnings
