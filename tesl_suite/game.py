"""Locate TESL installs next to the suite and describe their data folders."""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, asdict
from pathlib import Path

GAME_FOLDER = "The Elder Scrolls Legends"
DATA_FOLDER = "The Elder Scrolls Legends_Data"
CODE_ROOT = Path(__file__).resolve().parent.parent   # the program (a checkout or zip, or the installed app's bundle)
FROZEN = bool(getattr(sys, "frozen", False))          # the installed "TESL Forge.exe"


def _documents() -> Path:
    """The user's Documents folder (also when it is moved, e.g. to OneDrive)."""
    if sys.platform == "win32":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except Exception:
            pass
    return Path.home() / "Documents"


# Where mods, the workspace and the enabled-mod list live. A checkout or zip keeps them in its own folder; the installed
# app keeps them in Documents/TESL Forge, so updating or uninstalling the program never touches anyone's mods.
# TESL_FORGE_HOME overrides both.
SUITE_ROOT = Path(os.environ["TESL_FORGE_HOME"]) if os.environ.get("TESL_FORGE_HOME") else (_documents() / "TESL Forge" if FROZEN else CODE_ROOT)


def first_run_setup() -> None:
    """Installed app: create the data folder and copy the bundled sample mods in once (never over a mod that exists)."""
    import shutil
    (SUITE_ROOT / "mods").mkdir(parents=True, exist_ok=True)
    (SUITE_ROOT / "deploy").mkdir(exist_ok=True)
    bundled = CODE_ROOT / "bundled-mods"
    if bundled.is_dir():
        for m in bundled.iterdir():
            if m.is_dir() and not (SUITE_ROOT / "mods" / m.name).exists():
                shutil.copytree(m, SUITE_ROOT / "mods" / m.name)


def _steam_libraries() -> list[Path]:
    """Steam library folders (registry SteamPath + steamapps/libraryfolders.vdf)."""
    roots: list[Path] = []
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                roots.append(Path(winreg.QueryValueEx(k, "SteamPath")[0]))
        except OSError:
            pass
    from . import settings
    roots += settings.steam_roots()
    libs: list[Path] = []
    for r in roots:
        vdf = r / "steamapps" / "libraryfolders.vdf"
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        libs.append(r)
        for line in text.splitlines():
            parts = line.strip().split('"')
            if len(parts) >= 4 and parts[1] == "path":
                libs.append(Path(parts[3].replace("\\\\", "\\")))
    return libs


@dataclass
class GameInstall:
    root: str
    data: str
    streaming_assets: str
    managed: str
    bundles: int
    original_rules: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _candidates() -> list[Path]:
    env = os.environ.get("TESL_GAME_DIR")
    found = []
    if env:
        found.append(Path(env))
    # The suite lives next to the game folder of the version it mods.
    found.append(CODE_ROOT.parent / GAME_FOLDER)
    # More install folders (a second copy, a Bethesda.net install): "game_dirs" in workspace/settings.json (tesl settings),
    # kept on this computer only.
    from . import settings
    found += [Path(d) for d in settings.get("game_dirs")]
    # Steam libraries (the installed app lives elsewhere)
    found += [lib / "steamapps" / "common" / GAME_FOLDER for lib in _steam_libraries()]
    return found


def find_install(explicit: str | None = None) -> GameInstall:
    paths = [Path(explicit)] if explicit else _candidates()
    for root in paths:
        data = root / DATA_FOLDER
        if data.is_dir() and (data / "StreamingAssets").is_dir():
            sa = data / "StreamingAssets"
            bundles = sum(1 for p in sa.rglob("*.manifest"))
            # the engine's card rules: development checkout, else the installed TESL: Everlasting plugin
            rules = root / ".analysis" / "offline-engine" / "data" / "original-rules" / "card-rule-graphs.jsonl.gz"
            if not rules.is_file():
                rules = root / "BepInEx" / "plugins" / "TESLOffline" / "data" / "original-rules" / "card-rule-graphs.jsonl.gz"
            return GameInstall(str(root), str(data), str(sa), str(data / "Managed"), bundles,
                               str(rules) if rules.is_file() else None)
    raise FileNotFoundError("No TESL install found. Set TESL_GAME_DIR or pass --game.")


def workspace() -> Path:
    path = SUITE_ROOT / "workspace"
    path.mkdir(exist_ok=True)
    return path


def assert_outside_game(path: Path, game: GameInstall) -> None:
    """The suite never writes into a game folder."""
    target = path.resolve()
    root = Path(game.root).resolve()
    if target == root or root in target.parents:
        raise PermissionError(f"Refusing to write inside the game folder: {target}")


def write_location_pointer() -> None:
    """Tell TESL: Everlasting where TESL Forge is (its enabled-mod list), wherever Forge is installed: a one-line file in
    %APPDATA%/TESL Forge/location.txt, outside the game folder."""
    try:
        base = Path(os.environ.get("APPDATA") or Path.home())
        target = base / "TESL Forge" / "location.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_text(encoding="utf-8").strip() != str(SUITE_ROOT):
            target.write_text(str(SUITE_ROOT), encoding="utf-8")
    except OSError:
        pass
