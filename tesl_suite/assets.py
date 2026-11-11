"""Asset index (from Unity bundle manifests) and extraction (UnityPy), original resolution, never modifying game files."""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
import threading
import re
import time
from pathlib import Path

from .game import GameInstall, workspace, assert_outside_game

KINDS = {
    "texture": (".png", ".tga", ".jpg", ".jpeg", ".psd", ".tif", ".tiff", ".exr", ".bmp"),
    "model": (".fbx", ".obj", ".blend", ".dae", ".3ds"),
    "audio": (".ogg", ".wav", ".mp3", ".aif", ".aiff"),
    "material": (".mat",),
    "prefab": (".prefab",),
    "animation": (".anim", ".controller", ".overridecontroller"),
    "shader": (".shader", ".shadervariants"),
    "font": (".ttf", ".otf", ".fontsettings"),
    "text": (".json", ".txt", ".bytes", ".xml", ".csv"),
}


def kind_of(path: str) -> str:
    low = path.lower()
    for kind, exts in KINDS.items():
        if low.endswith(exts):
            return kind
    return "other"


def index_path() -> Path:
    return workspace() / "asset-index.json"


def build_index(game: GameInstall) -> dict:
    """Read every bundle manifest's Assets list. Fast: no bundle is opened."""
    sa = Path(game.streaming_assets)
    entries = []
    bundles = 0
    started = time.time()
    for manifest in sorted(sa.rglob("*.manifest")):
        bundle = manifest.with_suffix("")
        if not bundle.is_file():
            continue
        bundles += 1
        rel = bundle.relative_to(sa).as_posix()
        in_assets = False
        for line in manifest.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("Assets:"):
                in_assets = True
                continue
            if in_assets:
                if line.startswith("- "):
                    path = line[2:].strip()
                    entries.append({"bundle": rel, "path": path, "kind": kind_of(path)})
                elif line.startswith(" ") and entries and entries[-1]["bundle"] == rel:
                    # YAML folds long paths that contain spaces onto indented continuation lines.
                    last = entries[-1]
                    last["path"] = last["path"] + " " + line.strip()
                    last["kind"] = kind_of(last["path"])
                else:
                    in_assets = False
    index = {"game": game.root, "built": time.strftime("%Y-%m-%dT%H:%M:%S"), "bundles": bundles,
             "assets": len(entries), "seconds": round(time.time() - started, 1), "entries": entries}
    atomic_write(index_path(), json.dumps(index), encoding="utf-8")
    return index


def load_index(game: GameInstall) -> dict:
    path = index_path()
    if path.is_file():
        index = json.loads(path.read_text(encoding="utf-8"))
        if index.get("game") == game.root:
            return index
    return build_index(game)


def query(index: dict, kind: str | None = None, contains: str | None = None, bundle: str | None = None,
          regex: str | None = None) -> list[dict]:
    pattern = re.compile(regex, re.IGNORECASE) if regex else None
    needle = contains.lower() if contains else None
    out = []
    for e in index["entries"]:
        if kind and e["kind"] != kind:
            continue
        if bundle and not e["bundle"].startswith(bundle):
            continue
        if needle and needle not in e["path"].lower():
            continue
        if pattern and not pattern.search(e["path"]):
            continue
        out.append(e)
    return out


def _preloaded(env, path_lower: str, type_name: str) -> list:
    """Objects of one type that belong to a container path (AssetBundle preload range, local objects only)."""
    local = {o.path_id: o for o in env.objects}
    found = []
    for o in env.objects:
        if o.type.name != "AssetBundle":
            continue
        ab = o.read()
        for path, info in ab.m_Container:
            if path.lower() != path_lower:
                continue
            for i in range(info.preloadIndex, info.preloadIndex + info.preloadSize):
                p = ab.m_PreloadTable[i]
                obj = local.get(p.m_PathID) if p.m_FileID == 0 else None
                if obj is not None and obj.type.name == type_name and obj not in found:
                    found.append(obj)
    return found


def _safe(name: str) -> str:
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip() or "unnamed"


def _alpha(image) -> bool:
    if image.mode not in ("RGBA", "LA", "PA"):
        return False
    lo, _hi = image.getchannel("A").getextrema()
    return lo < 255


_MANIFEST_LOCK = threading.Lock()


