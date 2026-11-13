"""MCP server (stdio, JSON-RPC 2.0) for AI agents: Claude Code, Codex or any MCP client. No extra packages.

Register it once, for example:
    claude mcp add tesl -- "<suite>\\.venv\\Scripts\\python.exe" -X utf8 -m tesl_suite.mcp_server
or open the suite folder in an agent that reads .mcp.json (included). Tools wrap the same functions as the CLI, the local API
and the app; image and audio arguments are file paths on this computer.
"""
from __future__ import annotations

import json
import sys
import traceback

from . import __version__, api, avatars, cardbacks, mods, replace

PROTOCOL = "2024-11-05"


def _s(desc, **props):
    """JSON schema helper: props as name=(type, description[, required])."""
    required = [k for k, v in props.items() if len(v) > 2 and v[2]]
    def prop(v):
        d = {"type": v[0], "description": v[1]}
        if "array" in v[0]:
            d["items"] = {}          # entries may be strings or {name, count} objects
        return d
    return {"type": "object", "properties": {k: prop(v) for k, v in props.items()}, "required": required,
            "description": desc}


TOOLS = {
    "suite_info": (_s("Where the game, the suite workspace and the mods folder are."), lambda a: api.info()),
    "list_mods": (_s("All mods with card/deck counts and whether each is enabled."), lambda a: {"mods": mods.list_mods()}),
    "mod_detail": (_s("Everything in a mod: cards, decks, avatars, card backs, replacements and the validation result.",
                      mod=("string", "mod id", True)), lambda a: api.mod_detail(a["mod"])),
    "new_mod": (_s("Create a mod (a folder in the suite; never touches game files). starter: blank (default), copy (a full copy of 'source' "
                   "with its own ids; copy sample-skyrim for a complete starter pack), card, story, mode or opponent (a first item to edit).",
                   id=("string", "folder id: letters, digits, dashes", True), name=("string", "display name", True), author=("string", "author"),
                   description=("string", "what it adds"), starter=("string", "blank|copy|card|story|mode|opponent"), source=("string", "mod to copy")),
                lambda a: __import__("tesl_suite.starters", fromlist=["create"]).create(api._game(), a["id"], a["name"], a.get("starter") or "blank",
                                                                                     a.get("author", ""), a.get("description", ""), a.get("source"))),
    "set_mod_enabled": (_s("Turn a mod on or off for the offline game (takes effect at the game's next start).",
                           mod=("string", "mod id", True), enabled=("boolean", "true to enable", True),
                           force=("boolean", "enable even if compatibility checks would skip it")),
                        lambda a: mods.set_enabled(a["mod"], bool(a["enabled"]), bool(a.get("force")))),
    "edit_item": (_s("Edit an existing item in place (its id and slug stay; only the given fields change). kind: card {name, cost, attack, health, "
                     "text, rarity, unique, art (image path), rules_from, abilities, keywords} | deck {name, cards_spec (list or 'A x3; B x2' - use ; or a list for names with commas), art_card, "
                     "description} | avatar {name, image, head, voice} | cardback {name, image, price, unlock} | board {name, image, base, mode} | "
                     "track {name, file, contexts, mode, volume}.", mod=("string", "mod id", True), kind=("string", "card|deck|avatar|cardback|board|track", True),
                     item=("string", "slug, name or card id", True), fields=("object", "fields to change", True)),
                  lambda a: __import__("tesl_suite.edits", fromlist=["edit"]).edit(api._game(), a["mod"], a["kind"], a["item"], a.get("fields") or {})),
    "undo_mod_change": (_s("Undo the last change to a mod (its files return to how they were; deleted files come back from the trash).",
                           mod=("string", "mod id", True)), lambda a: __import__("tesl_suite.fsutil", fromlist=["undo"]).undo(a["mod"])),
    "redo_mod_change": (_s("Redo the last undone change to a mod.", mod=("string", "mod id", True)),
                        lambda a: __import__("tesl_suite.fsutil", fromlist=["redo"]).redo(a["mod"])),
    "mod_history": (_s("Recent changes of a mod (undo and redo steps).", mod=("string", "mod id", True)),
                    lambda a: __import__("tesl_suite.fsutil", fromlist=["history"]).history(a["mod"])),
    "check_mod_compatibility": (_s("Compatibility of the enabled mods: the load order the game will use, mods it will skip and why (missing "
                                   "dependency, declared conflict, newer engine needed, duplicates), overlaps (same image/sound/board/music "
                                   "changed by two mods: the later wins; clashing deck/card ids), and per mod its multiplayer class "
                                   "(local / cosmetic / gameplay), required engine level and fingerprint."),
                                lambda a: __import__("tesl_suite.compat", fromlist=["report"]).report()),
    "install_mod": (_s("Install a mod from a .zip, a mod folder or an https link to a .zip (content files only; an older installed version is "
                       "backed up). Validated and compatibility-checked; enabled only if asked.", source=("string", "path or https link", True),
                       enable=("boolean", "enable it too"), force=("boolean", "replace the same or a newer installed version")),
                    lambda a: __import__("tesl_suite.packages", fromlist=["install"]).install(a["source"], bool(a.get("enable")), bool(a.get("force")))),
    "export_mod": (_s("Package a mod as a shareable .zip with package.json (version, engine level, multiplayer class, fingerprint).",
                      mod=("string", "mod id", True), out=("string", "output file (optional)")),
                   lambda a: __import__("tesl_suite.packages", fromlist=["export_mod"]).export_mod(a["mod"], a.get("out"))),
    "set_mod_load_order": (_s("Set the load order of enabled mods (first loads first; later mods win overlaps), or sort it automatically "
                              "by dependencies and load_after/load_before hints.", order=("array", "mod ids in load order (left out = disabled)"),
                              auto=("boolean", "sort automatically instead")),
                           lambda a: (lambda c: c.auto_order() if a.get("auto") else c.set_order(list(a.get("order") or [])))(__import__("tesl_suite.compat", fromlist=["report"]))),
    "validate_mod": (_s("Check a mod (deck rules, missing files, unknown rule types, overlaps).", mod=("string", "mod id", True)),
                     lambda a: mods.validate(api._game(), a["mod"])),
    "search_cards": (_s("Search the game's card catalog (original card data). Use it to pick templates and rule donors.",
                        q=("string", "name, rules text or numeric id"), attribute=("string", "Strength, Intelligence, Willpower, Agility or Endurance"),
                        type=("string", "Creature, Action, Item or Support"), cost=("integer", "magicka cost (7 = 7 or more)"),
                        collectible=("boolean", "only collectible cards (default true)"), limit=("integer", "max results (default 30)")),
                     lambda a: api.card_query({"q": a.get("q", ""), "attribute": a.get("attribute", ""), "type": a.get("type", ""),
                                               "cost": "" if a.get("cost") is None else str(a["cost"]),
                                               "collectible": "0" if a.get("collectible") is False else "1", "limit": str(a.get("limit", 30))})),
    "new_card": (_s("Create a card from a template card (frame, type, sounds and rules), optionally with another card's rules.",
                    mod=("string", "mod id", True), name=("string", "card name", True), template=("string", "existing card name or id", True),
                    cost=("integer", "magicka cost"), attack=("integer", "power"), health=("integer", "health"), rarity=("string", "Common, Rare, Epic or Legendary"),
                    text=("string", "card text (only to reword; normally the rules' own text)"), art=("string", "path to a square image"),
                    rules_from=("string", "card whose rules to copy"), no_rules=("boolean", "vanilla card"), unique=("boolean", "one copy per deck"),
                    abilities=("array", "rule editor: [{card, ability: 'triggered:0'|'play:0'|'aura:0'|'activated:0', params: {path: value}}] (see card_abilities)"),
                    keywords=("object", "rule editor: {Guard: true, Charge: true, Rally: 1, ...}")),
                 lambda a: mods.new_card(api._game(), a["mod"], a["name"], a["template"], a.get("cost"), a.get("attack"), a.get("health"),
                                         a.get("text"), a.get("rarity"), a.get("art"), a.get("rules_from"), bool(a.get("no_rules")), a.get("unique"),
                                         a.get("abilities"), a.get("keywords"))),
    "card_abilities": (_s("A card's abilities (ids for new_card abilities) with their editable parameters (amounts, card references) and keywords.",
                          card=("string", "card name or id", True)), lambda a: api.card_abilities(a["card"])),
    "new_deck": (_s("Create a premade deck. Game rules: 50-70 cards (75-100 with three attributes), at most 3 copies.",
                    mod=("string", "mod id", True), name=("string", "deck name", True),
                    cards=(["string", "array"], "a list [\"Card Name x3\", \"Other x2\"] or text 'Card Name x3; Other x2' (separate with ; or new lines; commas also work but names with commas like 'Miraak, Dragonborn' need ; or a list). Names or numeric ids.", True), art_card=("string", "card used for the deck banner"),
                    description=("string", "deck description")),
                 lambda a: mods.new_deck(api._game(), a["mod"], a["name"], a["cards"], a.get("art_card"), a.get("description", ""))),
    "new_avatar": (_s("Add an avatar choice (own page in the avatar picker).", mod=("string", "mod id", True), name=("string", "avatar name", True),
                      image=("string", "path to a tall portrait", True), voice=("string", "original avatar whose emote voice it borrows (see list_voices)"),
                      head=("number", "head height as a fraction from the top, for the round crop (default 0.22)"),
                      profile=("string", "separate picture for the round profile portrait (default: cut from image)")),
                   lambda a: avatars.new_avatar(a["mod"], a["name"], a["image"], a.get("voice"), float(a.get("head") or 0.22), a.get("profile"))),
    "list_voices": (_s("Original avatars whose emote voice lines new avatars can borrow."), lambda a: {"voices": avatars.original_avatars()}),
    "set_avatar_emote": (_s("Set one of an avatar's 8 emote lines (Hello, GoodGame, Implore, Taunt, Oops, NicePlay, ThankYou, Sorry). The AI uses them too.",
                            mod=("string", "mod id", True), avatar=("string", "avatar name or slug", True), emote=("string", "emote type", True),
                            text=("string", "the line"), audio=("string", "path to a voice clip (WAV/MP3/OGG)")),
                         lambda a: avatars.set_emote(a["mod"], a["avatar"], a["emote"], a.get("text"), a.get("audio"))),
    "new_cardback": (_s("Add a card back (free, or sold for gold in the offline store).", mod=("string", "mod id", True), name=("string", "name", True),
                        image=("string", "path to an image", True), price=("integer", "gold; 0 = free"), unlock=("string", "how to get it"),
                        size=("integer", "1024 or 2048")),
                     lambda a: cardbacks.new_cardback(a["mod"], a["name"], a["image"], int(a.get("price") or 0), a.get("unlock"), int(a.get("size") or 1024))),
    "new_board": (_s("Add a board: a 2:1 painting re-skinning one of the five playmats (props stay). rotation = joins the random choice; replace = always instead of that base.",
                     mod=("string", "mod id", True), name=("string", "name", True), image=("string", "path to a wide image (omit: keep the base's table, edit it with edit_board)"),
                     base=("string", "Original, IsleOfMadness, AllianceWar, Elsweyr or RealmsOfOblivion"), mode=("string", "rotation (default) or replace"),
                     size=("integer", "2048 (default) or 4096")),
                  lambda a: __import__("tesl_suite.boards", fromlist=["new_board"]).new_board(a["mod"], a["name"], a.get("image"), a.get("base") or "Original", a.get("mode") or "rotation", int(a.get("size") or 2048))),
    "add_extra_emote": (_s("Add an emote beyond the game's eight (players page to it with 'More' in the match emote panel). Without avatar it joins every avatar, originals included. "
                            "like = Hello/GoodGame/Implore/Taunt/Oops/NicePlay/ThankYou/Sorry: the AI uses it as a variant of that emote.",
                            mod=("string", "mod id", True), text=("string", "what the bubble says", True), label=("string", "button text (short)"),
                            avatar=("string", "mod avatar (omit for every avatar)"), audio=("string", "voice clip path"), like=("string", "one of the eight")),
                         lambda a: avatars.add_extra_emote(a["mod"], a.get("text") or "", a.get("label"), a.get("avatar"), a.get("audio"), a.get("like"))),
    "search_sounds": (_s("Find the game's sounds by plain words (card voices like 'Fiery Imp attacks', emote lines, story dialogue, announcer, interface). "
                          "categories: card-voice, card-sfx, emote, board-dialogue, story, announcer, cinematic, ui.",
                          q=("string", "words"), category=("string", "category id"), limit=("integer", "default 50")),
                       lambda a: __import__("tesl_suite.sounds", fromlist=["search"]).search(api._game(), a.get("q"), a.get("category"), int(a.get("limit") or 50))),
    "replace_sound": (_s("Replace one of the game's sounds (all its takes and languages) with your audio; several files = a random pick each time.",
                          mod=("string", "mod id", True), sound=("string", "sound id from search_sounds (or a clip name)", True),
                          files=("array", "paths to audio files", True), volume=("number", "0..1")),
                       lambda a: __import__("tesl_suite.sounds", fromlist=["replace_sound"]).replace_sound(api._game(), a["mod"], a["sound"], list(a["files"]), float(a.get("volume") or 1.0))),
    "card_voice": (_s("Give a mod card its own voice line. Lines: Play (enters play), Attack, Death (last gasp), Hit, Success, Failure; unset lines keep the template card's voice.",
                       mod=("string", "mod id", True), card=("string", "mod card name", True), line=("string", "Play, Attack, Death, Hit, Success or Failure", True),
                       file=("string", "path to the audio", True)),
                    lambda a: __import__("tesl_suite.sounds", fromlist=["card_voice"]).card_voice(a["mod"], a["card"], a["line"], a["file"])),
    "new_music_track": (_s("Add a soundtrack: an audio file (any format; converted to OGG) that plays in the chosen contexts. Contexts: moments such as MainMenuState, StoreState, StoryState, "
                            "MatchOngoing, MatchHalfHealth, EndGameWin, EndGameLose, or boards Board:Original / Board:Elsweyr / Board:<mod>/<board> (see music_contexts). "
                            "replace = instead of the game's music there; rotation = mixed with it.",
                            mod=("string", "mod id", True), name=("string", "track name", True), file=("string", "path to the audio", True),
                            contexts=("array", "where it plays", True), mode=("string", "replace (default) or rotation"), volume=("number", "0..1, default 1")),
                         lambda a: __import__("tesl_suite.music", fromlist=["add_track"]).add_track(a["mod"], a["name"], a["file"], list(a["contexts"]), a.get("mode") or "replace", float(a.get("volume") or 1.0))),
    "music_contexts": (_s("Where soundtracks can play: game moments and boards (with this mod's own boards).", mod=("string", "mod id")),
                        lambda a: __import__("tesl_suite.music", fromlist=["contexts"]).contexts(a.get("mod"))),
    "mode_options": (_s("What a game mode can use: lane types (with the game's rule text; implemented ones are playable offline), decks, card places, turn rules.",
                        mod=("string", "mod id")),
                     lambda a: (lambda m: {"lanes": m.lanes(), "decks": m.decks(api._game(), a.get("mod")), "zones": m.ZONES, "rules": m.RULES, "difficulties": m.DIFFICULTIES})(
                         __import__("tesl_suite.modes", fromlist=["lanes"]))),
    "save_mode": (_s("Create or replace a game mode (played from the offline game's F10 menu > Practice mode, then Play > Practice). "
                     "lanes: [{type, size 2|4|6}] 1-2; player/opponent: {health, magicka, runes 0-5, extra_cards, deck own|random|practice|<mod deck type_name>, random_size, "
                     "cards {hand|lane1|lane2|support|deck: [card names]}}; first random|player|opponent; difficulty chosen|Novice|Adept|Expert; "
                     "rules {draw_per_turn, magicka_per_turn, damage_per_turn, heal_per_turn, random_creature_every, lane_shuffle_every, no_mulligan}; "
                     "board: Original|IsleOfMadness|AllianceWar|Elsweyr|RealmsOfOblivion or a mod board 'mod/slug'; reward_gold.",
                     mod=("string", "mod id", True), name=("string", "mode name", True), description=("string", "one line"), lanes=("array", "lanes"),
                     player=("object", "the human's side"), opponent=("object", "the AI's side"), first=("string", "who starts"), difficulty=("string", "AI"),
                     opponent_name=("string", "AI name"), rules=("object", "turn rules"), board=("string", "board"), reward_gold=("integer", "gold for a win"),
                     ai=("string", "an AI opponent '<mod>/<slug>' (its portrait, name, deck, difficulty and personality)")),
                  lambda a: __import__("tesl_suite.modes", fromlist=["save_mode"]).save_mode(api._game(), a["mod"], a["name"], a.get("description") or "", a.get("lanes"),
                      a.get("player"), a.get("opponent"), a.get("first") or "random", a.get("difficulty") or "chosen", a.get("opponent_name"), a.get("rules"),
                      a.get("board"), int(a.get("reward_gold") or 0), a.get("ai"))),
    "preview_cards": (_s("Draw a mod's cards with the game itself (starts TESL: Everlasting hidden; about half a minute plus a few seconds per card; "
                         "the game must be closed). Returns the picture files.", mod=("string", "mod id", True), cards=("array", "only these card names or ids")),
                      lambda a: (lambda pv: {**pv.render(api._game(), a["mod"], a.get("cards"), wait=True), "folder": str(pv.folder(a["mod"]))})(
                          __import__("tesl_suite.previews", fromlist=["render"]))),
    "bulk_import": (_s("Import many items at once. kind cards: text = CSV (name, template, cost, power, health, rarity, text, art, unique; existing names "
                       "are updated); kind art: files {file name: path}, each named after a card (mod cards get art, originals a replacement); kind sounds: files "
                       "{name: path}, each named after a game sound or a card voice line (\"Arena End.wav\", \"<card> Play.wav\"); kind music: files "
                       "{name: path} with contexts [moments] and mode rotation|replace.", mod=("string", "mod id", True), kind=("string", "cards|art|sounds|music", True),
                       text=("string", "CSV text"), files=("object", "{file name: local path}"), contexts=("array", "music moments"), mode=("string", "rotation|replace")),
                    lambda a: (lambda b: b.cards_csv(api._game(), a["mod"], a.get("text") or "", a.get("files") or {}) if a["kind"] == "cards" else
                               b.art_by_name(api._game(), a["mod"], a.get("files") or {}) if a["kind"] == "art" else
                               b.sounds_by_name(api._game(), a["mod"], a.get("files") or {}) if a["kind"] == "sounds" else
                               b.music(a["mod"], a.get("files") or {}, a.get("contexts") or [], a.get("mode") or "rotation"))(__import__("tesl_suite.bulk", fromlist=["music"]))),
    "translation_table": (_s("A mod's texts (English) with their translation in a language (ISO codes: de, fr, es, it, ru, pl, pt, ja, zh, ko, ...); the game shows "
                             "the translation when it runs in that language.", mod=("string", "mod id", True), language=("string", "language code", True)),
                          lambda a: __import__("tesl_suite.translations", fromlist=["table"]).table(a["mod"], a["language"])),
    "save_translations": (_s("Save translations: values {English text: translation} (empty removes one).", mod=("string", "mod id", True),
                             language=("string", "language code", True), values=("object", "{English: translation}", True)),
                          lambda a: __import__("tesl_suite.translations", fromlist=["save"]).save(a["mod"], a["language"], a.get("values") or {})),
    "save_pack": (_s("Create or change a card pack sold for gold in TESL: Everlasting's offline store. pool: mod | all | [card set codes: 0_Core, Skyrim, "
                     "Dark_Brotherhood, Clockwork_City, Morrowind, Isles_Of_Madness, Alliance_War, Sage, Crisis, Monthlies]; odds/last_slot: {common, rare, epic, legendary} "
                     "chances; cards_list [{card, weight}] replaces rarity slots; premium percent; image: store art picture.",
                     mod=("string", "mod id", True), name=("string", "pack name", True), slug=("string", "existing slug"), description=("string", "store text"),
                     price=("integer", "gold"), cards=("integer", "cards per pack 1-12"), pool=("string", "mod, all, or comma-separated set codes"),
                     odds=("object", "rarity chances"), last_slot=("object", "rarity chances for the last slot"), premium=("number", "percent"),
                     cards_list=("array", "[{card, weight}]"), image=("string", "art picture path")),
                  lambda a: __import__("tesl_suite.packs", fromlist=["save_pack"]).save_pack(api._game(), a["mod"],
                      {**{k: a.get(k) for k in ("slug", "name", "description", "price", "cards", "odds", "last_slot", "premium", "cards_list")},
                       "pool": None if a.get("pool") is None else (a["pool"] if a["pool"] in ("mod", "all") else [s.strip() for s in str(a["pool"]).split(",") if s.strip()])}, a.get("image"))),
    "remove_pack": (_s("Remove a card pack.", mod=("string", "mod id", True), name=("string", "name or slug", True)),
                    lambda a: __import__("tesl_suite.packs", fromlist=["remove"]).remove(a["mod"], a["name"])),
    "mod_details": (_s("Change a mod's details: name, author, description, website, version (1.2.3), dependencies [{id, version range}], "
                       "conflicts [ids], load_after [ids], load_before [ids]. Omit what stays.", mod=("string", "mod id", True), name=("string", "name"),
                       author=("string", "author"), description=("string", "description"), website=("string", "link"), version=("string", "1.2.3"),
                       dependencies=("array", "[{id, version}]"), conflicts=("array", "mod ids"), load_after=("array", "mod ids"), load_before=("array", "mod ids")),
                    lambda a: __import__("tesl_suite.details", fromlist=["update"]).update(a["mod"], {k: v for k, v in a.items() if k != "mod"})),
    "release_mod": (_s("Record a release: raises the version (part major/minor/patch, or an exact version) and adds changelog notes.",
                       mod=("string", "mod id", True), notes=("string", "what changed", True), part=("string", "major|minor|patch"), version=("string", "exact version")),
                    lambda a: __import__("tesl_suite.details", fromlist=["add_change"]).add_change(a["mod"], a["notes"], a.get("part") or "minor", a.get("version"))),
    "save_opponent": (_s("Create or change an AI opponent for TESL: Everlasting (offline, vs the in-game AI). It plays in Practice (picked in F10, or at random when the "
                         "player allows mod opponents) and in modes/story battles that set ai '<mod>/<slug>'. portrait: avatar:<this mod's avatar slug> or asset:<path>; "
                         "image: a picture file to crop into the portrait instead. deck: practice|random|<deck type name or name>; difficulty chosen|Novice|Apprentice|Adept|Expert|Master; "
                         "temperament Friendly|Cocky|Playful|Stoic (emote personality); practice false = only where named.",
                         mod=("string", "mod id", True), name=("string", "name", True), slug=("string", "existing slug to change"), title=("string", "title line"),
                         image=("string", "portrait picture path"), portrait=("string", "avatar:/asset: reference"), deck=("string", "deck"),
                         random_size=("integer", "random deck size 10-100"), difficulty=("string", "difficulty"), temperament=("string", "personality"),
                         practice=("boolean", "can appear in random Practice")),
                      lambda a: __import__("tesl_suite.opponents", fromlist=["save_opponent"]).save_opponent(a["mod"],
                          {k: a.get(k) for k in ("slug", "name", "title", "portrait", "deck", "random_size", "difficulty", "temperament", "practice")}, a.get("image"))),
    "search_mods": (_s("Search every mod by words: cards, decks, avatars, AI opponents, card backs, boards, music, sounds, modes, stories, replaced game images "
                       "(with which enabled mod's replacement the game shows).", query=("string", "words to find", True)),
                    lambda a: __import__("tesl_suite.search", fromlist=["search"]).search(a["query"])),
    "list_opponents": (_s("AI opponents in a mod.", mod=("string", "mod id", True)),
                       lambda a: __import__("tesl_suite.opponents", fromlist=["list_opponents"]).list_opponents(a["mod"])),
    "remove_opponent": (_s("Remove an AI opponent.", mod=("string", "mod id", True), name=("string", "name or slug", True)),
                        lambda a: __import__("tesl_suite.opponents", fromlist=["remove"]).remove(a["mod"], a["name"])),
    "story_options": (_s("What a story can use: templates (DBH, CWC, IOM), installed story maps, location discs and AI portraits (as asset: paths), reward kinds, "
                          "and the battle options (lanes, decks, difficulties, turn rules).", mod=("string", "mod id")),
                       lambda a: __import__("tesl_suite.stories", fromlist=["options"]).options(api._game(), a.get("mod"))),
    "list_stories": (_s("A mod's stories with act/chapter/event/battle counts.", mod=("string", "mod id", True)),
                     lambda a: __import__("tesl_suite.stories", fromlist=["list_stories"]).list_stories(a["mod"])),
    "new_story": (_s("Create a story (played from Play > Story in the offline game) with a first act, chapter, dialogue event and battle.",
                     mod=("string", "mod id", True), name=("string", "story name", True), description=("string", "one line"),
                     template=("string", "DBH (default), CWC or IOM: the installed story whose screens and default art it borrows")),
                  lambda a: __import__("tesl_suite.stories", fromlist=["new_story"]).new_story(a["mod"], a["name"], a.get("description") or "", a.get("template") or "DBH")),
    "get_story": (_s("A story's full JSON and the image/voice files in its folder.", mod=("string", "mod id", True), story=("string", "story slug", True)),
                  lambda a: (lambda s: {"story": s.read_story(a["mod"], a["story"]), **s.files(a["mod"], a["story"])})(__import__("tesl_suite.stories", fromlist=["read_story"]))),
    "save_story": (_s("Validate and save a whole story. Shape: {name, description, template, icon, acts: [{slug, name, description, chapters: [{slug, name, subtitle, "
                      "map (file in the story folder or 'asset:<installed path>'), intro: [lines], ending: [lines], events: [{slug, name, x, y (0..1 of the map picture), "
                      "coin (image), requires: [{event: 'slug' | 'chapter/event' | 'act/chapter/event', choice: 1-3, when: intro|ending}], required (counts for chapter "
                      "completion; default: unless it needs a choice), intro/ending: [lines], battle: {game-mode setup as save_mode + opponent_name, opponent_portrait "
                      "(image, asset: or 'ai:<installed opponent>'), briefing, briefing_image, victory_lines: [{speaker, text, portrait}]}, battles: [{...battle, requires: "
                      "the intro choice that picks it}], rewards: [{gold}|{card, count}|{pack}|{xp}|{gems}]}]}]}]}. Line: {speaker, text, portrait, voice (file), end, "
                      "requires, choices: [{text, description, card, gold, requires}] (max 3; a line without choices gets Continue)}.",
                      mod=("string", "mod id", True), story=("object", "the whole story", True)),
                   lambda a: __import__("tesl_suite.stories", fromlist=["save_story"]).save_story(a["mod"], a["story"], api._game())),
    "add_story_file": (_s("Copy an image (PNG/JPG) or voice line (WAV/OGG; MP3/FLAC/M4A converted) into a story's folder; then name it in the story.",
                          mod=("string", "mod id", True), story=("string", "story slug", True), file=("string", "path on this computer", True), name=("string", "file name")),
                       lambda a: __import__("tesl_suite.stories", fromlist=["add_file"]).add_file(a["mod"], a["story"], a["file"], a.get("name"))),
    "board_map": (_s("What can be edited on a game board (Original, IsleOfMadness, AllianceWar, Elsweyr, RealmsOfOblivion): objects with paths and a spot "
                     "on the board picture (x, y 0..1), lights, particle effects, animations, textures.", base=("string", "board", True)),
                  lambda a: __import__("tesl_suite.board_edit", fromlist=["board_map"]).board_map(a["base"])),
    "edit_board": (_s("Change or add things on a mod board (make one first with new_board; image optional). kind: object {path, hide, pos, rot, scale, offset, tint, glow, image} | "
                      "texture {texture, image} | light {path, enabled, color, intensity, range_} | lighting {brightness, tint} | effect {path, enabled, color, speed, rate, size} | "
                      "animation {path, enabled, speed} | model {model: file (OBJ/GLB/glTF, or FBX/.blend/DAE/3DS/STL/PLY/USD via Blender), x, y, fit, rot, texture, tint, glow, motion} | "
                      "image {image, x, y, width, rot} | add-light {x, y, height, kind point|spot, color, intensity, range_} | add-effect {preset embers|mist|fireflies|sparks|snow|magic|smoke|bubbles, "
                      "x, y, color, rate, size, speed, area} | move {item, x, y, rot, fit, motion} | take {item}. Any edit with reset=true undoes it. motion: spin|bob|sway|pulse|float. "
                      "Colours '#rrggbb'. x/y: spot on the board picture (0..1, from the top left).",
                      mod=("string", "mod id", True), board=("string", "mod board", True), kind=("string", "what to do (see description)", True),
                      args=("object", "that kind's fields", True)),
                   lambda a: (lambda be: {"object": be.edit_object, "texture": be.edit_texture, "light": be.edit_light, "lighting": be.edit_lighting, "effect": be.edit_effect,
                                          "animation": be.edit_animation, "model": be.add_model, "image": be.add_image, "add-light": be.add_light, "add-effect": be.add_effect,
                                          "move": be.move_added, "take": be.remove_added}[a["kind"]](a["mod"], a["board"], **(a.get("args") or {})))(
                       __import__("tesl_suite.board_edit", fromlist=["edit_object"]))),
    "replace_art": (_s("Remaster: replace an original image (a card's art, or any texture by asset path). Shown at the original size.",
                       mod=("string", "mod id", True), image=("string", "path to the new image", True), card=("string", "card name or id"),
                       asset=("string", "asset path (see search_assets)"), fit=("string", "crop (default) or stretch")),
                    lambda a: replace.add(api._game(), a["mod"], a["image"], a.get("asset"), a.get("card"), a.get("fit") or "crop")),
    "search_assets": (_s("Search the game's assets by plain words: each result has a label (what it is and what it belongs to: 'Brynjolf - art', "
                         "'Elsweyr board - Incense Burner - normal map', 'Altar of Silence - lane icon'), its category, its asset path and how a mod can "
                         "change it (change: remaster, sounds, cardback, board, music, or empty).",
                         q=("string", "words in the label or path"), category=("string", "card-art, card-effect, avatar, ai-portrait, deck-art, card-back, story, quest, "
                         "board, lane, pack, interface, music, sound, font, shader, text, other"), kind=("string", "texture, audio, model, material, prefab, animation..."),
                         changeable=("boolean", "only assets a mod can change"), limit=("integer", "max results (default 50)")),
                      lambda a: __import__("tesl_suite.catalog", fromlist=["search"]).search(api._game(), a.get("q"), a.get("category"), a.get("kind"),
                          bool(a.get("changeable")), int(a.get("limit") or 50))),
    "export_card_art": (_s("Export a card's original art to a PNG file and return its path (for reference or remastering).",
                           card_id=("integer", "numeric card id (see search_cards)", True)),
                        lambda a: {"file": str(api.card_art(int(a["card_id"]), "full") or "")}),
}


