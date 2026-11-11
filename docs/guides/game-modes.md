# Game modes

Custom matches against the AI with your own rules. Players start them from TESL: Everlasting's **F10 > Practice mode**,
then **Play > Practice**.

## What you can set (Game modes page)
- **Lanes:** any of 48 playable lane types (Field, Shadow, Plunder, Windy, Smelting, ...) per lane, with options where a
  lane has them (for example `Plunder:4`); shuffle lanes.
- **Per side** (player / opponent): health, starting magicka, runes, deck (a mod or original deck, the player's choice,
  or random), starting cards in hand or in a lane.
- **Match:** who goes first, cards drawn per turn, magicka per turn, no-mulligan, board, music.
- **Reward:** gold for a win.
- **Opponent:** any AI opponent (see [AI opponents](ai-opponents.md)).

## Command line
```
tesl mode lanes
tesl mode save --mod my-mod --name "Laying Siege" --lane Plunder:4 --lane Windy --player-health 25 --player-magicka 3 --player-card "lane1:Fiery Imp" --opponent-deck random --draw-per-turn 1 --reward-gold 50
```
(MCP: `mode_options`, `save_mode`.)

## Tips
- Test small changes one at a time; **Play test** (or `.offline-user-data\mod-report.json` in the game folder) lists any skipped settings.
- Modes are gameplay content: offline against the AI only.
