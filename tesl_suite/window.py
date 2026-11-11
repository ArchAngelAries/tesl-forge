"""TESL Forge in its own window (the app, not a browser tab).

The local API runs on a free 127.0.0.1 port in this process and the app is shown in a native window through pywebview
(Microsoft Edge WebView2, part of Windows 10/11). The window and taskbar show the TESL Forge icon. Closing the window
stops TESL Forge. If no game folder is found, the window asks for it once and remembers it (workspace/settings.json).

Run: `tesl window`, "TESL Forge.exe" (installed), or "Open TESL Forge.cmd".
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import time
from pathlib import Path

ICON = Path(__file__).parent / "web" / "icon.ico"
APP_ID = "ArchAngelAries.TESLForge"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _taskbar_identity() -> None:
    """Own taskbar entry and icon (not Python's)."""
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except Exception:
            pass


def remember_game_dir(path: str) -> None:
    from .game import workspace
    f = workspace() / "settings.json"
    try:
        settings = json.loads(f.read_text(encoding="utf-8")) if f.is_file() else {}
    except (OSError, ValueError):
        settings = {}
    dirs = [d for d in settings.get("game_dirs", []) if isinstance(d, str) and d != path]
    settings["game_dirs"] = [path] + dirs
    f.write_text(json.dumps(settings, indent=1), encoding="utf-8")


PICK_TITLE = "TESL Forge: choose your The Elder Scrolls Legends game folder"


def _libraries() -> list:
    try:
        from .game import _steam_libraries
        return _steam_libraries()
    except Exception:
        return []


def _title_folder_dialog(title: str) -> None:
    """pywebview's Windows folder dialog has a title but pywebview never sets it: give it ours."""
    try:
        from webview.platforms import winforms
        show = winforms.OpenFolderDialog.show.__func__
        if getattr(show, "_tesl_titled", False):
            return
        def titled(cls, parent=None, initialDirectory=None, allow_multiple=False, title=None):
            return show(cls, parent, initialDirectory, allow_multiple, title or PICK_TITLE)
        titled._tesl_titled = True
        winforms.OpenFolderDialog.show = classmethod(titled)
    except Exception:
        pass


def _ask_for_game(window) -> None:
    """Runs once the window is up: if no game folder is found, ask for it."""
    import webview
    from . import api
    from .game import find_install, DATA_FOLDER
    try:
        find_install(api._state.get("game_path"))
        return
    except FileNotFoundError:
        pass
    _title_folder_dialog(PICK_TITLE)
    window.evaluate_js("typeof toast === 'function' && toast('Choose your The Elder Scrolls Legends game folder (the one with \"The Elder Scrolls Legends.exe\"), for example ...\\\\steamapps\\\\common\\\\The Elder Scrolls Legends.')")
    start = next((str(lib / "steamapps" / "common") for lib in _libraries() if (lib / "steamapps" / "common").is_dir()), str(Path.home()))
    while True:
        picked = window.create_file_dialog(webview.FileDialog.FOLDER, directory=start)
        if not picked:
            window.evaluate_js("typeof toast === 'function' && toast('TESL Forge needs the game: choose The Elder Scrolls Legends folder (Settings, or restart TESL Forge).', true)")
            return
        root = Path(picked[0] if isinstance(picked, (list, tuple)) else picked)
        if (root / DATA_FOLDER).is_dir():
            remember_game_dir(str(root))
            api._state.pop("game", None)
            window.evaluate_js("location.reload()")
            return
        window.evaluate_js("typeof toast === 'function' && toast('That folder has no The Elder Scrolls Legends_Data folder. Choose the game folder.', true)")


def main(game_path: str | None = None, debug: bool = False) -> int:
    import webview
    from . import api
    from .game import first_run_setup
    _taskbar_identity()
    first_run_setup()
    port = _free_port()
    threading.Thread(target=api.serve, args=(port, False, game_path), daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    for _ in range(100):   # wait until the local API answers
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    from .game import workspace
    try:   # where the running app answers (for the CLI, agents and tests); removed when the window closes
        (workspace() / "app-url.txt").write_text(url, encoding="utf-8")
    except OSError:
        pass
    window = webview.create_window("TESL Forge", url, width=1440, height=920, min_size=(960, 640), background_color="#15171c")
    try:
        webview.start(_ask_for_game, window, icon=str(ICON), debug=debug, private_mode=False, storage_path=str(workspace() / "webview"))
    finally:
        try:
            (workspace() / "app-url.txt").unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
