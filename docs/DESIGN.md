# TESL Forge — design

Names (owner, 2026-11-04): the modding suite is **TESL Forge**; the offline revival mod is **TESL: Everlasting**
("The Elder Scrolls: Legends — Everlasting"). Folder names (TESL-Modding-Suite, offline-engine) are unchanged.

Status (1.0.0, 2026-11-11): every milestone below is done and shipped in TESL Forge 1.0.0. This page keeps the design
reasoning; the user guides are in `docs/guides`.

## Goals
- A separate, fully functional program with a modern UI, installed in its **own folder next to** the game folder of the
  version being modded (`steamapps/common/TESL-Modding-Suite`). It never writes into a game folder.
- Every supported workflow works **without code**: asset extraction (textures, models, audio), texture/image replacement for
  remastering, avatars and profile pictures, new cards, new decks, new rules for new cards, new game modes, new emotes (the AI
  opponent can use them too), validation, packaging, enable/disable, conflict reports, and testing against the AI.
- **Agent-operable:** everything the UI does is a CLI command and a local API call with JSON in and out, so Claude Code or Codex
  can, for example, generate card art with an image service, then create the cards, their rules and a deck through the suite.

## Architecture
```
TESL-Modding-Suite/
  tesl.cmd                  launcher (project-local Python environment)
  tesl_suite/               core library: one implementation shared by CLI, API and UI
    game.py                 locate installs (Steam, Bethesda), version and data paths
    assets.py               bundle index (from Unity manifests), extraction (UnityPy)
    cards.py                card catalog in the original card JSON format (data/original-rules)
    cli.py                  `tesl <area> <command> [--json]`
  docs/                     design, agent guide
  workspace/                per-user cache, exports, projects (git-ignored)
  mods/                     authored mod packages
```
- **Core first.** Each capability is a function in `tesl_suite`, exposed by the CLI (`--json` on every command, stable result
  shapes, non-zero exit on failure). The local HTTP API and an MCP server wrap the same functions; the web UI (a single-page
  app with no build step, served locally and shown in Forge's own window) calls the API.
- **Reading game data:** Unity 2017.4 asset bundles via UnityPy (MIT). The bundle `.manifest` files list every asset path,
  so the index is built from manifests without opening 7.6 GB of bundles; extraction opens only the bundles it needs.
- **Card data and rules:** the original card JSON (the game's FullSerializer form, including the rule graphs the shipped
  binary strips) is the catalog and the authoring format. New cards are written in exactly that shape, so the offline engine
  loads them the same way it loads Bethesda's cards (`OriginalGraphRules`). The UI offers templates taken from existing cards
  ("summon a token", "deal N damage", ...) and a validator built from the 219 rule object types in the original data.
- **Testing:** the suite runs the offline engine's hidden headless harness (smoke + real paid play + a match against the AI)
  on a mod's cards and reports the results.

## Mod packages (milestone 3)
A mod is a folder (or `.teslmod` zip) with `mod.json` (id, name, version, author, game version, dependencies) and optional
`cards/`, `decks/`, `art/`, `avatars/`, `emotes/`, `modes/`, `replace/` (asset overrides keyed by bundle asset path). New
content gets unique ids derived from the mod id, so mods never collide with each other or with original ids. The suite writes
the enabled set to `deploy/active-mods.json`; the offline engine plugin (BepInEx, outside the game's own files) reads it at
startup, injects cards/decks/avatars/emotes into the loaded configuration and swaps textures at load time. Disabling a mod
restores the original appearance and content; original files are never modified.

## Milestones
1. **Asset index and extraction:** `tesl info`, `tesl assets index|list|export`, `tesl cards list`,
   `tesl assets export-card-art` with readable names, a manifest (source bundle and path, card id and name, dimensions, alpha,
   full art vs. crop) and checks.
2. Local API + MCP server; agent guide. Done: local HTTP API (`tesl serve`, tesl_suite/api.py) and the MCP server.
3. Mod packages, deploy/enable/disable, engine-side loader for new cards and decks (with art import and cropping).
4. Texture/model replacement (remastering), avatars and profile pictures, emotes (player and AI). Done so far: image
   replacement for path-loaded images (`tesl replace`, engine serves them at the original size); new avatar choices
   (`tesl avatar`, own picker pages, borrowed voices); emote lines per avatar (`tesl avatar emote`, text + voice) and
   AI opponent emotes with temperaments; card backs (`tesl cardback`, unlimited, free or sold for gold); boards (`tesl board`, re-skins of the five playmats).
   Soundtracks (`tesl music`): tracks play in chosen moments (menus, store, story, match, victory/defeat) or on boards (a mod board's track wins over its base's); replace or rotation; converted to OGG; follow the game's music volume and mute.
   Sounds (`tesl sound`): a labelled catalog of the game's ~5,100 sounds; replace any of them; mod cards get their own voice lines. Extra emotes (`tesl emote`): beyond the eight, paged with "More..." in the match emote panel, per avatar or for every avatar; "like" makes them AI variants.
   Asset catalog (`tesl assets find`, the app's Asset browser): every asset labelled from the game configuration (data/asset-labels.tsv, exported by the engine audit), the card data, the sound catalog and folder rules; says how a mod can change each one. Remaster art also replaces non-card images picked from it.
   Board editor (`tesl board map/edit/add/move/take`, app Boards > Edit board): every prop, texture, light, particle effect and animation of the five game boards is editable; new 3D models (runtime OBJ/glTF loader in the engine, other formats converted with Blender), images (shape cut into the mesh: this build has no alpha variants of the lit shader), lights, particle presets and motions; placed by clicking the board picture (camera projection from the engine's board maps, data/boards/*.json). Table painting optional.
   Game modes (`tesl mode`, app Game modes): custom matches vs the AI played from the Practice screen: 1-2 lanes of any implemented lane type (size 2/4/6), per-side health, magicka, runes, deck (own, mod deck, random), starting cards in hand/lanes/supports/deck, first player, AI difficulty and name, turn rules (extra draws, extra magicka, damage/heal per turn, random reinforcements, shifting lanes), board, music context Mode:<mod>/<mode>, gold for a win.
   Stories (`tesl story`, app Stories, MCP `story_options`/`new_story`/`get_story`/`save_story`/`add_story_file`): campaigns built into the game's own story data and played from Play > Stories: acts, chapters with a map (own picture or any installed story map), events placed on the map (location discs) with dialogue lines (speaker, portrait, optional voice file, up to 3 choices giving a card or gold), battles with the game-mode setup plus opponent name/portrait, briefing and victory lines, several battles per event picked by the intro choice, events/lines unlocked by earlier events or choices (branching), rewards (gold, cards, packs, XP, gems). Limits: the episode screen shows as many acts and episodes per act as the template's layout has (DBH: 3 acts).
5. Rule authoring UI and validator; headless test runs; game modes. Done: rule editor (keywords + abilities from any card
   with editable amounts and card references; `tesl card abilities`, app Cards page, MCP `card_abilities`/`new_card`).
6. Web UI and packaged installer. Done: the web app (tesl_suite/web, no build step) served by `tesl serve`, the native window
   and the Windows installer (`TESL-Forge-Setup-<version>.exe`).
