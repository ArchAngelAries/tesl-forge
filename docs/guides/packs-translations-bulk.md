# Card packs, translations and bulk import

## Card packs (Card packs page)
Packs your mod sells for gold in TESL: Everlasting's offline store, with their own drop table.
- **Name, description, price** (gold) and **store art** picture.
- **Cards per pack** (1–12).
- **Card pool:** your mod's cards, all cards, or chosen sets (Core, Skyrim, Morrowind, ...).
- **Rarity odds** (common, rare, epic, legendary) for every slot, and separate odds for the **last slot** (for example a
  guaranteed rare or better).
- **Premium chance:** the percent chance a card comes as premium.
- Or **hand-picked cards** with weights instead of rarity slots.

```
tesl pack save --mod my-mod --name "Skyrim Heroes Pack" --price 100 --cards 6 --pool mod --odds 79,15,4.5,1.5 --last-slot 0,80,15,5 --image pack.png
tesl pack save --mod my-mod --name "Jarl's Chest" --price 300 --card "Jarl's Housecarl=3" --card "Greybeard Thu'um=1"
tesl pack list --mod my-mod
tesl pack remove --mod my-mod --name "Jarl's Chest"
```

## Translations (Translations page)
Every text your mod shows (card names and text, deck names, story dialogue, emotes, mode and pack names, ...) is collected
automatically. The game shows the translation when it runs in that language; untranslated text stays in English.
- Pick a language (ISO code such as `de`, `fr`, `es`, `pt-BR`) and translate line by line; progress shows in the mod check.
- For translators: **export a CSV** (English, translation), have it filled in, **import** it back.

```
tesl translate list --mod my-mod
tesl translate export --mod my-mod --lang de [--out my-mod-de.csv]
tesl translate import --mod my-mod --lang de --file my-mod-de.csv
tesl translate set --mod my-mod --lang de --english "Jarl's Housecarl" --text "Huskarl des Jarls"
```

## Bulk import (Bulk import page)
Make or change many things at once. Problems are listed per row, and the whole import is one undo step.
- **Cards from a CSV.** The first row names the columns: `name, template, cost, power, health, rarity, text, art,
  unique`. Existing cards with the same name are updated. Art files are found by file name in the art folder (default:
  next to the CSV).
- **Art by file name.** Pictures named after cards: your mod's cards get new art; original cards get a remastered
  replacement.
- **Music.** A folder of audio files becomes soundtrack tracks for the moments you choose.

```
tesl bulk cards --mod my-mod --csv cards.csv [--art-dir art]
tesl bulk art --mod my-mod --dir remasters
tesl bulk music --mod my-mod --dir music --at MainMenuState,Victory [--mode rotation]
```
