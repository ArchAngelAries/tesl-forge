"""Local HTTP API and web app server: `tesl serve`. Binds to 127.0.0.1 only. Every endpoint is a thin wrapper over the same
functions the CLI uses, so the app, agents (HTTP + JSON) and the CLI behave identically.

GET  /api/settings, POST /api/settings          this computer's settings (extra game folders, Blender/ffmpeg paths; workspace/settings.json)
GET  /api/info                                  game, workspace, suite version
GET  /api/mods                                  all mods with counts and enabled state
POST /api/mods                                  {id, name, author?, description?}
GET  /api/mods/<id>                             everything in a mod (cards, decks, avatars, card backs, replacements, validation)
POST /api/mods/<id>/enable | /disable           (enable: body {"force": true} to enable despite compatibility errors)
GET  /api/compat                                load order, skipped mods, overlaps, per-mod class and fingerprint
POST /api/mods/install                          {"source": uploaded path | folder | https link, "enable", "force"}
POST /api/mods/<id>/export                      a shareable .zip (returns its path; GET /api/mods/<id>/export.zip downloads it)
POST /api/mods/<id>/uninstall                   moved to workspace/trash
POST /api/compat/order                          {"order": [ids]} or {"auto": true}
POST /api/mods/<id>/cards                       {name, template, cost?, attack?, health?, text?, rarity?, art?, rules_from?, no_rules?, unique?}
POST /api/mods/<id>/decks                       {name, cards: "Name x3; Other x2" (";", new lines or commas) or ["Name x3", {name|id, count}], art_card?, description?}
POST /api/mods/<id>/avatars                     {name, image, voice?, head?}
POST /api/mods/<id>/avatars/<slug>/emotes       {emote, text?, audio?}
DELETE /api/mods/<id>/avatars/<slug>
POST /api/mods/<id>/avatar-page                 {name?, description?}
POST /api/mods/<id>/cardbacks                   {name, image, price?, unlock?, size?}
DELETE /api/mods/<id>/cardbacks/<slug>
POST /api/mods/<id>/replace                     {image, card? | asset?, fit?}
DELETE /api/mods/<id>/replace?asset=<path>
GET  /api/cards?q=&set=&type=&collectible=1&limit=&offset=      original card catalog (plus mod cards with ?mods=1)
GET  /api/cards/<id>/art?size=thumb|full         original card art (exported from the bundles once, then cached)
GET  /api/voices                                original avatars usable as emote voices
GET  /api/assets?kind=&q=&limit=                asset index search
GET  /api/assets/preview?path=<bundle path>     a texture as PNG (cached)
POST /api/upload  (raw body, header X-Filename) a file into workspace/uploads; returns {path} for the other calls
GET  /mod-file/<id>/<path>                       a file from a mod folder (images, audio)
"""
from __future__ import annotations

import json
import mimetypes
import re
import threading
import time
import traceback
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, assets, avatars, boards, cardbacks, cards, mods, music, replace, sounds
from .game import find_install, workspace

WEB = Path(__file__).parent / "web"
LOCK = threading.RLock()          # one write at a time (mod files)
EXPORT = threading.Lock()         # bundle reads (UnityPy) one at a time: parallel previews of one bundle failed
_state: dict = {}


def _game():
    if "game" not in _state:
        _state["game"] = find_install(_state.get("game_path"))
    return _state["game"]


def _catalog() -> list[dict]:
    if "catalog" not in _state:
        _state["catalog"] = cards.catalog(_game())
    return _state["catalog"]


def _index() -> dict:
    if "index" not in _state:
        _state["index"] = assets.load_index(_game())
    return _state["index"]


def _cache(kind: str) -> Path:
    d = workspace() / "cache" / kind
    d.mkdir(parents=True, exist_ok=True)
    return d


def info() -> dict:
    game = _game()
    return {"version": __version__, "game": game.root, "workspace": str(workspace()), "mods_dir": str(mods.MODS)}


