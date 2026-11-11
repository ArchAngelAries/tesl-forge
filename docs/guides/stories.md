# Stories

Whole campaigns, played from **Play > Stories** in TESL: Everlasting, next to the original stories.

## Structure
- **Story:** name, description, look (reuses an original story's map, discs and portraits, or your own images).
- **Acts** (any number) with **episodes** (any number), each with a map and **events** (location discs).
- **Events:** dialogue (speaker, portrait, text, voice file, **choices** that branch), **battles** (in the game-mode
  format: lanes, health, decks, start cards, opponent), rewards (gold, cards, card backs...).
- **Branching:** choices can lead to different events; the story remembers them.
- **Difficulty:** Normal and Master.

## In the app (Stories page)
1. **New story:** name, description, look. *Create story*.
2. **Edit:** build acts, episodes and events; drop images and voice lines; set battles like a game mode.
3. **Check** shows broken links (missing events, decks, files) before you play.

## Command line
```
tesl story new --mod my-mod --name "The Greenwood Saga"
tesl story options                          installed maps, discs and portraits
tesl story file --mod my-mod --story the-greenwood-saga --file narrator-01.wav
tesl story save --mod my-mod --file story.json
tesl story check --mod my-mod
```
Agents can read and write the whole story as JSON (MCP `get_story`, `save_story`).

## Tips
- Voice lines are plain audio files; record them, or use text-to-speech you're allowed to use.
- Start with one act and one episode, play it, then grow it.
- Stories are gameplay content: offline against the AI only.
