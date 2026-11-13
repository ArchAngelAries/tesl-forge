"""New avatar choices. A mod's avatars appear as their own pages in the game's avatar picker (four per page), and can be
selected like the originals. Each avatar is a full-body portrait in the original shape (286 x 512, any resolution in
that ratio) plus a head-and-shoulders square used where the game shows round avatars (profile, match intro, arena).
Emote voice lines are borrowed from an original avatar (`voice`).

Layout: mods/<id>/avatars/avatars.json + the PNG files beside it.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash
from .settings import find_tool as _tool

import json
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

PORTRAIT = (286, 512)
CIRCLE = 512
MAX_HEIGHT = 2048


def _manifest_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "avatars" / "avatars.json"


def _read(mod_id: str) -> dict:
    p = _manifest_path(mod_id)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "avatars": []}


def _write(mod_id: str, manifest: dict) -> None:
    p = _manifest_path(mod_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def crops(src: Path, dest_dir: Path, slug: str, head: float = 0.22, profile: Path | None = None) -> dict:
    """Portrait: cover-crop to 286:512, keeping the source resolution (at least 286 x 512, at most MAX_HEIGHT tall).
    Circle: a square around the head (head = its height as a fraction of the portrait from the top), 512 x 512;
    or, when `profile` is given, that picture (centre-cropped square) as the round profile portrait."""
    from PIL import Image
    img = Image.open(src).convert("RGBA")
    aspect = PORTRAIT[0] / PORTRAIT[1]
    w, h = img.size
    if w / h > aspect:
        nw = round(h * aspect); img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
    else:
        nh = round(w / aspect); img = img.crop((0, 0, w, nh))           # keep the top (the head) when trimming height
    th = min(max(PORTRAIT[1], img.height), MAX_HEIGHT)
    portrait = img.resize((round(th * aspect), th), Image.LANCZOS)
    dest_dir.mkdir(parents=True, exist_ok=True)
    portrait.save(dest_dir / f"{slug}.png")
    side = portrait.width
    top = min(max(0, round(portrait.height * head - side / 2)), portrait.height - side)
    circle = portrait.crop((0, top, side, top + side)).resize((CIRCLE, CIRCLE), Image.LANCZOS)
    if profile is not None:
        pimg = Image.open(profile).convert("RGBA")
        pw, ph = pimg.size; ps = min(pw, ph)
        circle = pimg.crop(((pw - ps) // 2, (ph - ps) // 2, (pw - ps) // 2 + ps, (ph - ps) // 2 + ps)).resize((CIRCLE, CIRCLE), Image.LANCZOS)
    # The originals (arena portraits) are 512 x 512 with a soft transparent circle edge.
    from PIL import ImageDraw
    big = Image.new("L", (CIRCLE * 4, CIRCLE * 4), 0)
    ImageDraw.Draw(big).ellipse((0, 0, CIRCLE * 4 - 1, CIRCLE * 4 - 1), fill=255)
    mask = big.resize((CIRCLE, CIRCLE), Image.LANCZOS)
    from PIL import ImageChops
    circle.putalpha(ImageChops.multiply(circle.getchannel("A"), mask))
    circle.save(dest_dir / f"{slug}-circle.png")
    return {"image": f"{slug}.png", "circle": f"{slug}-circle.png", "width": portrait.width, "height": portrait.height}


def original_avatars() -> list[dict]:
    """Original avatars (from the game configuration): name, race page, emote package; used for --voice."""
    rows = (Path(__file__).parent / "data" / "original-avatars.tsv").read_text(encoding="utf-8").splitlines()
    head = rows[0].split("	")
    return [dict(zip(head, r.split("	"))) for r in rows[1:] if r.strip()]


def new_avatar(mod_id: str, name: str, image: str, voice: str | None = None, head: float = 0.22, profile: str | None = None) -> dict:
    """profile: a separate picture for the round profile portrait (the rune circle); default: cut from the portrait."""
    meta = read_mod(mod_id)
    src = Path(image)
    if not src.is_file():
        raise ValueError(f"Image not found: {image}")
    if profile and not Path(profile).is_file():
        raise ValueError(f"Profile image not found: {profile}")
    if voice and voice not in {a["unique_name"] for a in original_avatars()}:
        raise ValueError(f"Unknown voice '{voice}': use an original avatar name (tesl avatar voices)")
    slug = slugify(name)
    files = crops(src, mod_dir(mod_id) / "avatars", slug, head, Path(profile) if profile else None)
    manifest = _read(mod_id)
    entry = {"slug": slug, "name": name, **{k: files[k] for k in ("image", "circle")}}
    if voice:
        entry["voice"] = voice
    manifest["avatars"] = [a for a in manifest["avatars"] if a["slug"] != slug] + [entry]
    manifest.setdefault("page", {"name": meta.get("name", mod_id)})
    _write(mod_id, manifest)
    n = len(manifest["avatars"])
    return {"mod": mod_id, "avatar": {**entry, "width": files["width"], "height": files["height"],
            "game_id": f"mod.{mod_id}.avatar.{slug}"}, "total": n, "pages": (n + 3) // 4}


EMOTE_TYPES = ("Hello", "GoodGame", "Implore", "Taunt", "Oops", "NicePlay", "ThankYou", "Sorry")


def _to_wav(src: Path, dest: Path) -> float:
    """Copy a PCM WAV, or convert any audio with ffmpeg (if installed) to 16-bit 44.1 kHz WAV. Returns seconds."""
    import shutil, subprocess, wave
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        with wave.open(str(src), "rb") as w:
            if w.getsampwidth() in (1, 2) and w.getcomptype() == "NONE":
                shutil.copyfile(src, dest)
                return w.getnframes() / w.getframerate()
    except (wave.Error, EOFError):
        pass
    ffmpeg = _tool("ffmpeg")
    if not ffmpeg:
        raise ValueError(f"{src.name} is not a plain WAV and ffmpeg was not found to convert it")
    subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(dest)], check=True)
    with wave.open(str(dest), "rb") as w:
        return w.getnframes() / w.getframerate()


def set_emote(mod_id: str, avatar: str, emote: str, text: str | None = None, audio: str | None = None) -> dict:
    """An avatar's own line for one emote (types: EMOTE_TYPES); emotes it doesn't set keep its voice's lines."""
    manifest = _read(mod_id)
    slug = slugify(avatar)
    entry = next((a for a in manifest["avatars"] if a["slug"] in (slug, avatar)), None)
    if entry is None:
        raise ValueError(f"{mod_id} has no avatar '{avatar}' (tesl avatar list)")
    kind = next((t for t in EMOTE_TYPES if t.lower() == emote.replace(" ", "").lower()), None)
    if kind is None:
        raise ValueError(f"Unknown emote '{emote}': one of {', '.join(EMOTE_TYPES)}")
    if text is None and audio is None:
        raise ValueError("give --text and/or --audio")
    line = entry.setdefault("emotes", {}).setdefault(kind, {})
    if text is not None:
        line["text"] = text
    seconds = None
    if audio:
        src = Path(audio)
        if not src.is_file():
            raise ValueError(f"Audio not found: {audio}")
        name = f"{entry['slug']}-emote-{kind}.wav"
        seconds = round(_to_wav(src, mod_dir(mod_id) / "avatars" / name), 2)
        line["audio"] = name
    _write(mod_id, manifest)
    return {"mod": mod_id, "avatar": entry["slug"], "emote": kind, "line": line, "audio_seconds": seconds}


