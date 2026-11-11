# Compatibility and sharing

## Load order
- The **Load order & compatibility** page lists enabled mods top to bottom; the top one loads first. Move mods with the
  arrows, or **Sort by dependencies**.
- When two mods change the same thing:
  | Overlap | Result |
  |---|---|
  | same image, sound or base board replaced | the later mod wins (shown on the page) |
  | same music moment | both play (shared) |
  | same card id or deck | the later one is skipped |
  | same card or story name | warning only |
- A broken file or item is skipped and listed; the rest of the mod and the game carry on.

## Manifest (`mod.json`)
```json
{
  "id": "skyrim-heroes", "name": "Skyrim Heroes", "version": "1.2.0", "author": "you",
  "dependencies": [{"id": "skyrim-core", "version": ">=1.0"}],
  "conflicts": ["old-skyrim-pack"],
  "load_after": ["remaster-hd"], "load_before": []
}
```
`requires_engine` (the TESL: Everlasting engine level the mod needs) is filled in for you. The game skips a mod whose
dependency is missing or the wrong version, that conflicts with an earlier mod, or that needs a newer engine, and says why.

## Mod class and fingerprint
- **local**: only images, sounds, music, boards. Also loads in online launches (only you see/hear it).
- **cosmetic**: avatars, card backs, emotes. Offline only for now.
- **gameplay**: cards, decks, rules, modes, stories, opponents. Offline against the AI only.
- **Fingerprint:** a SHA-256 of the mod's content, so two people can confirm they have the same mod (a future modded
  multiplayer server would compare these).

## Sharing a mod
1. Bump the version on the Overview page.
2. **Export** on the Load order page (or `tesl mod export <id>`): a `.zip` with `package.json` (version, engine level,
   class, fingerprint).
3. Share the zip (GitHub release, community index, mod sites).
4. Others **install** it from the zip, a folder or an `https` link (`tesl mod install <path-or-link>`); TESL Forge checks
   it (content files only, no paths outside the mod, size limits), backs up an older version and validates it.
5. **Uninstall** moves it to the trash in the workspace.

## Before you share
- Credit others' work you used and follow their terms.
- Original game art, audio and text belong to Bethesda/ZeniMax. Mods that only contain your own work are the safest to
  share and the only kind you can safely sell. See [Licensing](../LICENSING.md).
- Write a short README: what it adds, requirements, load order notes.
