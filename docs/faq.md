# FAQ — TESL Forge

**Do I need to code?**
No. The app does everything with forms, pickers and drag-and-drop. The command line and MCP server are optional.

**Does TESL Forge include the game or its art?**
No. It reads your own installed game and never writes into a game folder. See the [DISCLAIMER](../DISCLAIMER.md).

**Do I need TESL: Everlasting?**
To play your mods, yes: TESL: Everlasting loads them. They're separate downloads and never bundled.

**Do my mods work online with TESL-Reborn?**
Only local visual and audio mods (remasters, sounds, music, boards), and only you see or hear them. Cards, decks, modes,
stories, avatars and other gameplay or cosmetic content are offline only. TESL-Reborn is a separate project; please don't
ask its team for help with TESL Forge.

**Can I sell what I make?**
Your own creations are yours, including to sell (see [Licensing](LICENSING.md)). TESL Forge itself may never be sold.
Original Bethesda art, audio or text inside a mod stays theirs; mods made only of your own work are the safe ones to sell.

**Can an AI agent build mods for me?**
Yes. Connect the MCP server (see README) and ask, for example, "make a deck of Skyrim heroes with new art". Agents follow
the same rules as people, and agent or LLM players are offline against the in-game AI only.

**Where do I install TESL Forge?**
Anywhere outside the game folder. It records its location each time it runs, so TESL: Everlasting finds your mods.

**Where are my mods stored?**
In `mods/<mod-id>/` inside the TESL Forge folder. Exports go to `workspace/exports/`. Deleted items go to
`workspace/trash/`.

**How do I back up my work?**
Copy the `mods` folder, or export each mod as a package.

**Can I edit original cards?**
Not directly; make a new card from it as a template, or replace its art (remaster). Rule changes to original cards may
come later.

**Why was my deck refused?**
It breaks the game's deck rules (size, copies, attributes, tokens). The game would mark it invalid, so TESL Forge refuses it.

**Is there a native app / installer?**
Coming. For now: unzip, run **Set up TESL Forge.cmd** once, then **Open TESL Forge.cmd**. It runs as a local app at
`127.0.0.1` (your computer only).

**Can I translate my mod?**
Yes: the **Translations** page collects every text your mod shows; translate it per language or hand a CSV to translators.

**Mac or Linux?**
Windows is the target. The Python parts may run elsewhere, but the game and TESL: Everlasting are Windows programs.
