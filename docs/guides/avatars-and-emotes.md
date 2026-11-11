# Avatars and emotes

## Avatars (Avatars & emotes page)
- Give a **tall full-body portrait** (the game's shape is 286:512; any resolution). TESL Forge also cuts the round
  head-and-shoulders portrait for the profile and match intro; move it with *head position* if needed.
- **Voice:** borrow an original avatar's emote voice lines, or give your own per emote.
- A mod's avatars get their own pages in the in-game picker, four per page; set the page's name and description.
- Command line:
  ```
  tesl avatar new --mod my-mod --name "Shieldmaiden" --image portrait.png --voice AvatarNord1 [--head 0.22]
  tesl avatar page --mod my-mod --name "Skyrim Heroes" --description "..."
  tesl avatar voices
  ```

## Emote lines
Each avatar has 8 emotes: Hello, Good game, Implore, Taunt, Oops, Nice play, Thank you, Sorry. Set the text and/or voice
of any of them for a mod avatar; unset ones keep the borrowed voice.
```
tesl avatar emote --mod my-mod --avatar "Shieldmaiden" --emote Taunt --text "Is that all?" --audio taunt.wav
```

## Extra emotes (beyond the eight)
They appear on a **More...** page of the emote panel. With no avatar given they're for every avatar. *Like* (e.g. Taunt)
lets the AI use it as a variant of that emote.
```
tesl emote add --mod my-mod --text "For Skyrim!" --label "Skyrim" [--avatar "Shieldmaiden"] [--audio line.wav] [--like Taunt]
```

## The AI emotes too
AI opponents use their avatar's lines and emote by temperament (friendly, cocky, playful, stoic): openings, big hits,
wiped boards, near-death, slow turns, and replies to yours.
