# Cards

New cards work like original cards: the game draws the frame, cost gem, name banner, type line, attribute icon and rules
text itself from the card data. Only the art is yours.

## In the app (Cards page)
1. **Name** and **template card**. The template sets type (creature, action, item, support), frame, sounds and default
   rules. Search by name or text; filter by attribute and cost.
2. **Cost / Power / Health**, **rarity**, **unique** (one copy per deck).
3. **Rules**, three ways:
   - keep the template's rules;
   - **rules from** another card: its abilities and text on your card's body;
   - **build rules**: keywords (Guard, Charge, Breakthrough, Drain, Lethal, Regenerate, Ward, Rally=2, ...) plus abilities
     copied from any cards, with their numbers and card references changed.
   - **no rules** for a vanilla card.
4. **Text**: leave it empty to use the text that matches the rules; type your own when you reword it. If a changed number
   can't be rewritten in the text safely, the result tells you to set the text yourself.
5. **Art**: drop a picture. It's cropped to a square and saved at 1024×1024; previews show the hand (upper part) and board
   (centred portrait) crops.
6. **Voice lines**: on *Sounds & voices*, give the card its own Play, Attack, Death, Hit, Success and Failure lines (unset
   lines keep the template card's voice).

## Command line
```
tesl card new --mod my-mod --name "Jarl's Housecarl" --template "Renowned Legate" --cost 5 --attack 4 --health 4 --art housecarl.png
tesl card new --mod my-mod --name "Greybeard Thu'um" --template "Fireball" --rules-from "Crushing Blow" --cost 2 --art thuum.png
tesl card abilities "Fiery Imp"
tesl card new --mod my-mod --name "Imp Swarm" --template "Fiery Imp" --keywords "Charge" --abilities '[{"card": "Fiery Imp", "ability": "triggered:0", "params": {"<path>": 3}}]'
```

## Tips
- Pick a template whose ability is close to what you want, then adjust numbers.
- A mechanic that no original card has can't be built yet; it needs engine work.
- Mod cards are owned as a full playset when the mod is on, and go away when it's off.
- Cards are gameplay content: offline against the AI only.
