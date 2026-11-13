"""Board editor: change everything on a board and add your own things.

A mod board (tesl_suite.boards) sits on one of the five game boards. Besides (or instead of) a new table painting it
can carry edits, applied in the game when the board loads:
  - existing objects: hide, move, rotate, resize, tint, glow, new textures (by object, or a texture everywhere it is used);
  - lights: on/off, colour, brightness, reach; the whole board's brightness and tint;
  - particle effects: on/off, colour, speed, amount, size; animations: speed, on/off;
  - new things: 3D models (OBJ, glTF/GLB; FBX, .blend, DAE, 3DS, STL, PLY, USD... converted with Blender when it is
    installed), flat images (decals, banners, rugs), lights, particle effects (embers, mist, fireflies, sparks, snow,
    magic, smoke, bubbles), each with an optional motion (spin, bob, sway, pulse, float).
Positions of new things are given as a spot on the board picture (x, y from 0 to 1, left/top = 0) or in board units.

Board maps (data/boards/<Base>.json): every object of each game board with its position, materials, lights, effects and
the camera, recorded by the offline engine's `boardmap` diagnostic; board pictures in workspace/board-maps/<Base>.jpg.
"""
from __future__ import annotations
from .fsutil import atomic_write, trash

import json
import re
import shutil
import subprocess
from pathlib import Path

from .mods import mod_dir, read_mod, slugify

DATA = Path(__file__).parent / "data" / "boards"
PRESETS = ["embers", "mist", "fireflies", "sparks", "snow", "magic", "smoke", "bubbles"]
MOTIONS = ["spin", "bob", "sway", "pulse", "float"]
NATIVE_MODELS = (".obj", ".glb", ".gltf")
BLENDER_MODELS = (".fbx", ".blend", ".dae", ".3ds", ".stl", ".ply", ".x3d", ".usd", ".usda", ".usdc", ".usdz", ".abc")
BOARD_NAMES = {"Original": "Original", "IsleOfMadness": "Isle of Madness", "AllianceWar": "Alliance War", "Elsweyr": "Elsweyr",
               "RealmsOfOblivion": "Realms of Oblivion"}


# ---- maps -------------------------------------------------------------------------------------------------------------
def _workspace() -> Path:
    from .game import SUITE_ROOT
    return Path(SUITE_ROOT) / "workspace"


def raw_map(base: str) -> dict:
    f = DATA / f"{base}.json"
    if not f.is_file():
        raise ValueError(f"No map for board {base}")
    return json.loads(f.read_text(encoding="utf-8"))


def picture(base: str) -> Path | None:
    f = _workspace() / "board-maps" / f"{base}.jpg"
    return f if f.is_file() else None


def _mul(m: list[float], v: list[float]) -> list[float]:
    return [sum(m[r * 4 + c] * v[c] for c in range(4)) for r in range(4)]


def project(m: dict, world: list[float]) -> tuple[float, float] | None:
    c = _mul(m["camera"]["viewProjection"], [world[0], world[1], world[2], 1.0])
    if c[3] <= 1e-6:
        return None
    return (c[0] / c[3] + 1) / 2, 1 - (c[1] / c[3] + 1) / 2


def _inverse(a: list[float]) -> list[float]:
    """4x4 inverse (row-major), Gauss-Jordan."""
    m = [a[r * 4:(r + 1) * 4] + [1.0 if r == c else 0.0 for c in range(4)] for r in range(4)]
    for col in range(4):
        piv = max(range(col, 4), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        p = m[col][col]
        m[col] = [x / p for x in m[col]]
        for r in range(4):
            if r != col:
                f = m[r][col]
                m[r] = [x - f * y for x, y in zip(m[r], m[col])]
    return [m[r][4 + c] for r in range(4) for c in range(4)]


def table_height(m: dict) -> float:
    """The table's top: the widest flat renderer on the board (Background, BG Plane...)."""
    flat = [n for n in m["nodes"] if n.get("bounds") and n["bounds"][1][1] < 1.0 and n["bounds"][1][0] > 40]
    if not flat:
        return 0.0
    bg = max(flat, key=lambda n: n["bounds"][1][0] * n["bounds"][1][2])
    return round(bg["bounds"][0][1] + bg["bounds"][1][1] / 2, 3)


def unproject(m: dict, x: float, y: float, height: float | None = None) -> list[float]:
    """The point on the table (or at `height`) under a spot on the board picture (0..1, top-left origin)."""
    inv = _inverse(m["camera"]["viewProjection"])
    nx, ny = x * 2 - 1, (1 - y) * 2 - 1
    near, far = _mul(inv, [nx, ny, -1, 1]), _mul(inv, [nx, ny, 1, 1])
    near, far = [v / near[3] for v in near[:3]], [v / far[3] for v in far[:3]]
    h = table_height(m) if height is None else height
    t = (h - near[1]) / ((far[1] - near[1]) or 1e-9)
    return [round(near[i] + (far[i] - near[i]) * t, 3) for i in range(3)]


def _label(name: str) -> str:
    name = re.sub(r"(?i)^(iom|aw|els|oc|playmat|fx_par|fx_mesh|fx)_", "", name)
    name = re.sub(r"\(Clone\)|_\d{1,2}$", "", name)
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).replace("_", " ").strip()
    return name[:1].upper() + name[1:] if name else "object"