def set_page(mod_id: str, name: str | None = None, description: str | None = None) -> dict:
    manifest = _read(mod_id)
    page = manifest.setdefault("page", {})
    if name:
        page["name"] = name
    if description is not None:
        page["description"] = description
    _write(mod_id, manifest)
    return {"mod": mod_id, "page": page}


def list_avatars(mod_id: str) -> dict:
    read_mod(mod_id)
    m = _read(mod_id)
    return {"mod": mod_id, "page": m.get("page", {}), "avatars": m["avatars"]}


def remove(mod_id: str, name: str) -> dict:
    manifest = _read(mod_id)
    slug = slugify(name)
    gone = [a for a in manifest["avatars"] if a["slug"] in (slug, name)]
    if not gone:
        raise ValueError(f"{mod_id} has no avatar '{name}'")
    manifest["avatars"] = [a for a in manifest["avatars"] if a not in gone]
    for a in gone:
        for k in ("image", "circle"):
            f = mod_dir(mod_id) / "avatars" / a[k]
            if f.is_file():
                trash(f, mod_id)
    _write(mod_id, manifest)
    return {"mod": mod_id, "removed": gone[0]["slug"], "total": len(manifest["avatars"])}


def check(mod_id: str) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    for a in _read(mod_id)["avatars"]:
        for k in ("image", "circle"):
            if not (mod_dir(mod_id) / "avatars" / a.get(k, "")).is_file():
                errors.append(f"avatar {a['slug']}: missing {k} file")
        for kind, line in a.get("emotes", {}).items():
            if kind not in EMOTE_TYPES:
                errors.append(f"avatar {a['slug']}: unknown emote {kind}")
            if line.get("audio") and not (mod_dir(mod_id) / "avatars" / line["audio"]).is_file():
                errors.append(f"avatar {a['slug']}: emote {kind} audio missing")
    return errors, warnings


