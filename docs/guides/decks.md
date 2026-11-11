# Decks

Premade decks appear in the in-game deck list and can be given to AI opponents, modes and stories.

## Rules (the game client's own)
- 50–70 cards with one or two attributes; three attributes need 75–100 cards and at least one three-attribute card.
- At most 3 copies of a card, 1 if it's unique. Collectible cards only (no tokens).
- A deck that breaks these shows a warning sign in game and can't be played, so TESL Forge refuses to save it.

## In the app (Decks page)
1. Name and description.
2. Search cards (original and mod cards), click to add one copy, use the counters to adjust.
3. Watch the checks and the magicka curve.
4. **Banner card:** a mod card with art gets two crops cut for you (a 512×128 list banner and a 256×512 portrait);
   otherwise the deck uses that card's original art.
5. **Save deck**.

## Command line
```
tesl deck new --mod my-mod --name "Skyrim Heroes" --cards "Jarl's Housecarl x3; Greybeard Thu'um x3; Fireball x3; ..." --art-card "Jarl's Housecarl"
```
Separate entries with `;` or new lines (names may contain commas, like "Miraak, Dragonborn").