def board_map(base: str) -> dict:
    """What can be edited on a game board: objects (with a spot on the picture), lights, effects, animations, textures."""
    m = raw_map(base)
    objects, lights, effects, anims, textures = [], [], [], [], {}
    for n in m["nodes"]:
        path = n["path"]
        if not path or "CATRig" in path or "Bone" in path.rsplit("/", 1)[-1] or (n.get("components") and "DynamicSoundGroup" in " ".join(n["components"])
                                                                                  and "renderer" not in n):
            continue
        sized = n.get("bounds") and max(n["bounds"][1]) > 0.05
        spot = project(m, n["bounds"][0] if sized else n["world"])
        item = {"path": path, "label": _label(path.rsplit("/", 1)[-1]), "depth": path.count("/"), "active": n["active"],
                "spot": [round(spot[0], 4), round(spot[1], 4)] if spot else None, "pos": n["pos"], "rot": n["rot"], "scale": n["scale"],
                "world": n["world"], "clickable": bool(n.get("clickable"))}
        if n.get("renderer"):
            item["textures"] = sorted({t["name"] for mt in n["renderer"]["materials"] if mt for t in mt["textures"].values()})
            for mt in n["renderer"]["materials"]:
                for prop, t in (mt or {}).get("textures", {}).items():
                    e = textures.setdefault(t["name"], {"texture": t["name"], "size": t["size"], "used_by": []})
                    if path not in e["used_by"]:
                        e["used_by"].append(path)
        if "light" in n:
            lights.append({**item, "light": n["light"]})
        if "particles" in n:
            effects.append({**item, "particles": n["particles"]})
        if "animator" in n or "animation" in n:
            anims.append({**item, "animator": n.get("animator"), "animation": n.get("animation")})
        if n.get("renderer") or n.get("animator") or n.get("clickable"):
            objects.append(item)
    for t in textures.values():
        base_name, part = re.sub(r"_\d{1,2}(_[A-Za-z]+)?$", "", t["texture"]), ""
        low = t["texture"].lower()
        for suf, what in (("_d", "colour"), ("_n", "normal map"), ("_s", "specular"), ("_e", "glow"), ("_mask", "mask")):
            if low.endswith(suf):
                part = what
        t["label"] = _label(base_name) + (f" ({part})" if part else "")
    return {"board": base, "name": BOARD_NAMES.get(base, base), "picture": bool(picture(base)), "table_height": table_height(m), "camera": m["camera"],
            "objects": objects, "lights": lights, "effects": effects, "animations": anims,
            "textures": sorted(textures.values(), key=lambda t: t["label"].lower()), "presets": PRESETS, "motions": MOTIONS}


# ---- the mod board's edits ----------------------------------------------------------------------------------------------
def _manifest(mod_id: str) -> tuple[dict, Path]:
    p = mod_dir(mod_id) / "boards" / "boards.json"
    return (json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {"format": 1, "boards": []}), p


def _entry(mod_id: str, board: str) -> tuple[dict, dict, Path]:
    read_mod(mod_id)
    manifest, p = _manifest(mod_id)
    slug = slugify(board)
    e = next((b for b in manifest["boards"] if b["slug"] in (slug, board)), None)
    if e is None:
        raise ValueError(f"{mod_id} has no board '{board}' (tesl board new)")
    return manifest, e, p


