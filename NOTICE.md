# Third-party notices — TESL Forge

TESL Forge is our own code (see `LICENSE`). It uses the open-source components below, installed into its own Python
environment (`.venv`). Each keeps its own license.

| Component | Version | License | Use |
|---|---|---|---|
| [Python](https://www.python.org/) | 3.12 | PSF License | Runtime |
| [UnityPy](https://github.com/K0lb3/UnityPy) | 1.24.2 | MIT | Reads the game's Unity asset bundles |
| [Pillow](https://python-pillow.org/) | 13.0 | MIT-CMU (HPND) | Image cropping, resizing, previews |
| [texture2ddecoder](https://github.com/K0lb3/texture2ddecoder) | 1.0.6 | MIT | Texture decoding (UnityPy dependency) |
| [etcpak](https://github.com/K0lb3/etcpak) | 0.9.15 | MIT | Texture compression (UnityPy dependency) |
| [astc-encoder-py](https://github.com/K0lb3/astc-encoder-py) | 0.1.12 | MIT (bundles ARM astc-encoder, Apache-2.0) | Texture formats (UnityPy dependency) |
| [fmod_toolkit](https://github.com/K0lb3/fmod_toolkit) | 0.1.3 | MIT; **bundles the FMOD Engine library (`fmod.dll`), which is proprietary** (Firelight Technologies) | Decoding game audio (UnityPy dependency) |
| [pyfmodex](https://github.com/tyrylu/pyfmodex) | 0.7.2 | MIT | FMOD bindings |
| [lz4](https://github.com/python-lz4/python-lz4) | 4.4.5 | BSD-3-Clause | Bundle decompression |
| [brotli](https://github.com/google/brotli) | 1.2.1 | MIT | Decompression |
| [fsspec](https://github.com/fsspec/filesystem_spec) | 2026.9.0 | BSD-3-Clause | File access (UnityPy dependency) |
| [attrs](https://github.com/python-attrs/attrs) | 26.1.0 | MIT | UnityPy dependency |
| [archspec](https://github.com/archspec/archspec) | 0.2.7 | Apache-2.0 OR MIT | UnityPy dependency |

**Distribution note:** TESL Forge's own repository contains none of these; `pip` downloads them from PyPI on the user's
computer. A future installer may bundle the open-source ones (MIT, BSD, Apache, PSF) if it includes their license texts.

**FMOD must not be bundled.** FMOD's free non-commercial licence allows the FMOD Engine only "integrated and redistributed
in a software application (Product)", says it must "not [be] distributed as part of a game engine or tool set", rules out
"any form of monetisation, sponsorship or promotion", and requires a credit line naming FMOD Studio and Firelight
Technologies Pty Ltd. TESL Forge is a tool set and has donation links, so we don't ship `fmod.dll`. Instead, on the
user's own computer: the zip version's setup step lets `pip` fetch `fmod_toolkit` from PyPI, and the installed app (which
ships fmod_toolkit's code without its `fmod.dll`; the build fails if one is left) offers "Get game-audio support", a
one-time download of the same package from PyPI, checked against PyPI's SHA-256, keeping only `fmod.dll` in
`Documents\TESL Forge\runtime\fmod`. It is used only to decode the game's own audio. Without it, everything except
listening to/exporting original game sounds works.
Credit: audio decoding uses FMOD Studio by Firelight Technologies Pty Ltd (through fmod_toolkit), when installed.
Before an installer ships, re-read FMOD's current terms at https://www.fmod.com/legal (or ask sales@fmod.com).

## Optional external programs (not included, called if installed)

| Program | License | Use |
|---|---|---|
| [ffmpeg](https://ffmpeg.org/) | LGPL-2.1+ / GPL-2+ depending on build | Converting audio files |
| [Blender](https://www.blender.org/) | GPL-2.0+ | Importing FBX, .blend, DAE, 3DS, STL, PLY, USD models for boards |

## The original game

*The Elder Scrolls: Legends* and all its content (card data, art, audio, text, models) belong to Bethesda Softworks /
ZeniMax Media. TESL Forge reads them from the user's own installation and contains none of them. Screenshots in
`docs/screenshots/` show original card art, which belongs to its owners.

## Icon

The TESL Forge icon (`tesl_suite/web/icon.*`) is original work made for this project (anvil, flame and card shapes), under
the same license as TESL Forge. It uses no Bethesda or *The Elder Scrolls* logos or assets.
