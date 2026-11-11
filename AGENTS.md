# Using TESL Forge as an AI agent

**MCP (best for agents):** this folder's `.mcp.json` registers the suite's MCP server (`tesl` tools: new_mod, search_cards,
new_card, new_deck, new_avatar, set_avatar_emote, new_cardback, replace_art, validate_mod, set_mod_enabled, ...). Elsewhere:
`claude mcp add tesl -- "<suite>\.venv\Scripts\python.exe" -X utf8 -m tesl_suite.mcp_server`; for Codex add the same command
under `[mcp_servers.tesl]` in `~/.codex/config.toml`. Image and audio arguments are file paths.

Run `tesl.cmd` (or `.venv\Scripts\python -X utf8 -m tesl_suite.cli`) from this folder. `tesl serve --no-browser` starts the
local HTTP API (127.0.0.1:8765, JSON in and out; endpoint list at the top of `tesl_suite/api.py`), the same functions the
app and the CLI use; upload files with `POST /api/upload` (raw body, `X-Filename` header) and pass the returned path. Always pass `--json`: results are a
single JSON object on stdout; failures exit non-zero with `{"error": "..."}`.

| Goal | Command |
|---|---|
| Find the game and workspace | `tesl --json info` |
| Rebuild the asset index | `tesl --json assets index` |
| Search assets | `tesl --json assets list --kind texture --contains <text> [--bundle <prefix>] [--limit N]` |
| Extract assets | `tesl --json assets export --kind <kind> --contains <text> --out <folder>` |
| Extract card art with names | `tesl --json assets export-card-art [--contains <name>] [--collectible] --out <folder>` |
| Look up cards | `tesl --json cards list --contains <name> [--set <set>] [--collectible]` |
| New mod | `tesl --json mod new <mod-id> --name "<name>"` |
| New card | `tesl --json card new --mod <mod-id> --name "<name>" --template "<existing card>" [--cost N --attack N --health N] [--rarity R] [--text "..."] [--rules-from "<card whose rules to copy>"] [--no-rules] [--art <png/jpg>]` |
| A card's abilities (rule editor) | `tesl --json card abilities "<card>"` (ids like `triggered:0`, editable parameters with paths) |
| Card with built rules | `tesl --json card new ... --keywords "Guard,Charge,Rally=2" --abilities '[{"card": "Fiery Imp", "ability": "triggered:0", "params": {"<path>": 3}}]'` |
| New deck | `tesl --json deck new --mod <mod-id> --name "<name>" --cards "Card A x3, Card B x2, ..." [--art-card "<card>"]` |
| Replace an original image (remaster) | `tesl --json replace image --mod <mod-id> (--card "<card>" \| --asset <asset path>) --image <png/jpg> [--fit crop\|stretch]` |
| List / undo replacements | `tesl --json replace list --mod <mod-id>` / `tesl --json replace remove --mod <mod-id> --asset <path>` |
| New avatar choice | `tesl --json avatar new --mod <mod-id> --name "<name>" --image <png/jpg> [--voice <original avatar>] [--head 0.22] [--profile <png/jpg>]` (`--profile`: own picture for the round profile portrait) |
| Avatar page name / voices / list | `tesl --json avatar page --mod <mod-id> --name "..." [--description "..."]`, `tesl --json avatar voices`, `tesl --json avatar list --mod <mod-id>` |
| Avatar emote line (text/voice) | `tesl --json avatar emote --mod <mod-id> --avatar "<name>" --emote Hello\|GoodGame\|Implore\|Taunt\|Oops\|NicePlay\|ThankYou\|Sorry [--text "..."] [--audio <wav/mp3/ogg>]` |
| New card back | `tesl --json cardback new --mod <mod-id> --name "<name>" --image <png/jpg> [--price <gold>] [--unlock "..."] [--size 1024\|2048]` |
| Card backs list / remove | `tesl --json cardback list --mod <mod-id>` / `tesl --json cardback remove --mod <mod-id> --name "<name>"` |
| New board | `tesl --json board new --mod <mod-id> --name "<name>" --image <wide image> [--base Original\|IsleOfMadness\|AllianceWar\|Elsweyr\|RealmsOfOblivion] [--mode rotation\|replace] [--size 2048\|4096]` |
| Board map | `tesl --json board map --base Original\|IsleOfMadness\|AllianceWar\|Elsweyr\|RealmsOfOblivion` (objects with paths and a spot on the board picture, lights, effects, animations, textures; MCP `board_map`) |
| Edit a board | `tesl --json board edit object\|texture\|light\|lighting\|effect\|animation --mod <mod-id> --board <board> ...` (hide/move/rotate/resize/tint/glow/retexture props; `--reset` undoes; MCP `edit_board`) |
| Add to a board | `tesl --json board add model\|image\|light\|effect --mod <mod-id> --board <board> --x 0..1 --y 0..1 ...` (models: OBJ, GLB/glTF, zip; FBX/.blend/DAE/3DS/STL/PLY/USD via Blender; effects: embers, mist, fireflies, sparks, snow, magic, smoke, bubbles; `--motion spin\|bob\|sway\|pulse\|float`); `board move` / `board take` |
| Game mode | `tesl --json mode save --mod <mod-id> --name "<name>" --lane Plunder:4 --lane Windy --player-health 25 --player-magicka 3 --player-card "lane1:<card>" --opponent-deck random --draw-per-turn 1 --reward-gold 50 ...` (lanes: `tesl mode lanes`; MCP `mode_options`, `save_mode`; played via F10 > Practice mode, then Play > Practice) |
| Story | `tesl --json story new --mod <mod-id> --name "<name>"`, then edit `mods/<mod>/stories/<slug>/story.json` (or MCP `get_story` / `save_story`) and `tesl story save --mod <mod-id> --file story.json`; images and voice lines: `tesl story file --mod <mod-id> --story <slug> --file <path>`; installed maps/discs/portraits: `tesl story options`; check: `tesl story check --mod <mod-id>`. Played from Play > Stories. |
| Compatibility | `tesl --json mod check` (load order the game uses, skipped mods and why, overlaps, class, fingerprint); `tesl mod order --set a,b` or `--auto`; `tesl mod enable <id>` refuses a mod the game would skip (`--force` to override). Manifest fields in mod.json: `version`, `dependencies` [{id, version: ">=1.2"}], `conflicts`, `load_after`, `load_before`, `requires_engine` (stamped automatically). MCP `check_mod_compatibility`, `set_mod_load_order`. |
| New soundtrack | `tesl --json music add --mod <mod-id> --name "<name>" --file <any audio> --context MainMenuState [--context Board:Elsweyr ...] [--mode replace\|rotation] [--volume 0.8]` (places: `tesl music contexts --mod <mod-id>`; MCP `new_music_track`, `music_contexts`) |
| Find a game sound | `tesl --json sound search <words> [--category card-voice\|card-sfx\|emote\|board-dialogue\|story\|announcer\|cinematic\|ui]` (MCP `search_sounds`) |
| Find any asset by name | `tesl --json assets find <words> [--category card-art\|avatar\|ai-portrait\|deck-art\|story\|quest\|board\|lane\|interface\|...] [--changeable]` (labels say what each asset is and `change` how a mod can change it; MCP `search_assets`) |
| Replace a game sound | `tesl --json sound replace --mod <mod-id> --sound <id from search> --file <audio> [--file <another> ...]` (all takes and languages; several files = random pick; MCP `replace_sound`) |
| Mod card voice line | `tesl --json sound card-voice --mod <mod-id> --card "<card>" --line Play\|Attack\|Death\|Hit\|Success\|Failure --file <audio>` (unset lines keep the template card's voice; MCP `card_voice`) |
| Extra emote | `tesl --json emote add --mod <mod-id> --text "<line>" [--label "<button>"] [--avatar <mod avatar>] [--audio <clip>] [--like Taunt]` (no avatar = every avatar; like = AI variant; MCP `add_extra_emote`) |
| Check / turn on a mod | `tesl --json mod validate <mod-id>` then `tesl --json mod enable <mod-id>` (the game reads it at its next start) |

Kinds: texture, model, audio, material, prefab, animation, shader, font, text, other.

Rules for agents:
- Avatars: give a tall full-body portrait (the game's shape is 286:512; any resolution). The suite also cuts a round
  head-and-shoulders portrait for the profile and match intro (`--head` moves it). A mod's avatars get their own pages
  in the avatar picker, four per page. `--voice` borrows an original avatar's emote voice lines.
- Emotes: each avatar has 8 emote lines. `avatar emote` sets the avatar's own text and/or voice for one (audio is converted
  to WAV with ffmpeg if needed); lines it doesn't set keep its `--voice`. The AI opponent uses its avatar's lines too and
  emotes by temperament (friendly, cocky, playful, stoic): it opens, reacts to big hits, wiped boards, near-death and slow
  turns, and answers the player's emotes.
- Card backs: any number per mod. The image is cropped into the game's card shape (portrait, about 4:7). Price 0 = free for
  everyone with the mod; a price sells it for gold in the offline store (Special Offers). Selected in Collection > card backs.
- Rule editor: a card's rules = keywords + abilities copied from any cards, with amounts and card references changed
  (`card abilities` lists them). The engine plays these natively. Read `notes` in the result: when a changed number
  can't be rewritten in the text safely, set `--text` yourself. A mechanic no card has needs engine work.
- Image replacement works for images the game loads by path: card art, avatars, deck banners, arena/profile images
  (find them with `assets list --kind texture`). Export the original first (`assets export`) and keep its framing; any
  resolution works (the game shows it at the original size). Not yet: premium (animated) card versions, which use
  their own materials, sprites packed into shared atlases (refused), and UI textures built into prefabs.
- Never write into the game folder (the suite refuses). Use `--out` under the workspace or a folder the user names.
- Card ids, names and rules come from the original card JSON; `card new` writes that same shape. Pick a template whose
  ability matches what the user wants (search with `cards list --contains`), or combine a template's body with
  `--rules-from`. The card text should describe the rules it actually has; pass `--text` only for wording changes.
- Generated art (any image service) is passed with `--art`; the suite crops and resizes it. Keep originals untouched.
- Example: "make a deck of Skyrim characters" -> generate portraits, `mod new`, one `card new` per character with fitting
  templates/`--rules-from`, `deck new` with 50+ cards, `mod validate`, `mod enable`.
- Deck rules are the game client's own: 50-70 cards with one or two attributes; three attributes need 75-100 cards and
  at least one three-attribute card; at most 3 copies (1 if unique); collectible cards only (no tokens). `deck new` and
  `mod validate` refuse decks that break them, because the game would mark the deck invalid (a warning sign, unplayable).
- `--art-card` picks the deck's banner. When it is a mod card with art, the suite cuts the two crops the game uses for
  decks (a 512x128 list banner and a 256x512 portrait); otherwise the deck uses that card's original art.
- How mod cards look in game: the frame, cost gem, name banner, type line, attribute icon and rules text are drawn by
  the game from the card data, exactly as for original cards. Only the art is yours, so supply painted portrait art
  (square, subject centred with headroom; the hand shows the upper part, the board a centred portrait crop).

**Tests.** After changing TESL Forge, run `.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -v` from the TESL Forge folder
(standard library only, about 2 seconds). They work on throwaway copies of the sample mod and leave mods and the enabled-mod list unchanged.