def _save(manifest: dict, p: Path) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(p, json.dumps(manifest, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


def _files_dir(mod_id: str, entry: dict) -> Path:
    d = mod_dir(mod_id) / "boards" / entry["slug"]
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rel(mod_id: str, f: Path) -> str:
    return f.relative_to(mod_dir(mod_id) / "boards").as_posix()


def _color(c) -> list[float] | None:
    """[r,g,b(,a)] 0..1, or '#rrggbb'."""
    if c is None or c == "":
        return None
    if isinstance(c, str):
        h = c.lstrip("#")
        return [round(int(h[i:i + 2], 16) / 255, 3) for i in (0, 2, 4)] + ([round(int(h[6:8], 16) / 255, 3)] if len(h) == 8 else [1.0])
    return [float(x) for x in c]


def _vec(v) -> list[float] | None:
    if v is None or v == "":
        return None
    if isinstance(v, str):
        v = [x for x in re.split(r"[,\s]+", v.strip()) if x]
    return [float(x) for x in v]


def _image(src: str, dest: Path, max_side: int = 4096) -> Path:
    from PIL import Image
    s = Path(src)
    if not s.is_file():
        raise ValueError(f"Image not found: {src}")
    img = Image.open(s)
    img = img.convert("RGBA") if img.mode in ("RGBA", "LA", "P") else img.convert("RGB")
    if max(img.size) > max_side:
        img.thumbnail((max_side, max_side), Image.LANCZOS)
    dest = dest.with_suffix(".png")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest)
    return dest


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def edit_object(mod_id: str, board: str, path: str, hide: bool | None = None, pos=None, rot=None, scale=None, offset=None,
                tint=None, glow=None, image: str | None = None, reset: bool = False, x=None, y=None) -> dict:
    """x, y: move the object to that spot on the board picture (kept at its height)."""
    manifest, e, p = _entry(mod_id, board)
    if x is not None and y is not None:
        node = next((n for n in raw_map(e["base"])["nodes"] if n["path"] == path), None)
        if node is None:
            raise ValueError(f"no object {path} on {e['base']}")
        target = unproject(raw_map(e["base"]), float(x), float(y), node["world"][1])
        offset = [round(target[0] - node["world"][0], 3), 0.0, round(target[2] - node["world"][2], 3)]
    objs = e.setdefault("edits", {}).setdefault("objects", {})
    if reset:
        objs.pop(path, None)
    else:
        cur = objs.setdefault(path, {})
        cur.update(_clean({"hide": hide, "pos": _vec(pos), "rot": _vec(rot), "scale": _vec(scale), "offset": _vec(offset),
                           "tint": _color(tint), "glow": _color(glow)}))
        if image:
            f = _image(image, _files_dir(mod_id, e) / "textures" / slugify(path.rsplit("/", 1)[-1]))
            cur.setdefault("textures", {})["color"] = _rel(mod_id, f)
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "object": path, "edit": objs.get(path)}


def edit_texture(mod_id: str, board: str, texture: str, image: str | None, reset: bool = False) -> dict:
    manifest, e, p = _entry(mod_id, board)
    texs = e.setdefault("edits", {}).setdefault("textures", {})
    if reset or not image:
        texs.pop(texture, None)
    else:
        texs[texture] = _rel(mod_id, _image(image, _files_dir(mod_id, e) / "textures" / slugify(texture)))
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "texture": texture, "file": texs.get(texture)}


def edit_light(mod_id: str, board: str, path: str, enabled=None, color=None, intensity=None, range_=None, reset=False) -> dict:
    manifest, e, p = _entry(mod_id, board)
    ls = e.setdefault("edits", {}).setdefault("lights", {})
    if reset:
        ls.pop(path, None)
    else:
        ls.setdefault(path, {}).update(_clean({"enabled": enabled, "color": _color(color), "intensity": intensity, "range": range_}))
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "light": path, "edit": ls.get(path)}


def edit_lighting(mod_id: str, board: str, brightness=None, tint=None, reset=False) -> dict:
    manifest, e, p = _entry(mod_id, board)
    ed = e.setdefault("edits", {})
    if reset:
        ed.pop("lighting", None)
    else:
        ed.setdefault("lighting", {}).update(_clean({"brightness": brightness, "tint": _color(tint)}))
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "lighting": ed.get("lighting")}