def export(game: GameInstall, entries: list[dict], out: Path, naming=None) -> list[dict]:
    """Extract the given index entries at original resolution. naming(entry) -> file stem (optional)."""
    import UnityPy  # imported lazily: the index and listing need no Unity reader

    out = out.resolve()
    assert_outside_game(out, game)
    out.mkdir(parents=True, exist_ok=True)
    by_bundle: dict[str, list[dict]] = {}
    for e in entries:
        by_bundle.setdefault(e["bundle"], []).append(e)
    results = []
    sa = Path(game.streaming_assets)
    for rel, wanted in by_bundle.items():
        env = UnityPy.load(str(sa / rel))
        # One path can name both a Texture2D and its Sprite: export the texture, record the sprite's crop rectangle.
        container, sprites = {}, {}
        for path, obj in env.container.items():
            key = path.lower()
            if obj.type.name == "Sprite":
                sprites[key] = obj
                container.setdefault(key, obj)
            else:
                container[key] = obj
        for e in wanted:
            key = e["path"].lower()
            obj = container.get(key)
            record = {"bundle": rel, "path": e["path"], "kind": e["kind"]}
            if obj is None:
                record["error"] = "not in bundle container"
                results.append(record)
                continue
            stem = _safe(naming(e) if naming else Path(e["path"]).stem)
            try:
                data = obj.read()
                t = obj.type.name
                record["unity_type"] = t
                if t == "Texture2D":
                    image = data.image
                    file = out / f"{stem}.png"
                    image.save(file)
                    record.update(file=str(file), width=data.m_Width, height=data.m_Height,
                                  alpha=_alpha(image), format=str(data.m_TextureFormat))
                    sprite = sprites.get(key)
                    if sprite is not None:
                        s = sprite.read()
                        r = s.m_Rect
                        record["sprite_rect"] = [round(r.x), round(r.y), round(r.width), round(r.height)]
                        record["full_art"] = round(r.width) == data.m_Width and round(r.height) == data.m_Height
                elif t == "Sprite":
                    # A sprite with no texture of its own under this path (cut from a sprite sheet): export the sprite.
                    image = data.image
                    file = out / f"{stem}.png"
                    image.save(file)
                    r = data.m_Rect
                    record.update(file=str(file), width=image.width, height=image.height, alpha=_alpha(image),
                                  sprite_rect=[round(r.x), round(r.y), round(r.width), round(r.height)], from_sprite_sheet=True)
                elif t == "AudioClip":
                    files = []
                    for name, raw in data.samples.items():
                        file = out / _safe(name)
                        file.write_bytes(raw)
                        files.append(str(file))
                    record["files"] = files
                elif t == "Mesh":
                    file = out / f"{stem}.obj"
                    file.write_text(data.export(), encoding="utf-8")
                    record["file"] = str(file)
                elif e["kind"] == "model":
                    # An FBX path names its root (GameObject/Avatar); its meshes are in the bundle's preload range.
                    files = []
                    for mesh in _preloaded(env, key, "Mesh"):
                        m = mesh.read()
                        file = out / f"{stem} - {_safe(m.m_Name)}.obj"
                        file.write_text(m.export(), encoding="utf-8")
                        files.append(str(file))
                    if files:
                        record["files"] = files
                    else:
                        record["skipped"] = "model has no mesh objects in this bundle"
                elif t == "TextAsset":
                    file = out / Path(e["path"]).name
                    raw = data.m_Script
                    file.write_bytes(raw.encode("utf-8", "surrogateescape") if isinstance(raw, str) else bytes(raw))
                    record["file"] = str(file)
                else:
                    record["skipped"] = f"{t} export not supported yet"
            except Exception as ex:  # report and continue: one bad asset must not stop a batch
                record["error"] = f"{type(ex).__name__}: {ex}"
            results.append(record)
    # One manifest per folder, newest record per path. Written atomically under a lock: the app exports previews from
    # several requests at once, and a half-written manifest used to break every later export into that folder.
    with _MANIFEST_LOCK:
        manifest = out / "export-manifest.json"
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else []
        except (ValueError, OSError):
            previous = []
        done = {r["path"] for r in results}
        merged = [r for r in previous if isinstance(r, dict) and r.get("path") not in done] + results
        tmp = manifest.with_name(f"export-manifest.{threading.get_ident()}.tmp")
        atomic_write(tmp, json.dumps(merged, indent=1), encoding="utf-8")
        tmp.replace(manifest)
    return results
