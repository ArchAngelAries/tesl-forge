# TESL Forge command line

Every feature of the app is a `tesl` command. Run them from the TESL Forge folder (`tesl.cmd`, or
`.venv\Scripts\python -X utf8 -m tesl_suite.cli`). Add `--json` to any command for a single JSON result on stdout; failures
exit non-zero with `{"error": "..."}`. The full command table is in [AGENTS.md](../AGENTS.md).

## Mod housekeeping
```
tesl mod new <id> --name "<name>"      create a mod
tesl mod validate <id>                 check it like the game will
tesl mod enable <id> [--force]          switch it on (the game reads it at its next start)
tesl mod disable <id>
tesl mod edit ...                       change an existing card, deck, avatar, card back, board or track in place
tesl mod undo <id> / redo <id> / history <id>
tesl mod check                          load plan, skipped mods and why, overlaps, class, fingerprint
tesl mod order --set a,b | --auto
tesl mod export <id> / install <zip|folder|https link> / uninstall <id>
```

## Newer commands
```
tesl mod new <id> --name "<name>" --starter blank|copy|card|story|mode|opponent [--from <mod to copy>]
tesl mod details <id> ...                version, needed mods, conflicts, load-order hints, author, description
tesl mod release <id> ...                version up with changelog notes (exports carry CHANGELOG.md)
tesl pack save --mod <id> --name "<pack>" --odds 79,15,4.5,1.5 --last-slot 0,80,15,5 ...   card packs for the store
tesl pack list --mod <id> / remove --mod <id> --name "<pack>"
tesl translate list --mod <id>; export|import --mod <id> --lang <code> [--out|--file <csv>]; set ... --english "<text>" --text "<translation>"
tesl bulk cards --mod <id> --csv cards.csv [--art-dir <folder>]    many cards from a CSV
tesl bulk art --mod <id> --dir <folder>                             art or remasters named after cards
tesl bulk music --mod <id> --dir <folder> --at <moments> [--mode replace|rotation]
tesl search "<words>"                    search every mod
tesl preview --mod <id> [--card <name>]  cards drawn by the game itself (game must be closed)
tesl playtest --mod <id> [--report]      start TESL: Everlasting with the mod; --report reads what loaded
```
Run any command with `--help` for its options.

## AI opponents
```
tesl opponent save --mod <id> --name "<name>" [--title ...] [--image portrait.png | --portrait avatar:<slug>|asset:<path>]
    [--deck practice|random|<deck>] [--difficulty Novice|Apprentice|Adept|Expert|Master] [--temperament Friendly|Cocky|Playful|Stoic] [--no-practice]
tesl opponent list --mod <id> / remove --mod <id> --name "<name>"
```

## From the original README

### Use
From this folder (Windows):
```
tesl info                                  where the game and the workspace are
tesl assets index                          index every asset (about 70,000) from the bundle manifests, ~1 s
tesl assets list --kind texture --contains golden_saint
tesl assets export --kind audio --contains PlaymatIntro --out <a folder>
tesl assets export-card-art --collectible  all collectible card art, named "<Card> [<id>].png", with a manifest
tesl cards list --contains saint           card catalog (original card data)
```

New cards and decks (loaded by the offline restoration at game start; no game files change):
```
tesl mod new skyrim-heroes --name "Skyrim Heroes"
tesl card new --mod skyrim-heroes --name "Jarl's Housecarl" --template "Renowned Legate" --cost 5 --attack 4 --health 4 --art housecarl.png
tesl card new --mod skyrim-heroes --name "Greybeard Thu'um" --template "Fireball" --rules-from "Crushing Blow" --cost 2 --art thuum.png
tesl deck new --mod skyrim-heroes --name "Skyrim Heroes" --cards "Jarl's Housecarl x3, Greybeard Thu'um x3, Fireball x3, ..." --art-card "Jarl's Housecarl"
tesl mod validate skyrim-heroes
tesl mod enable skyrim-heroes              then start the offline game; the cards and deck are in your collection
```
Remastering: `tesl replace image --mod my-remaster --card "Fiery Imp" --image imp-4k.png` swaps an original image
(card art, avatars, deck banners; `--asset <path>` for any image the game loads by path). The game shows it at the
original size, so higher resolutions drop in; disabling the mod restores the original.

New avatars: `tesl avatar new --mod my-mod --name "Shieldmaiden" --image portrait.png --voice AvatarNord1` adds a choice
to the in-game avatar picker (the mod gets its own page, four avatars per page).

Emote lines: `tesl avatar emote --mod my-mod --avatar "Shieldmaiden" --emote Taunt --text "..." --audio line.wav` gives a
mod avatar its own voice lines. AI opponents emote too, with their own temperament.

Card backs: `tesl cardback new --mod my-mod --name "Dragon Seal" --image art.png --price 300` adds a card back (free with
price 0, otherwise sold for gold in the offline store).

A new card copies a template card (its frame, type, sounds and, unless told otherwise, its rules); `--rules-from` takes the
rules and text of any other card, `--no-rules` makes a vanilla card. Art is centre-cropped to a square and saved at
1024 x 1024. Decks follow the game's rules (50-70 cards, or 75-100 with three attributes) and get a banner
cut from the `--art-card` art. The game draws each mod card's frame, cost, name, type and text itself, so mod cards
look like original cards; mod cards and decks appear in the in-game collection and deck builder, owned as a playset. A sample mod is in `mods/sample-skyrim`.
Add `--json` to any command for machine-readable output. Exports go to `workspace/exports/` unless `--out` is given; the
suite refuses to write inside a game folder.

What exports today: textures (PNG, original resolution; manifest records size, transparency and the sprite crop), card art
mapped to every card that uses it, audio clips (WAV/OGG as stored), 3D models (OBJ per mesh), text assets.

### Setup
The suite uses its own Python environment in `.venv` (Python 3.10+, UnityPy 1.24.2 MIT, Pillow), made by
**Set up TESL Forge.cmd** from `requirements.txt`. By hand:
```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```
Card data comes from the original card JSON (`card-rule-graphs.jsonl.gz`), found automatically in the offline restoration's
`data/original-rules` folder, or given with `--data`.