def edit_effect(mod_id: str, board: str, path: str, enabled=None, color=None, speed=None, rate=None, size=None, reset=False) -> dict:
    manifest, e, p = _entry(mod_id, board)
    ps = e.setdefault("edits", {}).setdefault("particles", {})
    if reset:
        ps.pop(path, None)
    else:
        ps.setdefault(path, {}).update(_clean({"enabled": enabled, "color": _color(color), "speed": speed, "rate": rate, "size": size}))
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "effect": path, "edit": ps.get(path)}


def edit_animation(mod_id: str, board: str, path: str, enabled=None, speed=None, reset=False) -> dict:
    manifest, e, p = _entry(mod_id, board)
    an = e.setdefault("edits", {}).setdefault("animators", {})
    if reset:
        an.pop(path, None)
    else:
        an.setdefault(path, {}).update(_clean({"enabled": enabled, "speed": speed}))
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "animation": path, "edit": an.get(path)}


# ---- new things ---------------------------------------------------------------------------------------------------------
def blender() -> str | None:
    """blender.exe: the 'blender' setting, PATH, or the usual install folders (settings.find_blender)."""
    from . import settings
    return settings.find_blender()


_BLENDER_SCRIPT = r'''
import bpy, sys
src, dst = sys.argv[sys.argv.index("--") + 1:][:2]
ext = src.lower().rsplit(".", 1)[-1]
if ext != "blend":
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imp = {"fbx": lambda: bpy.ops.import_scene.fbx(filepath=src), "dae": lambda: bpy.ops.wm.collada_import(filepath=src),
           "3ds": lambda: bpy.ops.import_scene.max3ds(filepath=src), "stl": lambda: bpy.ops.wm.stl_import(filepath=src),
           "ply": lambda: bpy.ops.wm.ply_import(filepath=src), "x3d": lambda: bpy.ops.import_scene.x3d(filepath=src),
           "abc": lambda: bpy.ops.wm.alembic_import(filepath=src)}
    if ext in ("usd", "usda", "usdc", "usdz"):
        bpy.ops.wm.usd_import(filepath=src)
    else:
        imp[ext]()
bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB", export_apply=True, export_animations=False)
'''