def handle(msg: dict) -> dict | None:
    method, mid = msg.get("method"), msg.get("id")
    if method == "initialize":
        result = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                  "serverInfo": {"name": "tesl-modding-suite", "version": __version__},
                  "instructions": "TESL Forge: make cards, decks, avatars, emotes, card backs and remasters for the offline "
                                  "Elder Scrolls: Legends. Typical flow: new_mod -> search_cards (templates/rule donors) -> new_card "
                                  "(with art paths) -> new_deck (50+ cards) -> validate_mod -> set_mod_enabled."}
    elif method == "tools/list":
        result = {"tools": [{"name": n, "description": s["description"], "inputSchema": {k: v for k, v in s.items() if k != "description"}}
                            for n, (s, _) in TOOLS.items()]}
    elif method == "tools/call":
        name, args = msg["params"]["name"], msg["params"].get("arguments") or {}
        if name not in TOOLS:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"unknown tool {name}"}}
        try:
            from . import fsutil
            with api.LOCK, fsutil.operation("agent: " + name):
                out = TOOLS[name][1](args)
            result = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, indent=1, default=str)}]}
        except Exception as e:  # noqa: BLE001 - tool errors are results the agent can read
            result = {"content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}], "isError": True}
    elif method in ("ping",):
        result = {}
    elif mid is None:      # notifications (initialized, cancelled): no reply
        return None
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def main() -> None:
    out = sys.stdout
    sys.stdout = sys.stderr          # anything printed by the suite goes to stderr, never into the protocol stream
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except Exception:  # noqa: BLE001
            traceback.print_exc()
            continue
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()


if __name__ == "__main__":
    main()
