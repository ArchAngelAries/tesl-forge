# Sounds, voices and music

Audio files: WAV, OGG, MP3, FLAC and more (other formats are converted with ffmpeg if it's installed).

## Music (Music page)
- **New track:** name, audio file, where it plays (*moments* such as main menu, collection, deck builder, story map,
  match start, victory, defeat; a **board**; a **game mode**), mode *replace* (only your track) or *rotation* (mixed with
  the originals), volume.
- Command line:
  ```
  tesl music contexts --mod my-mod
  tesl music add --mod my-mod --name "Hearth Theme" --file theme.ogg --context MainMenuState --context Board:Elsweyr --mode rotation --volume 0.8
  ```

## Replace any game sound or voice line (Sounds & voices page)
1. Search: words plus an optional category (card-voice, card-sfx, emote, board-dialogue, story, announcer, cinematic, ui).
2. Pick the sound, drop one or more files. Several files = a random pick each time. All takes and languages are replaced.
- Command line:
  ```
  tesl sound search dragon roar --category card-voice
  tesl sound replace --mod my-mod --sound <id> --file roar1.wav --file roar2.wav
  ```

## Mod card voice lines
Each mod card can have Play, Attack, Death, Hit, Success and Failure lines; unset lines keep the template card's voice.
```
tesl sound card-voice --mod my-mod --card "Jarl's Housecarl" --line Play --file housecarl-play.wav
```

## Tips
- Music and sound replacements are **local audio mods**: they also load online (only you hear them).
- Voice acting: record your own, use voices you have rights to, or AI text-to-speech you're allowed to use.