def import_model(mod_id: str, entry: dict, src: str) -> tuple[Path, str]:
    """Copy (or convert) a model into the board's folder. Returns (file, how)."""
    s = Path(src)
    if not s.is_file():
        raise ValueError(f"Model not found: {src}")
    if s.suffix.lower() == ".zip":                   # a model with its material and texture files
        import tempfile, zipfile
        tmp = Path(tempfile.mkdtemp(prefix="tesl-model-"))
        with zipfile.ZipFile(s) as z:
            for name in z.namelist():
                target = (tmp / name).resolve()
                if tmp.resolve() in target.parents and not name.endswith("/"):
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
        inside = [f for f in tmp.rglob("*") if f.suffix.lower() in NATIVE_MODELS + BLENDER_MODELS]
        if not inside:
            raise ValueError("the zip holds no model file (OBJ, GLB, glTF, FBX, BLEND, ...)")
        inside.sort(key=lambda f: (NATIVE_MODELS + BLENDER_MODELS).index(f.suffix.lower()))
        try:
            return import_model(mod_id, entry, str(inside[0]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    ext = s.suffix.lower()
    dest_dir = _files_dir(mod_id, entry) / "models" / slugify(s.stem)
    dest_dir.mkdir(parents=True, exist_ok=True)
    if ext == ".obj":
        text = s.read_text(encoding="utf-8", errors="replace")
        for lib in re.findall(r"(?m)^mtllib\s+(.+?)\s*$", text):
            mtl = s.parent / lib
            if mtl.is_file():
                mtext = mtl.read_text(encoding="utf-8", errors="replace")
                def take(m):
                    tex = (mtl.parent / m.group(2).strip())
                    if tex.is_file():
                        shutil.copyfile(tex, dest_dir / tex.name)
                        return m.group(1) + tex.name
                    return m.group(0)
                mtext = re.sub(r"(?im)^(\s*(?:map_\w+|bump|norm)\s+(?:-\S+\s+\S+\s+)*)(.+)$", take, mtext)
                (dest_dir / Path(lib).name).write_text(mtext, encoding="utf-8")
        text = re.sub(r"(?m)^mtllib\s+(.+?)\s*$", lambda m: "mtllib " + Path(m.group(1)).name, text)
        out = dest_dir / s.name
        out.write_text(text, encoding="utf-8")
        return out, "copied"
    if ext == ".glb":
        out = dest_dir / s.name
        shutil.copyfile(s, out)
        return out, "copied"
    if ext == ".gltf":
        doc = json.loads(s.read_text(encoding="utf-8"))
        for key in ("buffers", "images"):
            for item in doc.get(key, []):
                uri = item.get("uri", "")
                if uri and not uri.startswith("data:") and (s.parent / uri).is_file():
                    (dest_dir / Path(uri).parent).mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(s.parent / uri, dest_dir / uri)
        out = dest_dir / s.name
        shutil.copyfile(s, out)
        return out, "copied"
    if ext in BLENDER_MODELS:
        exe = blender()
        if not exe:
            raise ValueError(f"{ext} models need Blender (free, blender.org) to convert; or export OBJ or GLB from your 3D program")
        script = _workspace() / "blender-to-glb.py"
        script.parent.mkdir(parents=True, exist_ok=True)
        script.write_text(_BLENDER_SCRIPT, encoding="utf-8")
        out = dest_dir / (s.stem + ".glb")
        args = [exe, "-b"] + ([str(s)] if ext == ".blend" else []) + ["--python", str(script), "--", str(s), str(out)]
        r = subprocess.run(args, capture_output=True, text=True, timeout=600)
        if not out.is_file():
            raise ValueError("Blender could not convert the model: " + (r.stderr or r.stdout)[-600:])
        return out, "converted with Blender"
    raise ValueError(f"Unsupported model type {ext}: use OBJ, GLB/glTF, or {', '.join(BLENDER_MODELS)} (with Blender)")


def _place(base: str, x=None, y=None, pos=None, lift: float = 0.0) -> list[float]:
    if pos is not None:
        return _vec(pos)
    if x is None or y is None:
        x, y = 0.5, 0.5
    m = raw_map(base)
    w = unproject(m, float(x), float(y))
    w[1] = round(w[1] + lift, 3)
    return w


def _add(mod_id: str, board: str, item: dict) -> dict:
    manifest, e, p = _entry(mod_id, board)
    adds = e.setdefault("edits", {}).setdefault("add", [])
    name = item.get("name") or "object"
    slug = slugify(name) or "object"
    taken = {a.get("slug") for a in adds}
    base_slug, i = slug, 2
    while slug in taken:
        slug, i = f"{base_slug}-{i}", i + 1
    item = {"slug": slug, **_clean(item)}
    adds.append(item)
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "added": item, "total": len(adds)}


def _motion(motion: str | None, speed=None, amount=None) -> dict | None:
    if not motion:
        return None
    if motion not in MOTIONS:
        raise ValueError(f"motion must be one of {', '.join(MOTIONS)}")
    return _clean({"type": motion, "speed": speed, "amount": amount})


def add_model(mod_id: str, board: str, model: str, name: str | None = None, x=None, y=None, pos=None, rot=None, fit: float | None = 10.0,
              scale=None, texture: str | None = None, tint=None, glow=None, motion=None, speed=None, amount=None) -> dict:
    _, e, _p = _entry(mod_id, board)
    f, how = import_model(mod_id, e, model)
    tex = _rel(mod_id, _image(texture, f.parent / "texture")) if texture else None
    r = _add(mod_id, board, {"name": name or Path(model).stem, "model": _rel(mod_id, f), "texture": tex, "pos": _place(e["base"], x, y, pos),
                              "rot": _vec(rot), "fit": fit if scale is None else None, "scale": _vec(scale) if isinstance(scale, (list, str)) else scale,
                              "tint": _color(tint), "glow": _color(glow), "motion": _motion(motion, speed, amount)})
    r["model"] = how
    return r


def add_image(mod_id: str, board: str, image: str, name: str | None = None, x=None, y=None, pos=None, width: float = 12.0, rot=None,
              tint=None, glow=None, motion=None, speed=None, amount=None) -> dict:
    _, e, _p = _entry(mod_id, board)
    f = _image(image, _files_dir(mod_id, e) / "images" / slugify(name or Path(image).stem))
    return _add(mod_id, board, {"name": name or Path(image).stem, "image": _rel(mod_id, f), "width": float(width), "pos": _place(e["base"], x, y, pos, 0.05),
                                "rot": _vec(rot), "tint": _color(tint), "glow": _color(glow), "motion": _motion(motion, speed, amount)})


def add_light(mod_id: str, board: str, name: str | None = None, x=None, y=None, pos=None, height: float = 6.0, kind: str = "point",
              color="#ffcc88", intensity: float = 1.5, range_: float = 15.0, angle: float = 45.0, rot=None, motion=None, speed=None, amount=None) -> dict:
    _, e, _p = _entry(mod_id, board)
    return _add(mod_id, board, {"name": name or f"{kind} light", "light": {"type": kind, "color": _color(color), "intensity": intensity, "range": range_,
                                "angle": angle}, "pos": _place(e["base"], x, y, pos, height), "rot": _vec(rot) or ([90, 0, 0] if kind == "spot" else None),
                                "motion": _motion(motion, speed, amount)})


def add_effect(mod_id: str, board: str, preset: str, name: str | None = None, x=None, y=None, pos=None, height: float = 0.5, color=None,
               rate: float | None = None, size: float | None = None, speed: float | None = None, area: float | None = None, motion=None) -> dict:
    if preset not in PRESETS:
        raise ValueError(f"preset must be one of {', '.join(PRESETS)}")
    _, e, _p = _entry(mod_id, board)
    return _add(mod_id, board, {"name": name or preset, "particles": _clean({"preset": preset, "color": _color(color), "rate": rate, "size": size,
                                "speed": speed, "area": area}), "pos": _place(e["base"], x, y, pos, height + (12 if preset == "snow" else 0)),
                                "motion": _motion(motion)})


def move_added(mod_id: str, board: str, item: str, x=None, y=None, pos=None, rot=None, fit=None, scale=None, motion=None, speed=None, amount=None,
               tint=None, glow=None) -> dict:
    manifest, e, p = _entry(mod_id, board)
    a = next((a for a in e.get("edits", {}).get("add", []) if a.get("slug") == item or a.get("name") == item), None)
    if a is None:
        raise ValueError(f"no added '{item}' on {e['slug']}")
    if x is not None or pos is not None:
        lift = 0.05 if "image" in a else (6.0 if "light" in a else (0.5 if "particles" in a else 0.0))
        a["pos"] = _place(e["base"], x, y, pos, lift)
    for k, v in (("rot", _vec(rot)), ("fit", fit), ("scale", scale), ("tint", _color(tint)), ("glow", _color(glow))):
        if v is not None:
            a[k] = v
    if motion is not None:
        if motion == "":
            a.pop("motion", None)
        else:
            a["motion"] = _motion(motion, speed, amount)
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "added": a}


