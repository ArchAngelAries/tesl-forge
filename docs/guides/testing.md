# Testing your mod

## Check
The mod **Overview** shows a *Check* badge. "Ready to play" means everything passes the same rules the game uses (deck
rules, missing files, broken story links, keywords written twice, ...). Otherwise it lists what to fix, linked to the item.

## Game previews (Cards, Decks, Card backs and Boards pages)
**Make game previews** starts TESL: Everlasting hidden and lets the game draw your content itself: cards with their own
frames and fonts, card backs on a real card, deck banners as the deck list shows them, and boards as a player sees an empty
board (with your table image and 3D edits). TESL Forge then shows these pictures. Your profile isn't touched. Close the game
first. Card backs, banners and boards need TESL: Everlasting 0.56 or newer.
```
tesl preview --mod my-mod [--card "Jarl's Housecarl"]   # without --card: cards, card backs, banners and boards
```

## Play test (Overview)
**Play test in TESL: Everlasting** starts the game offline with your mod switched on. Afterwards TESL Forge reads the
game's mod report and shows what loaded and anything that was skipped, with the reason.
```
tesl playtest --mod my-mod
tesl playtest --mod my-mod --report      only read the last report
```
The report is `.offline-user-data\mod-report.json` in the game folder; the logs are in `.offline-user-data\logs`.

## Search all mods
**Search all mods** (or `Ctrl+K`, `/`) finds any card, deck, avatar, opponent, board, track, sound, mode, story or
replaced image in every mod, which helps when two mods change the same thing. `tesl search "<words>"` does the same.

## Before you share
1. Check passes, play test is clean, previews look right.
2. **Details:** version, needed mods with version ranges, conflicts, load-order hints, website, preview image.
3. **Release:** raise the version and write changelog notes (exports include `CHANGELOG.md`).
4. Export the package (see [Compatibility and sharing](compatibility-and-sharing.md)).