# ---- helpers used by the routes ------------------------------------------------------------------------------------------
def mod_detail(mod_id: str) -> dict:
    meta = mods.read_mod(mod_id)
    root = mods.mod_dir(mod_id)
    from . import previews as _previews
    previews_dir = _previews.folder(mod_id)
    mod_cards = []
    for c in mods.mod_cards(mod_id):
        s = cards.summarize(c, "Mod_" + mod_id)
        slug = c.get("ResourceId", {}).get("UniqueName", "")
        s["slug"] = slug
        s["art"] = f"/mod-file/{mod_id}/art/{slug}.png" if (root / "art" / f"{slug}.png").is_file() else None
        pv = previews_dir / f"{slug}.png"
        s["preview"] = f"/api/mods/{mod_id}/previews/{slug}.png?t={int(pv.stat().st_mtime)}" if pv.is_file() else None
        s["preview_stale"] = bool(s["preview"]) and any(f.stat().st_mtime > pv.stat().st_mtime for f in (root / "cards" / f"{slug}.json", root / "art" / f"{slug}.png") if f.is_file())
        mod_cards.append(s)
    decks = []
    for p in sorted((root / "decks").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        art = (d.get("deck_art") or {}).get("tile")
        decks.append({"slug": p.stem, "name": d.get("name"), "cards": d.get("cards", []),
                      "total": sum(e.get("count", 0) for e in d.get("cards", [])),
                      "banner": f"/mod-file/{mod_id}/art/{art}" if art else (f"/api/cards/{d['art_card']}/art?size=thumb" if d.get("art_card") else None),
                      "preview": _previews.preview_url(mod_id, "decks", p.stem)})
    av = avatars.list_avatars(mod_id)
    for a in av["avatars"]:
        a["image_url"] = f"/mod-file/{mod_id}/avatars/{a['image']}"
        a["circle_url"] = f"/mod-file/{mod_id}/avatars/{a['circle']}"
    cb = cardbacks.list_cardbacks(mod_id)["cardbacks"]
    for c in cb:
        c["image_url"] = f"/mod-file/{mod_id}/cardbacks/{c.get('store') or c['image']}"
        c["preview"] = _previews.preview_url(mod_id, "backs", c["slug"])
    bd = boards.list_boards(mod_id)["boards"]
    for b in bd:
        b["image_url"] = f"/mod-file/{mod_id}/boards/{b['image']}" if b.get("image") else None
        b["preview"] = _previews.preview_url(mod_id, "boards", b["slug"])
    mu = music.list_tracks(mod_id)["tracks"]
    for t in mu:
        t["audio_url"] = f"/mod-file/{mod_id}/music/{t['file']}"
    ex = avatars.list_extra_emotes(mod_id)
    from . import modes as _modes
    md = _modes.list_modes(mod_id)["modes"]
    from . import stories as _stories
    st = _stories.list_stories(mod_id)["stories"]
    sd = sounds.list_replacements(mod_id)["sounds"]
    for s in sd:
        s["audio_urls"] = [f"/mod-file/{mod_id}/audio/{f}" for f in s["files"]]
    cv = sounds.card_voices(mod_id)["cards"]
    for c in cv:
        c["line_urls"] = {k: (f"/mod-file/{mod_id}/{v}" if v else None) for k, v in c["lines"].items()}
    rp = replace.list_replacements(mod_id)["images"]
    for r in rp:
        r["image_url"] = f"/mod-file/{mod_id}/replace/{r['file']}"
    from . import opponents as _opp
    op = _opp.list_opponents(mod_id)["opponents"]
    for o in op:
        p = o.get("portrait") or ""
        o["image_url"] = (f"/mod-file/{mod_id}/avatars/{next((a['image'] for a in av['avatars'] if a['slug'] == p[7:]), '')}" if p.startswith("avatar:")
                          else f"/mod-file/{mod_id}/opponents/{p}" if p and ":" not in p else None)
    from . import packs as _packs
    pk = _packs.list_packs(mod_id)["packs"]
    for x in pk:
        x["image_url"] = f"/mod-file/{mod_id}/packs/{x['art']}" if x.get("art") else None
    listing = mods.list_mods()
    choices = [{"key": k, "label": k} for k in _opp.keys([mod_id] + [m["id"] for m in listing if m["enabled"] and m["id"] != mod_id])]
    for c in choices:
        if c["key"].startswith(mod_id + "/"):
            c["label"] = next((o["name"] for o in op if f"{mod_id}/{o['slug']}" == c["key"]), c["key"]) + " (this mod)"
    enabled = next((m["enabled"] for m in listing if m["id"] == mod_id), False)
    return {"mod": meta, "enabled": enabled, "cards": mod_cards, "decks": decks, "avatars": av["avatars"], "avatar_page": av.get("page", {}),
            "opponents": op, "opponent_choices": choices, "packs": pk, "cardbacks": cb, "boards": bd, "board_bases": list(boards.BASES), "music": mu, "music_contexts": music.contexts(mod_id), "sounds": sd, "card_voices": cv, "voice_slots": sounds.ALL_SLOTS, "extra_emotes": ex, "emote_types": list(avatars.EMOTE_TYPES), "modes": md, "stories": st, "replacements": rp, "validation": mods.validate(_game(), mod_id)}


def card_abilities(ref: str) -> dict:
    from . import rules
    card = mods.find_card(_game(), ref)
    return {"id": card["ResourceId"]["Id"], "name": card.get("Name"), "text": card.get("Description"), "type": card.get("Definition"),
            "abilities": rules.abilities_of(card), "keywords": rules.keywords_of(card)}


def card_query(q: dict) -> dict:
    rows = _catalog()
    text = (q.get("q") or "").strip().lower()
    if text:
        rows = [c for c in rows if text in (c["name"] or "").lower() or text in (c["text"] or "").lower() or text == str(c["id"])]
    if q.get("set"):
        rows = [c for c in rows if c["set"] == q["set"]]
    if q.get("type"):
        rows = [c for c in rows if c["type"] == q["type"]]
    if q.get("collectible") in ("1", "true"):
        rows = [c for c in rows if c["collectible"] and not c["alternate_of"]]
    if q.get("art") in ("1", "true"):
        rows = [c for c in rows if c["image"]]
    if q.get("attribute"):
        rows = [c for c in rows if q["attribute"] in (c["subtypes"] or [])]
    if q.get("cost") not in (None, ""):
        want = int(q["cost"])
        rows = [c for c in rows if (c["cost"] or 0) == want or (want >= 7 and (c["cost"] or 0) >= 7)]
    rows = sorted(rows, key=lambda c: ((c["cost"] or 0), c["name"] or ""))
    offset, limit = int(q.get("offset") or 0), min(int(q.get("limit") or 60), 500)
    return {"total": len(rows), "offset": offset, "cards": rows[offset:offset + limit],
            "sets": sorted({c["set"] for c in _catalog() if c["set"]})}


def card_art(card_id: int, size: str) -> Path | None:
    """Original card art, exported from its bundle the first time, then a 320 px thumbnail."""
    full = _cache("card-art") / f"{card_id}.png"
    if not full.is_file():
        card = next((c for c in _catalog() if c["id"] == card_id), None)
        if not card or not card["image"]:
            return None
        by_path = assets.by_path(_index())
        entry = next((by_path[p] for p in cards.art_asset_paths(card["image"]) if p in by_path), None)
        if entry is None:
            return None
        with EXPORT:
            if not full.is_file():
                res = assets.export(_game(), [entry], _cache("card-art"), naming=lambda e: str(card_id))
                if not res or "file" not in res[0]:
                    return None
    if size != "thumb":
        return full
    thumb = _cache("card-thumbs") / f"{card_id}.jpg"
    if not thumb.is_file():
        from PIL import Image
        im = Image.open(full).convert("RGB")
        im.thumbnail((320, 320))
        im.save(thumb, quality=86)
    return thumb


def asset_preview(path: str) -> Path | None:
    entry = next((e for e in _index()["entries"] if e["path"] == path), None)
    if entry is None or entry["kind"] != "texture":
        return None
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", path)[-120:]
    out = _cache("asset-previews") / (name + ".png")
    if not out.is_file():
        with EXPORT:
            if not out.is_file():
                res = assets.export(_game(), [entry], _cache("asset-previews"), naming=lambda e: name)
                if not res or "file" not in res[0]:
                    return None
                produced = Path(res[0]["file"])
                if produced != out and produced.is_file():
                    produced.replace(out)
    return out


def sound_preview(path: str) -> Path | None:
    """An original sound exported once to the cache, for listening in the app."""
    entry = next((e for e in _index()["entries"] if e["path"] == path), None)
    if entry is None or entry["kind"] != "audio":
        return None
    out = _cache("sound-previews")
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", path)[-120:]
    done = out / (name + Path(path).suffix)
    if not done.is_file():
        with EXPORT:
            if not done.is_file():
                res = assets.export(_game(), [entry], out / "tmp")
                files = res[0].get("files") if res else None
                if not files:
                    return None
                Path(files[0]).replace(done)
    return done


def save_upload(name: str, data: bytes) -> dict:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", Path(name or "upload").name) or "upload"
    d = workspace() / "uploads"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{int(time.time() * 1000)}-{safe}"
    dest.write_bytes(data)
    return {"path": str(dest), "name": safe, "bytes": len(data)}


def _deck_spec(cards_field):
    """Deck list from the app/API/MCP: text (entries split on ";", new lines or commas), or a real list of "Name x3" strings
    and {name|id, count} objects. A list goes through unchanged, so card names with commas stay whole."""
    if isinstance(cards_field, str):
        return cards_field
    return list(cards_field or [])


def _int(v):
    return None if v in (None, "") else int(v)


# ---- HTTP ----------------------------------------------------------------------------------------------------------------
def _label(method: str, p: list) -> str:
    """A readable name for an undo step: "stories (save)", "cards (new)", "boards/greenwood-table (delete)"."""
    if len(p) >= 3 and p[0] == "mods":
        what = "/".join(p[2:4])
        return f"{what} ({'delete' if method == 'DELETE' else 'change'})"
    return "/".join(p[:3]) or "change"


class Handler(BaseHTTPRequestHandler):
    server_version = "TESLModdingSuite/" + __version__

    def log_message(self, fmt, *args):   # quiet; errors still go to stderr through send_error paths
        pass

    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # The app's own files change with the suite: never cached. Images are, briefly.
        self.send_header("Cache-Control", "max-age=60" if ctype.startswith(("image/", "audio/")) else "no-cache")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200):
        self._send(code, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _file(self, path: Path | None):
        if path is None or not path.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        size = path.stat().st_size
        if size < (4 << 20):
            return self._send(200, path.read_bytes(), ctype)
        self.send_response(200)   # large files (exports, music, models) are streamed
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.end_headers()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(1 << 20)
                if not chunk:
                    break
                self.wfile.write(chunk)

    def _body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def _payload(self) -> dict:
        raw = self._body()
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _allowed(self, method: str) -> str | None:
        """Only this computer's own app may use the API: the Host must be the local address and port (stops DNS-rebinding
        pages), and changes must come from the app's own page (a browser always sends Origin on cross-site requests)."""
        port = self.server.server_address[1]
        local = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
        if (self.headers.get("Host") or "").lower() not in local:
            return "this server only answers requests addressed to this computer"
        if method != "GET":
            origin = self.headers.get("Origin")
            if origin and origin.lower() not in {"http://" + h for h in local}:
                return "changes are only accepted from TESL Forge itself"
        return None

    def _route(self, method: str):
        why = self._allowed(method)
        if why:
            return self._json({"error": why}, 403)
        url = urllib.parse.urlparse(self.path)
        parts = [urllib.parse.unquote(p) for p in url.path.strip("/").split("/") if p]
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(url.query).items()}
        try:
            if not parts or parts[0] not in ("api", "mod-file"):
                return self._static(parts)
            if parts[0] == "mod-file":
                return self._mod_file(parts[1:])
            if method == "GET":
                return self._api(method, parts[1:], q)
            from . import fsutil
            with LOCK, fsutil.operation(_label(method, parts[1:])):   # every change runs alone and is one undo step
                return self._api(method, parts[1:], q)
        except (ValueError, KeyError, FileNotFoundError, FileExistsError, PermissionError, IndexError, TypeError, AssertionError) as e:
            return self._json({"error": f"{type(e).__name__}: {e}"}, 400)
        except Exception as e:  # noqa: BLE001 - report every failure to the app
            traceback.print_exc()
            return self._json({"error": f"{type(e).__name__}: {e}"}, 500)

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    def _static(self, parts):
        rel = "/".join(parts) or "index.html"
        path = (WEB / rel).resolve()
        if WEB.resolve() not in path.parents and path != WEB.resolve():
            return self._json({"error": "not found"}, 404)
        if not path.is_file():
            path = WEB / "index.html"
        return self._file(path)

    def _mod_file(self, parts):
        if len(parts) < 2:
            return self._json({"error": "not found"}, 404)
        root = mods.mod_dir(parts[0]).resolve()
        path = (root / "/".join(parts[1:])).resolve()
        if root not in path.parents:
            return self._json({"error": "not found"}, 404)
        return self._file(path)

    def _api(self, method, p, q):
        g = _game
        if method == "GET" and p == ["info"]:
            return self._json(info())
        if p == ["settings"]:
            from . import settings as _settings
            if method == "POST":
                return self._json(_settings.save(self._payload()))
            return self._json({**_settings.load(), "blender_found": _settings.find_blender(), "ffmpeg_found": _settings.find_tool("ffmpeg"),
                               "file": str(_settings.path())})
        if p and p[0] == "mods":
            if len(p) == 1 and method == "GET":
                return self._json({"mods": mods.list_mods()})
            if len(p) == 1 and method == "POST":
                b = self._payload()
                from . import starters
                with LOCK:
                    return self._json(starters.create(_game(), b["id"], b["name"], b.get("starter") or "blank", b.get("author", ""),
                                                      b.get("description", ""), b.get("source") or None))
            mod_id = p[1]
            if len(p) == 2 and method == "GET":
                return self._json(mod_detail(mod_id))
            what = p[2] if len(p) > 2 else ""
            with LOCK:
                if what in ("enable", "disable") and method == "POST":
                    b = self._payload() if what == "enable" else {}
                    return self._json(mods.set_enabled(mod_id, what == "enable", bool((b or {}).get("force"))))
                if what == "cards" and method == "POST":
                    b = self._payload()
                    return self._json(mods.new_card(g(), mod_id, b["name"], b["template"], _int(b.get("cost")), _int(b.get("attack")),
                                                    _int(b.get("health")), b.get("text") or None, b.get("rarity") or None, b.get("art") or None,
                                                    b.get("rules_from") or None, bool(b.get("no_rules")), b.get("unique"),
                                                    b.get("abilities"), b.get("keywords") or None))
                if what == "decks" and method == "POST":
                    b = self._payload()
                    return self._json(mods.new_deck(g(), mod_id, b["name"], _deck_spec(b.get("cards")), b.get("art_card") or None, b.get("description", "")))
                if what == "avatars" and method == "POST" and len(p) == 3:
                    b = self._payload()
                    return self._json(avatars.new_avatar(mod_id, b["name"], b["image"], b.get("voice") or None, float(b.get("head") or 0.22), b.get("profile") or None))
                if what == "avatars" and len(p) == 5 and p[4] == "emotes" and method == "POST":
                    b = self._payload()
                    return self._json(avatars.set_emote(mod_id, p[3], b["emote"], b.get("text"), b.get("audio") or None))
                if what == "avatars" and len(p) == 4 and method == "DELETE":
                    return self._json(avatars.remove(mod_id, p[3]))
                if what == "avatar-page" and method == "POST":
                    b = self._payload()
                    return self._json(avatars.set_page(mod_id, b.get("name"), b.get("description")))
                if what == "cardbacks" and method == "POST":
                    b = self._payload()
                    return self._json(cardbacks.new_cardback(mod_id, b["name"], b["image"], int(b.get("price") or 0), b.get("unlock") or None, int(b.get("size") or 1024)))
                if what == "cardbacks" and len(p) == 4 and method == "DELETE":
                    return self._json(cardbacks.remove(mod_id, p[3]))
                if what == "boards" and method == "POST":
                    b = self._payload()
                    return self._json(boards.new_board(mod_id, b["name"], b.get("image") or None, b.get("base") or "Original", b.get("mode") or "rotation", int(b.get("size") or 2048)))
                if what == "board-edit" and method == "POST":
                    from . import board_edit as be
                    b = self._payload(); kind = b.pop("action"); board = b.pop("board")
                    fns = {"object": be.edit_object, "texture": be.edit_texture, "light": be.edit_light, "lighting": be.edit_lighting, "effect": be.edit_effect,
                           "animation": be.edit_animation, "model": be.add_model, "image": be.add_image, "add-light": be.add_light, "add-effect": be.add_effect,
                           "move": be.move_added, "take": be.remove_added}
                    if "range" in b:
                        b["range_"] = b.pop("range")
                    return self._json(fns[kind](mod_id, board, **b))
                if what == "boards" and len(p) == 4 and method == "DELETE":
                    return self._json(boards.remove(mod_id, p[3]))
                if what == "modes" and method == "POST":
                    from . import modes as _modes
                    b = self._payload()
                    return self._json(_modes.save_mode(g(), mod_id, b["name"], b.get("description") or "", b.get("lanes"), b.get("player"), b.get("opponent"),
                                                       b.get("first") or "random", b.get("difficulty") or "chosen", b.get("opponent_name") or None, b.get("rules"),
                                                       b.get("board") or None, int(b.get("reward_gold") or 0), b.get("ai") or None))
                if what == "opponents" and method == "POST":
                    from . import opponents as _opp
                    b = self._payload()
                    return self._json(_opp.save_opponent(mod_id, b.get("fields") or {}, b.get("image") or None, float(b.get("head") or 0.22)))
                if what == "opponents" and len(p) == 4 and method == "DELETE":
                    from . import opponents as _opp
                    return self._json(_opp.remove(mod_id, p[3]))
                if what == "packs" and method == "POST":
                    from . import packs as _packs
                    b = self._payload()
                    return self._json(_packs.save_pack(g(), mod_id, b.get("fields") or {}, b.get("image") or None))
                if what == "packs" and len(p) == 4 and method == "DELETE":
                    from . import packs as _packs
                    return self._json(_packs.remove(mod_id, p[3]))
                if what == "pack-options" and method == "GET":
                    from . import packs as _packs
                    return self._json({**_packs.options(), "cards": sorted({c["name"] for c in _catalog() if c.get("name")} | {c.get("Name") for c in mods.mod_cards(mod_id) if c.get("Name")})})
                if what == "opponent-options" and method == "GET":
                    from . import opponents as _opp
                    return self._json(_opp.options(g(), mod_id))
                if what == "modes" and len(p) == 4 and method == "DELETE":
                    from . import modes as _modes
                    return self._json(_modes.remove_mode(mod_id, p[3]))
                if what == "stories":
                    from . import stories as _stories
                    if method == "GET" and len(p) == 3:
                        return self._json(_stories.list_stories(mod_id))
                    if method == "POST" and len(p) == 3:
                        b = self._payload()
                        if b.get("new"):
                            return self._json(_stories.new_story(mod_id, b["name"], b.get("description") or "", b.get("template") or "DBH"))
                        return self._json(_stories.save_story(mod_id, b["story"], g()))
                    if method == "GET" and len(p) == 4:
                        return self._json({"story": _stories.read_story(mod_id, p[3]), **_stories.files(mod_id, p[3])})
                    if method == "DELETE" and len(p) == 4:
                        return self._json(_stories.remove_story(mod_id, p[3]))
                    if method == "POST" and len(p) == 5 and p[4] == "file":
                        b = self._payload()
                        return self._json(_stories.add_file(mod_id, p[3], b["file"], b.get("name") or None))
                if what == "story-options" and method == "GET":
                    from . import stories as _stories
                    o = _stories.options(g(), mod_id)
                    o["cards"] = sorted({c["name"] for c in _catalog() if c.get("name")} | {c.get("Name") for c in mods.mod_cards(mod_id) if c.get("Name")})
                    o["bases"] = list(boards.BASES)
                    return self._json(o)
                if what == "mode-options" and method == "GET":
                    from . import modes as _modes
                    return self._json({"lanes": _modes.lanes(), "decks": _modes.decks(g(), mod_id), "zones": _modes.ZONES, "rules": _modes.RULES,
                                       "difficulties": _modes.DIFFICULTIES, "bases": list(boards.BASES),
                                       "cards": sorted({c["name"] for c in _catalog() if c.get("name")} | {c.get("Name") for c in mods.mod_cards(mod_id) if c.get("Name")})})
                if what == "extra-emotes" and method == "POST":
                    b = self._payload()
                    return self._json(avatars.add_extra_emote(mod_id, b.get("text") or "", b.get("label") or None, b.get("avatar") or None, b.get("audio") or None, b.get("like") or None))
                if what == "extra-emotes" and method == "DELETE":
                    return self._json(avatars.remove_extra_emote(mod_id, q["emote"], q.get("avatar") or None))
                if what == "sounds" and method == "POST":
                    b = self._payload()
                    return self._json(sounds.replace_sound(g(), mod_id, b["sound"], list(b.get("files") or []), float(b.get("volume") or 1.0)))
                if what == "sounds" and method == "DELETE":
                    return self._json(sounds.remove_replacement(mod_id, q["sound"]))
                if what == "card-voice" and method == "POST":
                    b = self._payload()
                    return self._json(sounds.card_voice(mod_id, b["card"], b["line"], b["file"]))
                if what == "card-voice" and method == "DELETE":
                    return self._json(sounds.remove_card_voice(mod_id, q["card"], q["line"]))
                if what == "music" and method == "POST":
                    b = self._payload()
                    return self._json(music.add_track(mod_id, b["name"], b["file"], list(b.get("contexts") or []), b.get("mode") or "replace", float(b.get("volume") or 1.0)))
                if what == "music" and len(p) == 4 and method == "DELETE":
                    return self._json(music.remove(mod_id, p[3]))
                if what == "replace" and method == "POST":
                    b = self._payload()
                    return self._json(replace.add(g(), mod_id, b["image"], b.get("asset") or None, b.get("card") or None, b.get("fit") or "crop"))
                if what == "replace" and method == "DELETE":
                    return self._json(replace.remove(mod_id, q["asset"]))
        if method == "GET" and p == ["cards"]:
            return self._json(card_query(q))
        if method == "GET" and len(p) == 3 and p[0] == "cards" and p[2] == "art":
            return self._file(card_art(int(p[1]), q.get("size", "thumb")))
        if method == "GET" and len(p) == 3 and p[0] == "cards" and p[2] == "abilities":
            return self._json(card_abilities(p[1]))
        if method == "GET" and p == ["keywords"]:
            from . import rules
            return self._json({"keywords": [{"label": l, "attribute": a, "kind": k} for l, a, k in rules.KEYWORDS]})
        if method == "GET" and p == ["voices"]:
            return self._json({"voices": avatars.original_avatars()})
        if method == "GET" and p == ["assets"]:
            rows = assets.query(_index(), q.get("kind") or None, q.get("q") or None)
            limit = min(int(q.get("limit") or 100), 1000)
            return self._json({"total": len(rows), "assets": rows[:limit]})
        if method == "GET" and len(p) == 2 and p[0] == "board-maps":
            from . import board_edit as be
            return self._json(be.board_map(p[1]))
        if method == "GET" and len(p) == 3 and p[0] == "board-maps" and p[2] == "picture":
            from . import board_edit as be
            return self._file(be.picture(p[1]))
        if method == "GET" and p == ["catalog"]:
            from . import catalog
            return self._json(catalog.search(_game(), q.get("q") or None, q.get("category") or None, q.get("kind") or None,
                                             q.get("changeable") in ("1", "true"), min(int(q.get("limit") or 100), 1000), int(q.get("offset") or 0),
                                             language=q.get("language") or None))
        if method == "GET" and p == ["sounds"]:
            return self._json(sounds.search(_game(), q.get("q") or None, q.get("category") or None, min(int(q.get("limit") or 100), 1000)))
        if method == "GET" and p == ["sounds", "preview"]:
            from . import audio_support
            if not audio_support.apply():
                return self._json({"error": "Listening to the game's own sounds needs game-audio support (FMOD). Get it once from the Sounds page.", "code": "needs_audio_support"}, 409)
            return self._file(sound_preview(q.get("path", "")))
        if p == ["audio-support"] and method == "GET":
            from . import audio_support
            return self._json(audio_support.status())
        if p == ["audio-support", "install"] and method == "POST":
            from . import audio_support
            return self._json(audio_support.install())
        if len(p) == 5 and p[0] == "mods" and p[2] == "edit" and method == "POST":
            from . import edits
            return self._json(edits.edit(_game(), p[1], p[3], p[4], self._payload()))
        if p == ["starters"] and method == "GET":
            from . import starters
            return self._json(starters.kinds())
        if p == ["search"] and method == "GET":
            from . import search as _search
            return self._json(_search.search(q.get("q", "")))
        if len(p) >= 3 and p[0] == "mods" and p[2] == "previews":
            from . import previews
            mods.read_mod(p[1])
            if method == "GET" and len(p) == 3:
                return self._json(previews.status(p[1]))
            if method == "POST" and len(p) == 3:
                body = self._payload()
                return self._json(previews.render(_game(), p[1], body.get("cards") or None, kinds=body.get("kinds") or None))
            if method == "GET" and (len(p) == 4 or (len(p) == 5 and p[3] in previews.KINDS)):
                root = previews.folder(p[1]).resolve()
                path = (root / "/".join(p[3:])).resolve()
                if root not in path.parents or path.suffix.lower() != ".png":
                    return self._json({"error": "not found"}, 404)
                return self._file(path)
        if len(p) == 4 and p[0] == "mods" and p[2] == "bulk" and method == "POST":
            from . import bulk
            mods.read_mod(p[1])
            b = self._payload()
            files = b.get("files") or {}
            if p[3] == "cards":
                return self._json(bulk.cards_csv(_game(), p[1], b.get("text") or "", files))
            if p[3] == "art":
                return self._json(bulk.art_by_name(_game(), p[1], files))
            if p[3] == "sounds":
                return self._json(bulk.sounds_by_name(_game(), p[1], files, float(b.get("volume") or 1.0)))
            if p[3] == "music":
                return self._json(bulk.music(p[1], files, b.get("contexts") or [], b.get("mode") or "rotation"))
        if p == ["bulk-template.csv"] and method == "GET":
            from . import bulk
            data = bulk.template_csv().encode("utf-8-sig")
            self.send_response(200); self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="cards-template.csv"'); self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data); return
        if len(p) >= 3 and p[0] == "mods" and p[2] == "translations":
            from . import translations as _tr
            mods.read_mod(p[1])
            if method == "GET" and len(p) == 3:
                return self._json(_tr.languages(p[1]))
            if method == "GET" and len(p) == 4 and p[3].endswith(".csv"):
                data = _tr.export_csv(p[1], p[3][:-4]).encode("utf-8-sig")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{p[1]}-{p[3]}"')
                self.send_header("Content-Length", str(len(data)))
                self.end_headers(); self.wfile.write(data); return
            if method == "GET" and len(p) == 4:
                return self._json(_tr.table(p[1], p[3]))
            if method == "POST" and len(p) == 4:
                b = self._payload()
                return self._json(_tr.save(p[1], p[3], b.get("values") or {}, bool(b.get("merge", True))))
            if method == "POST" and len(p) == 5 and p[4] == "csv":
                return self._json(_tr.import_csv(p[1], p[3], self._payload().get("text") or ""))
        if len(p) >= 3 and p[0] == "mods" and p[2] == "details":
            from . import details
            mods.read_mod(p[1])
            if method == "GET" and len(p) == 3:
                return self._json(details.get(p[1]))
            if method == "POST" and len(p) == 3:
                return self._json(details.update(p[1], self._payload()))
            if method == "POST" and len(p) == 4 and p[3] == "release":
                b = self._payload()
                return self._json(details.add_change(p[1], b.get("notes") or "", b.get("part") or "minor", b.get("version") or None))
            if method == "POST" and len(p) == 4 and p[3] == "preview":
                return self._json(details.set_preview(p[1], self._payload()["image"]))
        if len(p) == 3 and p[0] == "mods" and p[2] in ("playtest", "report"):
            from . import playtest
            mods.read_mod(p[1])
            if p[2] == "report" and method == "GET":
                return self._json(playtest.report(_game(), p[1]))
            if p[2] == "playtest" and method == "POST":
                return self._json(playtest.launch(_game(), p[1], bool(self._payload().get("enable", True))))
        if len(p) == 3 and p[0] == "mods" and p[2] in ("history", "undo", "redo"):
            from . import fsutil
            mods.read_mod(p[1])
            if p[2] == "history" and method == "GET":
                return self._json(fsutil.history(p[1]))
            if method == "POST" and p[2] in ("undo", "redo"):
                return self._json(fsutil.undo(p[1]) if p[2] == "undo" else fsutil.redo(p[1]))
        if method == "POST" and p == ["mods", "install"]:
            from . import packages
            b = self._payload()
            return self._json(packages.install(b["source"], bool(b.get("enable")), bool(b.get("force"))))
        if len(p) == 3 and p[0] == "mods" and p[2] in ("export", "uninstall") and method == "POST":
            from . import packages
            return self._json(packages.export_mod(p[1]) if p[2] == "export" else packages.uninstall(p[1]))
        if len(p) == 3 and p[0] == "mods" and p[2] == "export.zip" and method == "GET":
            from . import packages
            return self._file(Path(packages.export_mod(p[1])["file"]))
        if method == "GET" and p == ["compat"]:
            from . import compat
            return self._json(compat.report())
        if method == "POST" and p == ["compat", "order"]:
            from . import compat
            b = self._payload()
            return self._json(compat.auto_order() if b.get("auto") else compat.set_order(list(b.get("order") or [])))
        if method == "GET" and p == ["assets", "preview"]:
            return self._file(asset_preview(q.get("path", "")))
        if method == "POST" and p == ["upload"]:
            return self._json(save_upload(self.headers.get("X-Filename", "upload"), self._body()))
        return self._json({"error": f"no route {method} /api/{'/'.join(p)}"}, 404)


def serve(port: int = 8765, open_browser: bool = True, game_path: str | None = None) -> None:
    _state["game_path"] = game_path
    from .game import write_location_pointer
    write_location_pointer()
    try:
        from . import audio_support
        audio_support.apply()   # a downloaded fmod.dll (installed app), if any
    except Exception:
        pass
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"TESL Forge running at {url} (Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
