"""Builds the TESL Forge Windows app and its installer (maintainers only; players download the result).

  .venv\\Scripts\\python.exe tools/build_installer.py --out <folder> [--skip-installer]

1. PyInstaller bundles TESL Forge (Python, the web app, its data, pywebview and UnityPy) into
   <out>/forge-build/dist/TESL Forge/ with "TESL Forge.exe" (windowed, TESL Forge icon).
2. Inno Setup 6 (ISCC.exe; per-user install in %LOCALAPPDATA%/Programs/Inno Setup 6 or Program Files) makes
   <out>/TESL-Forge-<version>/TESL-Forge-Setup-<version>.exe.
Needs: pip install pyinstaller pywebview (in the .venv). Nothing is uploaded or published.
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COLLECT = ["UnityPy", "webview", "pythonnet", "clr_loader", "texture2ddecoder", "etcpak", "astc_encoder", "fmod_toolkit", "pyfmodex", "archspec"]


def version() -> str:
    return re.search(r'__version__ = "([^"]+)"', (ROOT / "tesl_suite" / "__init__.py").read_text(encoding="utf-8")).group(1)


def iscc() -> Path:
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        p = Path(base) / ("Programs/Inno Setup 6" if base == os.environ.get("LOCALAPPDATA", "") else "Inno Setup 6") / "ISCC.exe"
        if base and p.is_file():
            return p
    raise SystemExit("Inno Setup 6 (ISCC.exe) not found")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-installer", action="store_true")
    ap.add_argument("--names", default="", help="extra private words for the privacy scan (never written to a file)")
    a = ap.parse_args()
    v = version()
    out = Path(a.out).resolve()
    build = out / "forge-build"
    sep = os.pathsep
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--name", "TESL Forge",
            "--icon", str(ROOT / "tesl_suite" / "web" / "icon.ico"),
            "--distpath", str(build / "dist"), "--workpath", str(build / "work"), "--specpath", str(build),
            "--add-data", f"{ROOT / 'tesl_suite' / 'web'}{sep}tesl_suite/web",
            "--add-data", f"{ROOT / 'tesl_suite' / 'data'}{sep}tesl_suite/data",
            "--hidden-import", "tesl_suite.window", "--hidden-import", "tesl_suite.cli", "--collect-submodules", "tesl_suite",
            "--paths", str(ROOT)]
    for pkg in COLLECT:
        args += ["--collect-all", pkg]
    args.append(str(ROOT / "tools" / "forge_app.py"))
    subprocess.run(args, check=True, cwd=str(ROOT))
    app = build / "dist" / "TESL Forge"
    # FMOD (proprietary) must not ship: fmod_toolkit's code stays, its fmod.dll goes; the app fetches it on request
    # (tesl_suite/audio_support.py). The build fails if any copy is left.
    shutil.rmtree(app / "_internal" / "fmod_toolkit" / "libfmod", ignore_errors=True)
    left = [p for p in app.rglob("*") if p.name.lower().startswith("fmod") and p.suffix.lower() in (".dll", ".so", ".dylib")]
    if left:
        raise SystemExit("FMOD library left in the app: " + ", ".join(str(p) for p in left))
    for name in ("LICENSE", "NOTICE.md", "DISCLAIMER.md", "CREDITS.md", "README.md", "CHANGELOG.md"):
        shutil.copyfile(ROOT / name, app / name)
    print("app:", app)
    if a.skip_installer:
        return 0
    dest = out / f"TESL-Forge-{v}"
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(iscc()), f"/DAppVersion={v}", f"/DSourceDir={app}", f"/DOutDir={dest}",
                    str(ROOT / "tools" / "installer" / "tesl-forge.iss")], check=True)
    setup = dest / f"TESL-Forge-Setup-{v}.exe"
    print("installer:", setup)
    # checksums of every download in the release folder (the zips from package_release.py and this installer)
    import hashlib
    files = sorted(p for p in dest.iterdir() if p.is_file() and p.suffix.lower() in (".zip", ".exe"))
    (dest / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n" for p in files), encoding="utf-8")
    return privacy(app, a.names)


def privacy(app: Path, names: str) -> int:
    """Scan the installed files. The bundled Python and libraries carry their authors' public contacts and example paths;
    only findings about this computer or the owner fail the build (user folder, local game drives, --names words)."""
    out = subprocess.run([sys.executable, str(ROOT / "tools" / "privacy_scan.py"), str(app)] + (["--names", names] if names else []),
                         capture_output=True, text=True, encoding="utf-8", errors="replace").stdout.splitlines()
    user = os.environ.get("USERNAME", "").lower()
    words = [w.strip().lower() for w in names.split(",") if w.strip()]
    bad = [l for l in out if ": " in l and not l.startswith("privacy scan:")
           and (("windows user folder" in l.lower() and user and f"users/{user}" in l.lower().replace("\\", "/"))
                or "local drive path" in l.lower() or any(w in l.lower() for w in words))]
    print(f"privacy: {len(out) - 1} third-party finding(s) ignored, {len(bad)} about this computer or the owner")
    for l in bad:
        print("  " + l)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