# ---- extra emotes (beyond the game's eight) -------------------------------------------------------------------------
# Per avatar (avatars.json "extra_emotes") or for every avatar, originals included (emotes/emotes.json). In a match the
# emote panel gets a "More" button that pages through them. "like" (one of EMOTE_TYPES) lets the AI use it as a variant
# of that emote and answer it like that emote.

def _global_path(mod_id: str) -> Path:
    return mod_dir(mod_id) / "emotes" / "emotes.json"


def _extras(mod_id: str, avatar: str | None):
    """(list, folder, save) for an avatar's extras or the mod-wide ones."""
    if avatar:
        manifest = _read(mod_id)
        slug = slugify(avatar)
        entry = next((a for a in manifest["avatars"] if a["slug"] in (slug, avatar)), None)
        if entry is None:
            raise ValueError(f"{mod_id} has no avatar '{avatar}' (tesl avatar list)")
        return entry.setdefault("extra_emotes", []), mod_dir(mod_id) / "avatars", lambda: _write(mod_id, manifest), entry["slug"]
    p = _global_path(mod_id)
    data = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "emotes": []}

    def save():
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(p, json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return data["emotes"], p.parent, save, "all"


def add_extra_emote(mod_id: str, text: str, label: str | None = None, avatar: str | None = None, audio: str | None = None,
                    like: str | None = None) -> dict:
    read_mod(mod_id)
    if not text and not audio:
        raise ValueError("give the text and/or audio")
    if like:
        kind = next((t for t in EMOTE_TYPES if t.lower() == like.replace(" ", "").lower()), None)
        if kind is None:
            raise ValueError(f"like must be one of {', '.join(EMOTE_TYPES)}")
        like = kind
    items, folder, save, owner = _extras(mod_id, avatar)
    label = (label or text or "Emote").strip()
    slug = slugify(label)[:40] or f"extra-{len(items) + 1}"
    while any(x["slug"] == slug for x in items):
        slug += "-2"
    entry = {"slug": slug, "label": label[:24], "text": text or ""}
    if like:
        entry["like"] = like
    seconds = None
    if audio:
        src = Path(audio)
        if not src.is_file():
            raise ValueError(f"Audio not found: {audio}")
        name = f"extra-{owner}-{slug}.wav"
        seconds = round(_to_wav(src, folder / name), 2)
        entry["audio"] = name
    items.append(entry)
    save()
    return {"mod": mod_id, "avatar": avatar or "(every avatar)", "emote": entry, "audio_seconds": seconds, "total": len(items)}


def list_extra_emotes(mod_id: str) -> dict:
    read_mod(mod_id)
    out = {"mod": mod_id, "all_avatars": _extras(mod_id, None)[0], "avatars": {}}
    for a in _read(mod_id)["avatars"]:
        if a.get("extra_emotes"):
            out["avatars"][a["slug"]] = a["extra_emotes"]
    return out


def remove_extra_emote(mod_id: str, emote: str, avatar: str | None = None) -> dict:
    items, folder, save, _ = _extras(mod_id, avatar)
    hit = next((x for x in items if emote in (x["slug"], x["label"])), None)
    if hit is None:
        raise ValueError(f"no extra emote '{emote}'")
    items.remove(hit)
    if hit.get("audio"):
        (folder / hit["audio"]).unlink(missing_ok=True)
    save()
    return {"mod": mod_id, "removed": hit["slug"], "total": len(items)}


def check_extras(mod_id: str) -> list[str]:
    errors = []
    lists = [(x, mod_dir(mod_id) / "avatars", a["slug"]) for a in _read(mod_id)["avatars"] for x in a.get("extra_emotes", [])]
    lists += [(x, _global_path(mod_id).parent, "all") for x in _extras(mod_id, None)[0]]
    for x, folder, owner in lists:
        if x.get("audio") and not (folder / x["audio"]).is_file():
            errors.append(f"extra emote {owner}/{x['slug']}: audio missing")
        if x.get("like") and x["like"] not in EMOTE_TYPES:
            errors.append(f"extra emote {owner}/{x['slug']}: like must be one of the eight")
    return errors
