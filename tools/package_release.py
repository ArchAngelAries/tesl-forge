"""Builds the TESL Forge release downloads from an explicit list of files, then privacy-scans them.

  .venv\\Scripts\\python.exe tools/package_release.py --out <folder> [--names "private,words"]

Makes, in <folder>/TESL-Forge-<version>/:
  TESL-Forge-<version>.zip             the app (Python source, web app, docs, launchers, setup); no mods, no workspace
  TESL-Forge-Sample-Mod-<version>.zip  the sample mod as an installable mod package (kept apart: Forge ships no content)
  SHA256SUMS.txt
Nothing is uploaded or published. --names: extra private words to search for; they are never written into any file.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOP = ["README.md", "CHANGELOG.md", "LICENSE", "NOTICE.md", "DISCLAIMER.md", "CREDITS.md", "AGENTS.md", "requirements.txt",
       "Open TESL Forge.cmd", "Set up TESL Forge.cmd", "tesl.cmd"]
TREES = ["tesl_suite", "tests", "docs", "tools"]
SKIP = re.compile(r"(^|/)(__pycache__|\.pytest_cache)(/|$)|\.pyc$|^docs/(outreach|nexus)(/|$)|^docs/nexus-page\.md$|^docs/PUBLIC-RELEASE-LAYOUT\.md$")
MODS_README = ("Mods live here, one folder each (made with TESL Forge, or installed from a .zip on the Load order page).\r\n"
               "TESL Forge itself ships no mods; the sample mod is a separate download.\r\n")


def version() -> str:
    m = re.search(r'__version__ = "([^"]+)"', (ROOT / "tesl_suite" / "__init__.py").read_text(encoding="utf-8"))
    return m.group(1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", default="")
    a = ap.parse_args()
    v = version()
    out = Path(a.out) / f"TESL-Forge-{v}"
    out.mkdir(parents=True, exist_ok=True)
    app = out / f"TESL-Forge-{v}.zip"
    n = 0
    with zipfile.ZipFile(app, "w", zipfile.ZIP_DEFLATED) as z:
        for name in TOP:
            if not (ROOT / name).is_file():
                raise SystemExit(f"missing: {name}")
            z.write(ROOT / name, f"TESL Forge/{name}"); n += 1
        for tree in TREES:
            for p in sorted((ROOT / tree).rglob("*")):
                rel = p.relative_to(ROOT).as_posix()
                if p.is_file() and not SKIP.search(rel):
                    z.write(p, f"TESL Forge/{rel}"); n += 1
        z.writestr("TESL Forge/mods/README.txt", MODS_README); n += 1
    sys.path.insert(0, str(ROOT))
    from tesl_suite import packages
    sample = out / f"TESL-Forge-Sample-Mod-{v}.zip"
    packages.export_mod("sample-skyrim", str(sample))
    made = [app, sample]
    (out / "SHA256SUMS.txt").write_text("\n".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}" for p in made) + "\n", encoding="utf-8")
    for p in made:
        print(f"{p.name}: {p.stat().st_size // 1024} KB")
    print(f"app files: {n}")
    sys.path.insert(0, str(Path(__file__).parent))
    import privacy_scan
    return privacy_scan.main([str(p) for p in made] + (["--names", a.names] if a.names else []))


if __name__ == "__main__":
    sys.exit(main())
