# AI opponents

In-game AI characters for TESL: Everlasting: Practice, game modes and story battles.

- **Name and title.**
- **Portrait:** a picture (cropped to the avatar shape), one of your mod's avatars, or a game image.
- **Deck:** a named deck (mod or original), *practice* (the usual practice decks), or *random* (with a size).
- **Difficulty:** Novice, Apprentice, Adept, Expert, Master, or the player's choice.
- **Personality:** Friendly, Cocky, Playful or Stoic (how it emotes), or automatic.
- **Practice:** appears in random Practice (when the player allows mod opponents in F10), or only where a mode or story
  names it.

```
tesl opponent save --mod my-mod --name "Ulfric" --title "Jarl of Windhelm" --image ulfric.png --deck "Skyrim Heroes" --difficulty Expert --temperament Cocky
tesl opponent list --mod my-mod
tesl opponent remove --mod my-mod --name "Ulfric"
```

AI opponents play offline only. An LLM or agent "player" follows the same rule: offline against the in-game AI, never
against people.
