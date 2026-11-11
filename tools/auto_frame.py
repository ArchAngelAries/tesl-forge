"""Suggests (and with --apply writes) an art frame for every card of the given mods, so heads aren't cut off.

  python tools/auto_frame.py --mod tesl-followers [--mod ...] [--out frames.tsv] [--apply] [--sample-mod zz-frame-test --sample 16]

Needs OpenCV (pip install opencv-python) for the face finder; maintainers only, players never run this.
A card whose art has a face gets the smallest step back (scale >= 1.1) that shows the whole head below the name plate;
art with no face gets a gentle step back (scale 1.2). The art files are never changed. --sample-mod writes a throwaway
mod with the suggested frames of the cards that change most, so they can be checked with `tesl preview` first.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tesl_suite import framing  # noqa: E402
from tesl_suite.mods import mod_dir  # noqa: E402

CASCADES = [cv2.data.haarcascades + n for n in ("haarcascade_frontalface_default.xml", "haarcascade_frontalface_alt2.xml",
                                                "haarcascade_profileface.xml")]


def head_box(png: Path):
    img = cv2.imread(str(png))
    if img is None:
        return None
    g = cv2.equalizeHist(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    h, w = g.shape
    faces = []
    for path in CASCADES:
        det = cv2.CascadeClassifier(path)
        for flip in (False, True):
            src = cv2.flip(g, 1) if flip else g
            for (x, y, fw, fh) in det.detectMultiScale(src, 1.08, 5, minSize=(int(w * 0.05), int(h * 0.05))):
                if flip:
                    x = w - x - fw
                faces.append((x, y, fw, fh))
    if not faces:
        return None
    # the biggest face is the subject; ties go to the higher one
    x, y, fw, fh = max(faces, key=lambda f: (f[2] * f[3], -f[1]))
    face = (x / w, y / h, (x + fw) / w, (y + fh) / h)
    head = (max(0.0, (x - 0.15 * fw) / w), max(0.0, (y - 0.25 * fh) / h),      # a little hair above the face
            min(1.0, (x + 1.15 * fw) / w), min(1.0, (y + 1.15 * fh) / h))     # and the chin below
    return face, head


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mod", action="append", required=True)
    ap.add_argument("--out")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--top", action="store_true", help="every card: slight step back, window at the top of the picture (no face finding)")
    ap.add_argument("--sample-mod")
    ap.add_argument("--sample", type=int, default=16)
    ap.add_argument("--only", action="append", help="sample exactly these card slugs")
    a = ap.parse_args()
    rows = []
    for mod_id in a.mod:
        for f in sorted((mod_dir(mod_id) / "cards").glob("*.json")):
            c = json.loads(f.read_text(encoding="utf-8"))
            slug = c["ResourceId"]["UniqueName"]
            art = mod_dir(mod_id) / "art" / f"{slug}.png"
            if not art.is_file():
                continue
            found = head_box(art)
            s0, x0, y0 = float(c.get("ImageScale") or 1), float(c.get("ImageOffsetX") or 0), float(c.get("ImageOffsetY") or 0)
            box = found[1] if found else None
            cropped = bool(found) and framing.head_cut(found[0], s0, x0, y0)
            if a.top:
                new = framing.top_frame()
            elif cropped:
                new = framing.fit(box)
            elif s0 < 1.0:                       # zoomed in by a template's value: back to the whole frame, same aim
                new = {"scale": 1.0, "x": x0, "y": y0}
            else:
                new = {"scale": s0, "x": x0, "y": y0}
            rows.append({"mod": mod_id, "card": slug, "name": c.get("Name"), "face": bool(box), "head_cut_now": cropped,
                         "before": (s0, x0, y0), "after": (new["scale"], new["x"], new["y"]),
                         "change": abs(new["scale"] - s0) + abs(new["x"] - x0) + abs(new["y"] - y0), "box": box})
    if a.out:
        with open(a.out, "w", encoding="utf-8") as o:
            o.write("mod\tcard\tname\tface\thead_cut_now\tbefore\tafter\n")
            for r in rows:
                o.write(f"{r['mod']}\t{r['card']}\t{r['name']}\t{r['face']}\t{r['head_cut_now']}\t{r['before']}\t{r['after']}\n")
    faces = sum(r["face"] for r in rows)
    cut = sum(r["head_cut_now"] for r in rows)
    changed = sum(r["change"] > 0.001 for r in rows)
    print(f"{len(rows)} cards: {faces} with a face found, {cut} with the face cut off now, {changed} frames would change")
    if a.sample_mod:
        test = mod_dir(a.sample_mod)
        if test.exists():
            shutil.rmtree(test)
        (test / "cards").mkdir(parents=True); (test / "art").mkdir()
        first = mod_dir(rows[0]["mod"]) / "mod.json"
        m = json.loads(first.read_text(encoding="utf-8")); m["id"] = a.sample_mod; m["name"] = "Frame check"
        m["dependencies"] = []; m["conflicts"] = []
        (test / "mod.json").write_text(json.dumps(m, indent=1), encoding="utf-8")
        names = set(a.only or [])
        pick = [r for r in rows if r["card"] in names] if names else sorted([r for r in rows if r["head_cut_now"]], key=lambda r: -r["change"])[: a.sample // 2]
        if not names:
            pick += sorted([r for r in rows if not r["head_cut_now"] and r["change"] > 0], key=lambda r: -r["change"])[: a.sample - len(pick)]
        for i, r in enumerate(pick):
            src = json.loads((mod_dir(r["mod"]) / "cards" / f"{r['card']}.json").read_text(encoding="utf-8"))
            for j, (tag, frame) in enumerate((("before", r["before"]), ("after", r["after"]))):
                c = json.loads(json.dumps(src))
                slug = f"f{i:02d}-{j}-{r['card']}"[:60]
                c["ResourceId"]["UniqueName"] = slug; c["ResourceId"]["Id"] = 900002000 + i * 2 + j
                c["Name"] = f"{tag}: {r['name']}"[:40]
                c.pop("NameKey", None); c.pop("DescriptionKey", None); c.pop("audio", None); c.pop("Image", None)
                for k in list(c):
                    if k.endswith("CardVO") and str(c[k] or "").startswith("mod_"):
                        c[k] = None
                c["ImageScale"], c["ImageOffsetX"], c["ImageOffsetY"] = frame
                (test / "cards" / f"{slug}.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
                shutil.copy(mod_dir(r["mod"]) / "art" / f"{r['card']}.png", test / "art" / f"{slug}.png")
        print(f"sample mod {a.sample_mod}: {len(pick)} cards before/after")
    if a.apply:
        for r in rows:
            framing.set_frame(r["mod"], r["card"], *r["after"])
        print(f"applied {len(rows)} frames")
    return 0


if __name__ == "__main__":
    sys.exit(main())