def remove_added(mod_id: str, board: str, item: str) -> dict:
    manifest, e, p = _entry(mod_id, board)
    adds = e.get("edits", {}).get("add", [])
    gone = [a for a in adds if a.get("slug") == item or a.get("name") == item]
    if not gone:
        raise ValueError(f"no added '{item}' on {e['slug']}")
    e["edits"]["add"] = [a for a in adds if a not in gone]
    _save(manifest, p)
    return {"mod": mod_id, "board": e["slug"], "removed": gone[0]["slug"]}


def edits(mod_id: str, board: str) -> dict:
    _, e, _p = _entry(mod_id, board)
    return {"mod": mod_id, "board": e["slug"], "base": e["base"], "edits": e.get("edits", {})}


def check(mod_id: str) -> list[str]:
    errors = []
    manifest, _ = _manifest(mod_id)
    root = mod_dir(mod_id) / "boards"
    for b in manifest["boards"]:
        ed = b.get("edits") or {}
        files = list((ed.get("textures") or {}).values())
        files += [f for o in (ed.get("objects") or {}).values() for f in (o.get("textures") or {}).values()]
        files += [a[k] for a in ed.get("add", []) for k in ("model", "image", "texture") if a.get(k)]
        for f in files:
            if not (root / f).is_file():
                errors.append(f"board {b['slug']}: missing {f}")
        if not b.get("image") and not ed:
            errors.append(f"board {b['slug']}: neither a table image nor edits")
    return errors
