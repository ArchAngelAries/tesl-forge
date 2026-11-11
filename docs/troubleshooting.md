# Troubleshooting — TESL Forge

| Problem | What to try |
|---|---|
| Setup says Python was not found | Install Python 3.10+ from python.org with "Add python.exe to PATH" ticked, then run **Set up TESL Forge.cmd** again. |
| Setup stops while installing | Check your internet connection and run **Set up TESL Forge.cmd** again (it repairs). |
| `tesl` says the game wasn't found | Check `tesl info`. Steam installs are found automatically; for other installs add the folder to `workspace\settings.json` in TESL Forge's folder as `{"game_dirs": ["<the game folder>"]}`, or set the `TESL_GAME_DIR` environment variable. |
| The app page doesn't open | Run `tesl serve` in a terminal and read the error. Another program may use port 8765: `tesl serve --port 8790`. |
| "Card data not found" / empty card library | TESL Forge reads the card data that ships with TESL: Everlasting (`BepInEx/plugins/TESLOffline/data/`). Install TESL: Everlasting first, or pass `--data`. |
| Audio upload refused or silent | Install [ffmpeg](https://ffmpeg.org/) and make sure `ffmpeg` runs from a terminal; WAV and OGG work without it. |
| FBX/.blend model refused | Install [Blender](https://www.blender.org/); OBJ and glTF work without it. |
| Enabling a mod is refused | The game would skip it (missing dependency, conflict, newer engine needed). The Load order page says why; fix it or use force. |
| My mod doesn't appear in game | Is it enabled? Have you opened TESL Forge since moving its folder (it records its location)? Restart the game (mods load at startup). Use **Play test**, or read `.offline-user-data\mod-report.json` and the logs in `.offline-user-data\logs` in the game folder. Is the game in offline mode? |
| Game previews or Play test don't start | Close the game first; they start TESL: Everlasting themselves. |
| A deck has a warning sign in game | It breaks deck rules; open it in TESL Forge (Edit) and run *Check*. |
| Art looks cropped wrong | Use a square image with the subject centred and headroom; check the hand and board previews. |
| Package install refused | Packages may only contain content files, no programs, no paths outside the mod, within size limits. Ask the author for a clean export. |
| I deleted something by mistake | Use undo (Overview > History), or look in `workspace/trash/`. |

Still stuck? Open an issue on this project's tracker with what you did, what you expected and any error text.
**Please don't contact the TESL-Reborn team about TESL Forge.**
