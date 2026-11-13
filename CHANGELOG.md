# Changelog

## 1.0.1 — fixes

- **Decks with comma names:** card names that contain a comma ("Miraak, Dragonborn", "Let Me Guess, Someone Stole Your
  Sweetroll") now work in deck lists from the command line, the local API and the MCP tools. Separate cards with `;` or
  new lines, or hand over a real list (a JSON array of "Name x3" texts or `{name, count}` objects). Old comma-separated
  lists still work for names without commas, and a list with a mistyped card now says which card was not found.
- **Many sounds at once:** the Sounds page has a "Replace many sounds at once" drop zone. Drop several audio files; each
  is matched to a game sound by its file name (or to one of your cards' voice lines, "<card> Play.wav"), and every file
  gets its own result line. The single-sound drop box also takes several files now (they become takes picked at random).
  Also `tesl bulk sounds` and the `bulk_import` MCP tool (kind `sounds`).
- **Settings for this computer:** nothing machine-specific is built into the program any more. A new Settings page (and
  `tesl settings`) keeps extra game folders, extra Steam folders and the Blender and ffmpeg paths in
  `workspace/settings.json`; leave a path empty and TESL Forge finds the program itself (PATH, Program Files, Steam).
- **Faster:** validating a big mod went from about 16 seconds to under a second; mod fingerprints, mod card files, the
  asset index and asset-path lookups are remembered until the files change (by size and modification time).
- **Faces stay visible in small views:** new cards get deck-list, history and hover framing centred on the face height
  of generated art, with the deck-list art shifted right so faces clear the card name (measured with the game's own
  deck-list row).

## 1.0.0 — first public release

TESL Forge: make mods for TESL: Everlasting without writing code.

- **Windows installer and its own window:** `TESL-Forge-Setup-1.0.0.exe` installs for your user only (no administrator
  prompt, no Python needed). Your mods live in `Documents\TESL Forge` and survive updates and uninstalling. The zip
  version (with the `tesl` command line) is still available.
- **Add or replace almost anything:** cards (any number of abilities taken from any game card, with their numbers
  changed, plus keywords and your own cost, power and health), decks, avatars, emotes, card backs, boards (new table
  art and 3D edits), music, sounds and voices, game modes, stories, AI opponents, card packs, translations and remastered
  game art.
- **Game previews:** cards, card backs, deck banners and boards drawn by the game itself.
- **Stories can reuse the game's own story art:** tiles, banners, act and chapter pictures, maps, discs and portraits.
- **Safe by design:** never changes game files; undo and history, drafts, problems linked to items, load order and
  compatibility checks, search across mods, and packages ready to share.
- **Game audio:** listening to the game's own sounds uses FMOD, which TESL Forge can't ship; the app downloads it once on
  request (Sounds page, "Get game-audio support").
