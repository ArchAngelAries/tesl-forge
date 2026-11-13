"""`tesl` command line. Every command accepts --json for agents (stable shapes, non-zero exit on failure)."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import __version__, assets, cards
from .game import find_install, workspace


def _emit(args, payload, human):
    if args.json:
        print(json.dumps(payload, indent=1, ensure_ascii=False))
    else:
        human(payload)


def cmd_info(args):
    game = find_install(args.game)
    payload = {"suite_version": __version__, "game": game.to_dict(), "workspace": str(workspace())}
    _emit(args, payload, lambda p: [print(f"{k}: {v}") for k, v in {**p["game"], "workspace": p["workspace"]}.items()])


def cmd_index(args):
    game = find_install(args.game)
    index = assets.build_index(game)
    counts = {}
    for e in index["entries"]:
        counts[e["kind"]] = counts.get(e["kind"], 0) + 1
    payload = {k: index[k] for k in ("bundles", "assets", "seconds", "built")}
    payload["by_kind"] = dict(sorted(counts.items(), key=lambda x: -x[1]))
    _emit(args, payload, lambda p: print(f"Indexed {p['assets']} assets in {p['bundles']} bundles ({p['seconds']} s): {p['by_kind']}"))


def cmd_list(args):
    game = find_install(args.game)
    rows = assets.query(assets.load_index(game), args.kind, args.contains, args.bundle, args.regex)
    shown = rows[: args.limit] if args.limit else rows
    _emit(args, {"total": len(rows), "shown": len(shown), "assets": shown},
          lambda p: ([print(f"{e['kind']:9} {e['bundle']:32} {e['path']}") for e in p["assets"]], print(f"{p['shown']} of {p['total']}")))


def cmd_export(args):
    game = find_install(args.game)
    rows = assets.query(assets.load_index(game), args.kind, args.contains, args.bundle, args.regex)
    if args.limit:
        rows = rows[: args.limit]
    out = Path(args.out) if args.out else workspace() / "exports" / "assets"
    results = assets.export(game, rows, out)
    ok = [r for r in results if "error" not in r and "skipped" not in r]
    payload = {"requested": len(rows), "exported": len(ok), "out": str(out.resolve()), "results": results}
    _emit(args, payload, lambda p: print(f"Exported {p['exported']} of {p['requested']} to {p['out']} (manifest: export-manifest.json)"))
    return 0 if len(ok) == len(rows) or not rows else 2


def cmd_cards(args):
    game = find_install(args.game)
    rows = cards.catalog(game, args.data)
    if args.contains:
        rows = [c for c in rows if args.contains.lower() in (c["name"] or "").lower()]
    if args.set:
        rows = [c for c in rows if (c["set"] or "").lower() == args.set.lower()]
    if args.collectible:
        rows = [c for c in rows if c["collectible"]]
    shown = rows[: args.limit] if args.limit else rows
    _emit(args, {"total": len(rows), "shown": len(shown), "cards": shown},
          lambda p: ([print(f"{c['id']:>12} {c['set']:20} {str(c['cost']):>2} {c['type']:9} {c['name']}") for c in p["cards"]], print(f"{p['shown']} of {p['total']}")))


def cmd_card_art(args):
    """Card art at original resolution, named '<Card Name> [<id>].png', with a manifest mapping art to every card using it."""
    game = find_install(args.game)
    index = assets.load_index(game)
    by_path = assets.by_path(index)
    rows = cards.catalog(game, args.data)
    if args.contains:
        rows = [c for c in rows if args.contains.lower() in (c["name"] or "").lower()]
    if args.collectible:
        rows = [c for c in rows if c["collectible"]]
    users: dict[str, list[dict]] = {}
    missing = []
    for c in rows:
        if not c["image"]:
            continue
        entry = next((by_path[p] for p in cards.art_asset_paths(c["image"]) if p in by_path), None)
        if entry is None:
            missing.append({"id": c["id"], "name": c["name"], "image": c["image"]})
            continue
        users.setdefault(entry["path"].lower(), []).append(c)
    selected = list(users.items())
    if args.limit:
        selected = selected[: args.limit]
    entries = [by_path[p] for p, _ in selected]
    names = {by_path[p]["path"]: f"{cs[0]['name']} [{cs[0]['id']}]" for p, cs in selected}
    out = Path(args.out) if args.out else workspace() / "exports" / "card-art"
    results = assets.export(game, entries, out, naming=lambda e: names[e["path"]])
    for r in results:
        r["cards"] = [{"id": c["id"], "name": c["name"], "set": c["set"]} for c in users.get(r["path"].lower(), [])]
    ok = [r for r in results if "file" in r]
    (out / "card-art-manifest.json").write_text(json.dumps({"exported": results, "missing_art": missing}, indent=1, ensure_ascii=False), encoding="utf-8")
    payload = {"cards_considered": len(rows), "art_files": len(selected), "exported": len(ok), "missing_art": len(missing),
               "out": str(out.resolve()), "results": results if args.json else None}
    _emit(args, payload, lambda p: print(f"Exported {p['exported']} card-art files for {p['cards_considered']} cards to {p['out']} "
                                          f"({p['missing_art']} cards without art in the bundles; see card-art-manifest.json)"))
    return 0 if len(ok) == len(selected) else 2


def _simple(fn, human):
    def run(args):
        payload = fn(args)
        _emit(args, payload, human)
        return 0 if not isinstance(payload, dict) or payload.get("valid", True) else 2
    return run


def _keywords(spec):
    if not spec:
        return None
    out = {}
    for part in spec.split(","):
        k, _, v = part.strip().partition("=")
        out[k.strip()] = int(v) if v.strip().lstrip("-").isdigit() else True
    return out


def _mod_commands(sub):
    from . import mods
    m = sub.add_parser("mod", help="mod packages").add_subparsers(dest="cmd", required=True)
    n = m.add_parser("new", help="create a mod package"); n.add_argument("mod_id"); n.add_argument("--name", required=True)
    n.add_argument("--author", default=""); n.add_argument("--description", default="")
    n.add_argument("--starter", default="blank", choices=["blank", "copy", "card", "story", "mode", "opponent"],
                   help="begin with: nothing, a copy of --from, or a first card/story/mode/AI opponent to edit")
    n.add_argument("--from", dest="source", help="with --starter copy: the mod to copy (e.g. sample-skyrim)")
    def _new(a):
        from . import starters
        return starters.create(find_install(a.game), a.mod_id, a.name, a.starter, a.author, a.description, a.source)
    n.set_defaults(fn=_simple(_new, lambda p: print(f"Created {p['mod']['id'] if 'id' in p['mod'] else p['mod']}" + (f" ({p['note']})" if p.get('note') else ""))))
    m.add_parser("list", help="list mods").set_defaults(fn=_simple(lambda a: {"mods": mods.list_mods()},
        lambda p: [print(f"{'ON ' if x['enabled'] else 'off'} {x['id']:24} {x['cards']:3} cards {x['decks']:2} decks  {x['name']}") for x in p["mods"]]))
    v = m.add_parser("validate", help="check a mod"); v.add_argument("mod_id")
    v.set_defaults(fn=_simple(lambda a: mods.validate(find_install(a.game), a.mod_id),
        lambda p: (print(f"{p['mod']}: {p['cards']} cards, {p['decks']} decks, {'VALID' if p['valid'] else 'INVALID'}"),
                   [print("  error: " + e) for e in p["errors"]], [print("  warning: " + w) for w in p["warnings"]])))
    from . import compat
    for name, flag in (("enable", True), ("disable", False)):
        e = m.add_parser(name, help=f"{name} a mod for the offline game"); e.add_argument("mod_id")
        if flag:
            e.add_argument("--force", action="store_true", help="enable even if it would be skipped (missing dependency, conflict...)")
        e.set_defaults(fn=_simple(lambda a, f=flag: mods.set_enabled(a.mod_id, f, getattr(a, "force", False)),
            lambda p: print(f"{p['mod']} {'enabled' if p['enabled'] else 'disabled'} ({len(p['active'])} active; restart the game)")))
    from . import packages
    dt = m.add_parser("details", help="change a mod's version, needs/conflicts, load-order hints, author, description")
    dt.add_argument("mod_id"); dt.add_argument("--name"); dt.add_argument("--author"); dt.add_argument("--description"); dt.add_argument("--website")
    dt.add_argument("--version"); dt.add_argument("--needs", action="append", help="another mod it needs: id or id@range (e.g. base-pack@>=1.2); repeat")
    dt.add_argument("--conflicts", help="mod ids it does not work with (space or comma separated)")
    dt.add_argument("--load-after"); dt.add_argument("--load-before")
    def _details(a):
        from . import details
        f = {k: getattr(a, k) for k in ("name", "author", "description", "website", "version", "conflicts", "load_after", "load_before")}
        if a.needs is not None:
            f["dependencies"] = [{"id": n.split("@")[0], "version": n.split("@", 1)[1] if "@" in n else "*"} for n in a.needs]
        return details.update(a.mod_id, f)
    dt.set_defaults(fn=_simple(_details, lambda p: print(f"{p['id']} {p['version']}  needs: {', '.join(d['id'] + ' ' + d['version'] for d in p['dependencies']) or '-'}  conflicts: {', '.join(p['conflicts']) or '-'}")))
    rl = m.add_parser("release", help="record a release: version up and changelog notes (exports carry CHANGELOG.md)")
    rl.add_argument("mod_id"); rl.add_argument("--notes", required=True); rl.add_argument("--part", choices=["major", "minor", "patch"], default="minor"); rl.add_argument("--version")
    rl.set_defaults(fn=_simple(lambda a: __import__("tesl_suite.details", fromlist=["add_change"]).add_change(a.mod_id, a.notes, a.part, a.version),
                               lambda p: print(f"{p['id']} is now {p['version']}")))
    ex = m.add_parser("export", help="package a mod as a shareable .zip (with package.json: version, engine level, class, fingerprint)")
    ex.add_argument("mod_id"); ex.add_argument("--out")
    ex.set_defaults(fn=_simple(lambda a: packages.export_mod(a.mod_id, a.out), lambda p: print(f"{p['mod']} {p['package']['version']}: {p['file']} ({p['bytes'] // 1024} KB)")))
    ins = m.add_parser("install", help="install a mod from a .zip, a folder or an https link (content files only)")
    ins.add_argument("source"); ins.add_argument("--enable", action="store_true"); ins.add_argument("--force", action="store_true", help="replace the same or a newer installed version")
    ins.set_defaults(fn=_simple(lambda a: packages.install(a.source, a.enable, a.force), lambda p: print(
        f"installed {p['mod']} {p['version']}" + (f" (replaced {p['replaced']['version']}, backup kept)" if p["replaced"] else "")
        + ("" if not p["compatibility"] else "; would be skipped: " + "; ".join(p["compatibility"])) + (" - enabled" if p.get("enabled") else ""))))
    un = m.add_parser("uninstall", help="remove a mod (moved to workspace/trash, recoverable)"); un.add_argument("mod_id")
    un.set_defaults(fn=_simple(lambda a: packages.uninstall(a.mod_id), lambda p: print(f"{p['mod']} moved to {p['moved_to']}")))
    from . import fsutil
    for name, fn in (("undo", fsutil.undo), ("redo", fsutil.redo)):
        u = m.add_parser(name, help=f"{name} the last change to a mod (files saved by the suite; deletes come back from the trash)")
        u.add_argument("mod_id")
        u.set_defaults(fn=_simple(lambda a, fn=fn: fn(a.mod_id), lambda p: print(f"{p['mod']}: {'undid' if 'undone' in p else 'redid'} \"{p.get('undone') or p.get('redone')}\" ({p['files']} files)")))
    hi = m.add_parser("history", help="recent changes of a mod (undo/redo steps)"); hi.add_argument("mod_id")
    hi.set_defaults(fn=_simple(lambda a: fsutil.history(a.mod_id), lambda p: [print(f"undo {x['time']}  {x['label']}  ({x['files']} files)") for x in p["undo"]]
        + [print(f"redo {x['time']}  {x['label']}") for x in p["redo"]]))
    from . import edits
    ed = m.add_parser("edit", help="edit an existing card, deck, avatar, card back, board or music track in place (id and slug stay)")
    ed.add_argument("mod_id"); ed.add_argument("kind", choices=list(edits.KINDS)); ed.add_argument("item", help="slug, name or card id")
    ed.add_argument("--set", action="append", default=[], metavar="FIELD=VALUE",
                    help="e.g. --set name=\"New name\" --set cost=3 --set text=... --set art=pic.png --set cards=\"A x3; B x2\" (JSON values allowed)")
    def _fields(pairs):
        out = {}
        for pair in pairs:
            k, _, v = pair.partition("=")
            try: out[k.strip()] = json.loads(v)
            except ValueError: out[k.strip()] = v
        if "cards" in out: out["cards_spec"] = out.pop("cards")
        return out
    ed.set_defaults(fn=_simple(lambda a: edits.edit(find_install(a.game), a.mod_id, a.kind, a.item, _fields(a.set)),
        lambda p: print(f"{p['mod']}: edited " + ", ".join(f"{k} {v.get('name', '')}" for k, v in p.items() if isinstance(v, dict) and k != "art"))))
    ck = m.add_parser("check", help="compatibility of the enabled mods: load order, skipped mods, overlaps, multiplayer class")
    ck.set_defaults(fn=_simple(lambda a: compat.report(), lambda p: (
        print("Load order: " + (" > ".join(p["order"]) or "(none)")),
        [print(f"  {x['id']:24} v{x['version']:8} {x['class']:9} engine {x['requires_engine']}  {x['fingerprint']}") for x in p["mods"]],
        [print(f"{x['severity'].upper():8} {x['text']}") for x in p["problems"] + p["overlaps"]],
        print("OK" if p["ok"] else "Problems found"))))
    od = m.add_parser("order", help="show or set the load order (later mods win where two change the same thing)")
    od.add_argument("--set", help="comma-separated mod ids, first loads first (ids left out are disabled)")
    od.add_argument("--auto", action="store_true", help="sort by dependencies and load_after/load_before hints")
    od.set_defaults(fn=_simple(lambda a: compat.set_order([x.strip() for x in a.set.split(",") if x.strip()]) if a.set else compat.auto_order() if a.auto else compat.report(),
        lambda p: print("Load order: " + (" > ".join(p["order"]) or "(none)"))))
    c = sub.add_parser("card", help="author cards").add_subparsers(dest="cmd", required=True)
    cn = c.add_parser("new", help="new card from a template card (stats, text, art; rules kept or taken from another card)")
    cn.add_argument("--mod", required=True); cn.add_argument("--name", required=True)
    cn.add_argument("--template", required=True, help="existing card (name or id) the new card is based on")
    cn.add_argument("--cost", type=int); cn.add_argument("--attack", type=int); cn.add_argument("--health", type=int)
    cn.add_argument("--text"); cn.add_argument("--rarity", choices=["Common", "Rare", "Epic", "Legendary"])
    cn.add_argument("--art", help="image file (PNG/JPG); centre-cropped to a square and resized to 1024x1024")
    cn.add_argument("--rules-from", help="copy the rules (and text) of this card instead of the template's")
    cn.add_argument("--no-rules", action="store_true"); cn.add_argument("--unique", action="store_true", default=None)
    cn.add_argument("--abilities", help='rule editor: JSON list [{"card": "Fireball", "ability": "play:0", "params": {"<path>": 3}}] (see: tesl card abilities)')
    cn.add_argument("--keywords", help="rule editor: e.g. 'Guard,Charge,Rally=2'")
    cn.set_defaults(fn=_simple(lambda a: mods.new_card(find_install(a.game), a.mod, a.name, a.template, a.cost, a.attack, a.health,
                                                        a.text, a.rarity, a.art, a.rules_from, a.no_rules, a.unique,
                                                        json.loads(a.abilities) if a.abilities else None, _keywords(a.keywords)),
        lambda p: print(f"Card {p['card']['name']} [{p['card']['id']}] -> {p['card']['file']}\n  rules: {p['card']['rules_from']}; text: {p['card']['text']}")))
    fr = c.add_parser("frame", help="where a card's art sits in its art window (scale > 1 shows more of the picture); art untouched")
    fr.add_argument("--mod", required=True); fr.add_argument("--card", required=True)
    fr.add_argument("--scale", type=float); fr.add_argument("--x", type=float, default=0.0, help="+ shows more of the right side")
    fr.add_argument("--y", type=float, default=0.0, help="+ shows more of the top")
    fr.set_defaults(fn=_simple(lambda a: __import__("tesl_suite.framing", fromlist=["x"]).set_frame(a.mod, a.card, a.scale, a.x, a.y) if a.scale is not None
                               else __import__("tesl_suite.framing", fromlist=["x"]).current(a.mod, a.card),
        lambda p: print(json.dumps(p))))
    ab = c.add_parser("abilities", help="a card's abilities and editable parameters (for --abilities)"); ab.add_argument("card")
    ab.set_defaults(fn=_simple(lambda a: __import__("tesl_suite.api", fromlist=["card_abilities"]).card_abilities(a.card),
        lambda p: [print(f"{x['id']:12} {x['label']}: " + ", ".join(f"{q['label']}={q['value']} [{'.'.join(map(str, q['path']))}]" for q in x["params"])) for x in p["abilities"]]))
    d = sub.add_parser("deck", help="author decks").add_subparsers(dest="cmd", required=True)
    dn = d.add_parser("new", help="new deck: --cards 'Name x3; Other Card x2' (separate with ; or new lines, or give a JSON array; commas work for names without commas)")
    dn.add_argument("--mod", required=True); dn.add_argument("--name", required=True); dn.add_argument("--cards", required=True)
    dn.add_argument("--art-card"); dn.add_argument("--description", default="")
    dn.set_defaults(fn=_simple(lambda a: mods.new_deck(find_install(a.game), a.mod, a.name, a.cards, a.art_card, a.description),
        lambda p: print(f"Deck {p['deck']['name']}: {p['deck']['total_cards']} cards -> {p['deck']['file']}")))


def _replace_commands(sub):
    from . import replace
    r = sub.add_parser("replace", help="replace original images (remastering): card art, avatars, banners").add_subparsers(dest="cmd", required=True)
    ri = r.add_parser("image", help="swap an original image in a mod; keeps its on-screen size")
    ri.add_argument("--mod", required=True); ri.add_argument("--image", required=True, help="new image (PNG/JPG), any resolution")
    ri.add_argument("--asset", help="the original's asset path (from tesl assets list --kind texture)")
    ri.add_argument("--card", help="or: replace this card's art (name or id)")
    ri.add_argument("--fit", choices=["crop", "stretch"], default="crop", help="match the original's shape (default: centre-crop)")
    ri.set_defaults(fn=_simple(lambda a: replace.add(find_install(a.game), a.mod, a.image, a.asset, a.card, a.fit),
        lambda p: print(f"{p['mod']}: {p['replaced']['asset']} -> {p['replaced']['file']} ({p['replaced']['width']}x{p['replaced']['height']}, "
                        f"original {p['replaced']['original']['width']}x{p['replaced']['original']['height']}); {p['total']} replacements")))
    rl = r.add_parser("list", help="replacements in a mod"); rl.add_argument("--mod", required=True)
    rl.set_defaults(fn=_simple(lambda a: replace.list_replacements(a.mod),
        lambda p: [print(f"{x['asset']}  ->  {x['file']} ({x['width']}x{x['height']})") for x in p["images"]]))
    rr = r.add_parser("remove", help="undo a replacement"); rr.add_argument("--mod", required=True); rr.add_argument("--asset", required=True)
    rr.set_defaults(fn=_simple(lambda a: replace.remove(a.mod, a.asset), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _avatar_commands(sub):
    from . import avatars
    v = sub.add_parser("avatar", help="new avatar choices (their own pages in the avatar picker)").add_subparsers(dest="cmd", required=True)
    n = v.add_parser("new", help="add an avatar from any image: cropped to the game's portrait shape plus a round-portrait square")
    n.add_argument("--mod", required=True); n.add_argument("--name", required=True); n.add_argument("--image", required=True)
    n.add_argument("--voice", help="original avatar whose emote voice lines it uses (e.g. AvatarNord1)")
    n.add_argument("--head", type=float, default=0.22, help="head height as a fraction from the top, for the round crop (default 0.22)")
    n.add_argument("--profile", help="separate picture for the round profile portrait (default: cut from --image)")
    n.set_defaults(fn=_simple(lambda a: avatars.new_avatar(a.mod, a.name, a.image, a.voice, a.head, a.profile),
        lambda p: print(f"{p['mod']}: avatar {p['avatar']['name']} ({p['avatar']['width']}x{p['avatar']['height']}); {p['total']} avatars on {p['pages']} page(s)")))
    v.add_parser("voices", help="original avatars whose emote voices new avatars can use").set_defaults(fn=_simple(
        lambda a: {"voices": avatars.original_avatars()},
        lambda p: [print(f"{x['unique_name']:32} {x['race']}") for x in p["voices"]]))
    em = v.add_parser("emote", help="an avatar's own emote line (text and/or voice); the AI uses it too when it plays that avatar")
    em.add_argument("--mod", required=True); em.add_argument("--avatar", required=True)
    em.add_argument("--emote", required=True, help="Hello, GoodGame, Implore, Taunt, Oops, NicePlay, ThankYou or Sorry")
    em.add_argument("--text"); em.add_argument("--audio", help="voice clip (WAV; other formats converted with ffmpeg)")
    em.set_defaults(fn=_simple(lambda a: avatars.set_emote(a.mod, a.avatar, a.emote, a.text, a.audio),
        lambda p: print(f"{p['mod']}: {p['avatar']} {p['emote']}: {p['line']}")))
    pg = v.add_parser("page", help="name/describe the mod's avatar page(s)"); pg.add_argument("--mod", required=True)
    pg.add_argument("--name"); pg.add_argument("--description")
    pg.set_defaults(fn=_simple(lambda a: avatars.set_page(a.mod, a.name, a.description), lambda p: print(f"{p['mod']}: page {p['page']}")))
    ls = v.add_parser("list", help="avatars in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: avatars.list_avatars(a.mod),
        lambda p: [print(f"{x['slug']:24} {x['name']}  voice={x.get('voice', 'default')}") for x in p["avatars"]]))
    rm = v.add_parser("remove", help="remove an avatar"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: avatars.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _cardback_commands(sub):
    from . import cardbacks
    b = sub.add_parser("cardback", help="new card backs (selectable in the collection; free or sold for gold)").add_subparsers(dest="cmd", required=True)
    n = b.add_parser("new", help="a card back from any image (cropped into the game's card shape)")
    n.add_argument("--mod", required=True); n.add_argument("--name", required=True); n.add_argument("--image", required=True)
    n.add_argument("--price", type=int, default=0, help="gold in the offline store; 0 = free for everyone with the mod")
    n.add_argument("--unlock", help="text shown for how to get it"); n.add_argument("--size", type=int, default=1024, choices=[1024, 2048])
    n.set_defaults(fn=_simple(lambda a: cardbacks.new_cardback(a.mod, a.name, a.image, a.price, a.unlock, a.size),
        lambda p: print(f"{p['mod']}: card back {p['cardback']['name']} ({'free' if not p['cardback']['price'] else str(p['cardback']['price']) + ' gold'}); {p['total']} in this mod")))
    ls = b.add_parser("list", help="card backs in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: cardbacks.list_cardbacks(a.mod),
        lambda p: [print(f"{c['slug']:24} {c['name']}  {c.get('price', 0) or 'free'}") for c in p["cardbacks"]]))
    rm = b.add_parser("remove", help="remove a card back"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: cardbacks.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _bulk_commands(sub):
    from . import bulk
    b = sub.add_parser("bulk", help="import many cards, card art, sounds or music tracks at once").add_subparsers(dest="cmd", required=True)
    pictures = (".png", ".jpg", ".jpeg", ".webp")
    def folder_files(d, exts):
        return {p.name: str(p) for p in sorted(Path(d).iterdir()) if p.suffix.lower() in exts} if d else {}
    c = b.add_parser("cards", help="cards from a CSV: name, template, cost, power, health, rarity, text, art, unique")
    c.add_argument("--mod", required=True); c.add_argument("--csv", required=True); c.add_argument("--art-dir", help="folder with the art pictures (default: next to the CSV)")
    c.set_defaults(fn=_simple(lambda a: bulk.cards_csv(find_install(a.game), a.mod, Path(a.csv).read_text(encoding="utf-8-sig"),
                                                       folder_files(a.art_dir or Path(a.csv).parent, pictures), str(Path(a.csv).parent)), _bulk_report))
    r = b.add_parser("art", help="pictures named after cards: mod cards get new art, original cards a remastered replacement")
    r.add_argument("--mod", required=True); r.add_argument("--dir", required=True)
    r.set_defaults(fn=_simple(lambda a: bulk.art_by_name(find_install(a.game), a.mod, folder_files(a.dir, pictures)), _bulk_report))
    sn = b.add_parser("sounds", help="audio files named after game sounds or card voice lines (\"Arena End.wav\", \"<card> Play.wav\")")
    sn.add_argument("--mod", required=True); sn.add_argument("--dir", required=True)
    sn.set_defaults(fn=_simple(lambda a: bulk.sounds_by_name(find_install(a.game), a.mod, folder_files(a.dir, (".ogg", ".wav", ".mp3", ".flac", ".m4a"))), _bulk_report))
    m = b.add_parser("music", help="audio files as soundtrack tracks"); m.add_argument("--mod", required=True); m.add_argument("--dir", required=True)
    m.add_argument("--at", required=True, help="moments, comma separated (tesl music contexts)"); m.add_argument("--mode", default="rotation", choices=["rotation", "replace"])
    m.set_defaults(fn=_simple(lambda a: bulk.music(a.mod, folder_files(a.dir, (".ogg", ".wav", ".mp3", ".flac", ".m4a")), [x.strip() for x in a.at.split(",") if x.strip()], a.mode), _bulk_report))


def _bulk_report(p):
    print(f"{p['mod']}: {p['imported']} imported, {len(p['failed'])} failed")
    for f in p["failed"]:
        print("  failed:", f.get("card") or f.get("file"), "-", f["error"])


def _translate_commands(sub):
    from . import translations as tr
    t = sub.add_parser("translate", help="translations of a mod's text (shown when the game runs in that language)").add_subparsers(dest="cmd", required=True)
    ls = t.add_parser("list", help="languages and how much is translated"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: tr.languages(a.mod), lambda p: [print(f"{x['language']:6} {x['label']:20} {x['done']}/{x['total']}") for x in p["languages"]] or print(f"no translations yet ({p['total']} texts)")))
    ex = t.add_parser("export", help="write a CSV (English, translation) for translators"); ex.add_argument("--mod", required=True); ex.add_argument("--lang", required=True); ex.add_argument("--out", required=True)
    def _ex(a):
        Path(a.out).write_text(tr.export_csv(a.mod, a.lang), encoding="utf-8-sig")
        return {"file": a.out}
    ex.set_defaults(fn=_simple(_ex, lambda p: print(f"wrote {p['file']}")))
    im = t.add_parser("import", help="read a translated CSV back"); im.add_argument("--mod", required=True); im.add_argument("--lang", required=True); im.add_argument("--file", required=True)
    im.set_defaults(fn=_simple(lambda a: tr.import_csv(a.mod, a.lang, Path(a.file).read_text(encoding="utf-8-sig")),
                               lambda p: print(f"{p['language']}: {p['imported']} rows read, {p['strings']} translations in the mod" + (f"; not in the mod: {p['not_in_mod']}" if p['not_in_mod'] else ""))))
    st = t.add_parser("set", help="translate one text"); st.add_argument("--mod", required=True); st.add_argument("--lang", required=True)
    st.add_argument("--english", required=True); st.add_argument("--text", required=True, help="the translation ('' removes it)")
    st.set_defaults(fn=_simple(lambda a: tr.save(a.mod, a.lang, {a.english: a.text}), lambda p: print(f"{p['language']}: {p['strings']} translations")))


def _pack_commands(sub):
    from . import packs
    k = sub.add_parser("pack", help="card packs sold for gold in the offline store, with their own drop table").add_subparsers(dest="cmd", required=True)
    s = k.add_parser("save", help="create or change a pack")
    s.add_argument("--mod", required=True); s.add_argument("--name", required=True); s.add_argument("--slug"); s.add_argument("--description")
    s.add_argument("--price", type=int); s.add_argument("--cards", type=int, help="cards per pack, 1-12"); s.add_argument("--image", help="store art picture")
    s.add_argument("--pool", help="mod, all, or card sets separated by commas (0_Core, Skyrim, Morrowind, ...)")
    s.add_argument("--odds", help="common,rare,epic,legendary chances for every slot, e.g. 79,15,4.5,1.5")
    s.add_argument("--last-slot", help="the same for the last slot, e.g. 0,80,15,5")
    s.add_argument("--premium", type=float, help="percent chance a card is premium")
    s.add_argument("--card", action="append", help="hand-picked card: 'Name' or 'Name=weight'; repeat (replaces rarity slots)")
    def odds(v):
        if not v:
            return None
        parts = [float(x) for x in v.split(",")]
        return dict(zip(packs.RARITIES, parts + [0] * (4 - len(parts))))
    def run(a):
        pool = None if a.pool is None else (a.pool if a.pool in ("mod", "all") else [x.strip() for x in a.pool.split(",") if x.strip()])
        cl = None if a.card is None else [{"card": c.split("=")[0].strip(), "weight": float(c.split("=")[1]) if "=" in c else 1} for c in a.card]
        return packs.save_pack(find_install(a.game), a.mod, {"slug": a.slug, "name": a.name, "description": a.description, "price": a.price, "cards": a.cards,
                               "pool": pool, "odds": odds(a.odds), "last_slot": odds(a.last_slot), "premium": a.premium, "cards_list": cl}, a.image)
    s.set_defaults(fn=_simple(run, lambda p: print(f"{p['mod']}: pack {p['pack']['name']} ({p['pack']['price']} gold) saved; store key {p['store_key']}")))
    ls = k.add_parser("list", help="packs in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: packs.list_packs(a.mod), lambda p: [print(f"{x['slug']:24} {x['name']}  {x.get('price')} gold, {x.get('cards')} cards") for x in p["packs"]]))
    rm = k.add_parser("remove", help="remove a pack"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: packs.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _playtest_commands(sub):
    from . import playtest
    t = sub.add_parser("playtest", help="start TESL: Everlasting with a mod enabled; --report reads what the game loaded")
    t.add_argument("--mod"); t.add_argument("--report", action="store_true", help="only show the game's last mod-load report")
    def run(a):
        g = find_install(a.game)
        if a.report:
            r = playtest.report(g, a.mod)
            _emit(a, r, lambda p: (print(p.get("note") or f"Loaded: {', '.join(p.get('loaded', [])) or 'nothing'} ({p['age_seconds']} s ago)"),
                                   [print("  problem:", x) for x in p.get("problems", [])]))
            return 0
        _emit(a, playtest.launch(g, a.mod), lambda p: [print(n) for n in p["notes"]])
        return 0
    t.set_defaults(fn=run)


def _opponent_commands(sub):
    from . import opponents
    o = sub.add_parser("opponent", help="AI opponents for TESL: Everlasting (Practice, game modes, story battles)").add_subparsers(dest="cmd", required=True)
    s = o.add_parser("save", help="create or change an AI opponent")
    s.add_argument("--mod", required=True); s.add_argument("--name", required=True); s.add_argument("--slug")
    s.add_argument("--title"); s.add_argument("--image", help="a picture file for the portrait (cropped to the avatar shape)")
    s.add_argument("--portrait", help="avatar:<slug of this mod's avatar> or asset:<game image path>")
    s.add_argument("--deck", help="practice, random, or a deck type name/display name"); s.add_argument("--random-size", type=int)
    s.add_argument("--difficulty", choices=opponents.DIFFICULTIES); s.add_argument("--temperament", choices=[t for t in opponents.TEMPERAMENTS if t])
    s.add_argument("--no-practice", action="store_true", help="only in modes and stories that name it, never in random Practice")
    s.set_defaults(fn=_simple(lambda a: opponents.save_opponent(a.mod, {"slug": a.slug, "name": a.name, "title": a.title, "portrait": a.portrait, "deck": a.deck,
        "random_size": a.random_size, "difficulty": a.difficulty, "temperament": a.temperament, "practice": False if a.no_practice else None}, a.image),
        lambda p: print(f"{p['mod']}: AI opponent {p['opponent']['name']} saved as {p['key']} ({p['total']} in this mod)")))
    ls = o.add_parser("list", help="AI opponents in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: opponents.list_opponents(a.mod),
        lambda p: [print(f"{x['slug']:24} {x['name']}  deck={x.get('deck')} difficulty={x.get('difficulty')} personality={x.get('temperament') or 'auto'}") for x in p["opponents"]]))
    rm = o.add_parser("remove", help="remove an AI opponent"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: opponents.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _story_commands(sub):
    from . import stories
    s = sub.add_parser("story", help="stories: campaigns with acts, chapters, map events, dialogue, choices and battles (Play > Story)").add_subparsers(dest="cmd", required=True)
    n = s.add_parser("new", help="create a story with a first act, chapter, dialogue event and battle to edit")
    n.add_argument("--mod", required=True); n.add_argument("--name", required=True); n.add_argument("--description", default="")
    n.add_argument("--template", default="DBH", choices=list(stories.TEMPLATES), help="installed story whose look (screens, default art) it borrows")
    n.set_defaults(fn=_simple(lambda a: stories.new_story(a.mod, a.name, a.description, a.template),
        lambda p: print(f"{p['mod']}: story {p['story']['name']} in {p['dir']}; edit story.json there, in the app's Stories page, or with tesl story save")))
    ls = s.add_parser("list", help="a mod's stories"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: stories.list_stories(a.mod),
        lambda p: [print(f"{x['slug']:24} {x['name']}  {x['acts']} acts, {x['chapters']} chapters, {x['events']} events, {x['battles']} battles") for x in p["stories"]]))
    sh = s.add_parser("show", help="print a story's JSON"); sh.add_argument("--mod", required=True); sh.add_argument("--story", required=True)
    sh.set_defaults(fn=_simple(lambda a: stories.read_story(a.mod, a.story), lambda p: print(json.dumps(p, indent=1, ensure_ascii=False))))
    sv = s.add_parser("save", help="validate and save a whole story from a JSON file"); sv.add_argument("--mod", required=True); sv.add_argument("--file", required=True)
    sv.set_defaults(fn=_simple(lambda a: stories.save_story(a.mod, json.loads(Path(a.file).read_text(encoding="utf-8")), find_install(a.game)),
        lambda p: print(f"{p['mod']}: saved story {p['story']} ({p['summary']['chapters']} chapters, {p['summary']['events']} events)")))
    f = s.add_parser("file", help="add an image (PNG/JPG) or voice line (WAV/OGG/MP3/FLAC/M4A) to a story's folder")
    f.add_argument("--mod", required=True); f.add_argument("--story", required=True); f.add_argument("--file", required=True); f.add_argument("--name")
    f.set_defaults(fn=_simple(lambda a: stories.add_file(a.mod, a.story, a.file, a.name), lambda p: print(f"{p['story']}: added {p['kind']} {p['file']}")))
    c = s.add_parser("check", help="validate a mod's stories"); c.add_argument("--mod", required=True)
    c.set_defaults(fn=_simple(lambda a: (lambda e: {"valid": not e, "errors": e})(stories.check(a.mod)),
        lambda p: print("stories OK" if p["valid"] else "\n".join(p["errors"]))))
    o = s.add_parser("options", help="templates, installed story maps, discs and portraits, reward kinds"); o.add_argument("--mod")
    o.set_defaults(fn=_simple(lambda a: stories.options(find_install(a.game), a.mod),
        lambda p: [print(f"maps: {len(p['maps'])}, discs: {len(p['discs'])}, portraits: {len(p['portraits'])}"), [print(" ", m["asset"], "-", m["label"]) for m in p["maps"]]]))
    rm = s.add_parser("remove", help="delete a story and its files"); rm.add_argument("--mod", required=True); rm.add_argument("--story", required=True)
    rm.set_defaults(fn=_simple(lambda a: stories.remove_story(a.mod, a.story), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _mode_commands(sub):
    from . import modes
    m = sub.add_parser("mode", help="game modes (custom matches vs the AI, from the Practice screen)").add_subparsers(dest="cmd", required=True)
    ln = m.add_parser("lanes", help="lane types with their rules")
    ln.set_defaults(fn=_simple(lambda a: {"lanes": modes.lanes()}, lambda p: [print(f"{'' if x['implemented'] else '(not yet) '}{x['type']:20} {x['label']:22} {x['description'][:90]}") for x in p["lanes"]]))
    sv = m.add_parser("save", help="create or replace a mode")
    sv.add_argument("--mod", required=True); sv.add_argument("--name", required=True); sv.add_argument("--description", default="")
    sv.add_argument("--lane", action="append", help="TYPE[:SIZE], once or twice (default Field + Shadow)")
    for side in ("player", "opponent"):
        sv.add_argument(f"--{side}-health", type=int); sv.add_argument(f"--{side}-magicka", type=int); sv.add_argument(f"--{side}-runes", type=int)
        sv.add_argument(f"--{side}-extra-cards", type=int); sv.add_argument(f"--{side}-deck"); sv.add_argument(f"--{side}-card", action="append", help="PLACE:CARD (hand, lane1, lane2, support, deck)")
    sv.add_argument("--first", default="random", choices=["random", "player", "opponent"]); sv.add_argument("--difficulty", default="chosen", choices=modes.DIFFICULTIES)
    sv.add_argument("--opponent-name"); sv.add_argument("--board"); sv.add_argument("--reward-gold", type=int, default=0)
    for r in modes.RULES:
        sv.add_argument("--" + r.replace("_", "-"), type=int)
    sv.add_argument("--no-mulligan", action="store_true")
    def side(a, s):
        cards = {}
        for spec in getattr(a, f"{s}_card") or []:
            place, _, card = spec.partition(":")
            cards.setdefault(place, []).append(card)
        return {"health": getattr(a, f"{s}_health"), "magicka": getattr(a, f"{s}_magicka"), "runes": getattr(a, f"{s}_runes"),
                "extra_cards": getattr(a, f"{s}_extra_cards"), "deck": getattr(a, f"{s}_deck"), "cards": cards}
    def lanes(a):
        out = []
        for spec in a.lane or []:
            t, _, size = spec.partition(":")
            out.append({"type": t, "size": int(size or 4)})
        return out or None
    sv.set_defaults(fn=_simple(lambda a: modes.save_mode(find_install(a.game), a.mod, a.name, a.description, lanes(a), side(a, "player"), side(a, "opponent"), a.first,
        a.difficulty, a.opponent_name, {**{r: getattr(a, r) for r in modes.RULES}, "no_mulligan": a.no_mulligan}, a.board, a.reward_gold),
        lambda p: print(f"{p['mod']}: mode {p['mode']['name']} ({p['game_key']}); in game: F10 > Practice mode, then Play > Practice")))
    ls = m.add_parser("list", help="a mod's modes"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: modes.list_modes(a.mod), lambda p: [print(f"{x['slug']:24} {x['name']}  lanes {'/'.join(l['type'] for l in x['lanes'])}") for x in p["modes"]]))
    rm = m.add_parser("remove", help="remove a mode"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: modes.remove_mode(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _emote_commands(sub):
    from . import avatars
    e = sub.add_parser("emote", help="extra emotes beyond the game's eight").add_subparsers(dest="cmd", required=True)
    a = e.add_parser("add", help="an extra emote for one mod avatar, or for every avatar")
    a.add_argument("--mod", required=True); a.add_argument("--text", required=True); a.add_argument("--label", help="button text")
    a.add_argument("--avatar", help="mod avatar (default: every avatar)"); a.add_argument("--audio"); a.add_argument("--like", help="one of the eight, for the AI")
    a.set_defaults(fn=_simple(lambda a: avatars.add_extra_emote(a.mod, a.text, a.label, a.avatar, a.audio, a.like),
        lambda p: print(f"{p['mod']}: extra emote '{p['emote']['label']}' for {p['avatar']} ({p['total']} there)")))
    ls = e.add_parser("list", help="a mod's extra emotes"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: avatars.list_extra_emotes(a.mod),
        lambda p: [print(f"every avatar: {x['label']}: {x['text']}") for x in p['all_avatars']]
                  + [print(f"{k}: {x['label']}: {x['text']}") for k, xs in p['avatars'].items() for x in xs]))
    rm = e.add_parser("remove", help="remove an extra emote"); rm.add_argument("--mod", required=True); rm.add_argument("--emote", required=True)
    rm.add_argument("--avatar")
    rm.set_defaults(fn=_simple(lambda a: avatars.remove_extra_emote(a.mod, a.emote, a.avatar), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _sound_commands(sub):
    from . import sounds
    s = sub.add_parser("sound", help="replace game sounds; mod card voice lines").add_subparsers(dest="cmd", required=True)
    se = s.add_parser("search", help="find game sounds by plain words"); se.add_argument("words", nargs="*"); se.add_argument("--category")
    se.add_argument("--limit", type=int, default=40)
    se.set_defaults(fn=_simple(lambda a: sounds.search(find_install(a.game), " ".join(a.words) or None, a.category, a.limit),
        lambda p: [print(f"{x['id']:48} {x['category_label']:20} {x['label']}  ({len(x['clips'])} takes)") for x in p["sounds"]] + [print(f"{p['total']} found")]))
    r = s.add_parser("replace", help="replace a game sound (all takes and languages)")
    r.add_argument("--mod", required=True); r.add_argument("--sound", required=True, help="id from tesl sound search")
    r.add_argument("--file", action="append", required=True, help="audio file (repeat for a random pick)"); r.add_argument("--volume", type=float, default=1.0)
    r.set_defaults(fn=_simple(lambda a: sounds.replace_sound(find_install(a.game), a.mod, a.sound, a.file, a.volume),
        lambda p: print(f"{p['mod']}: {p['label']} replaced ({p['takes']} takes) by {', '.join(p['files'])}")))
    ls = s.add_parser("list", help="sounds a mod replaces and its card voice lines"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: {**sounds.list_replacements(a.mod), **sounds.card_voices(a.mod)},
        lambda p: [print(f"replaces {x['label']}: {', '.join(x['files'])}") for x in p["sounds"]]
                  + [print(f"{c['card']}: " + ", ".join(f"{k} {v}" for k, v in c['lines'].items() if v)) for c in p["cards"] if any(c['lines'].values())]))
    rm = s.add_parser("restore", help="stop replacing a game sound"); rm.add_argument("--mod", required=True); rm.add_argument("--sound", required=True)
    rm.set_defaults(fn=_simple(lambda a: sounds.remove_replacement(a.mod, a.sound), lambda p: print(f"{p['mod']}: {p['removed']} restored")))
    v = s.add_parser("card-voice", help="a mod card's own voice line")
    v.add_argument("--mod", required=True); v.add_argument("--card", required=True)
    v.add_argument("--line", required=True, help="Play, Attack, Death, Hit, Success, Failure, or Shout1/Shout2/Shout3 (a shout card's clip per shout level)"); v.add_argument("--file")
    v.add_argument("--remove", action="store_true")
    v.set_defaults(fn=_simple(lambda a: sounds.remove_card_voice(a.mod, a.card, a.line) if a.remove else sounds.card_voice(a.mod, a.card, a.line, a.file),
        lambda p: print(f"{p['mod']}: {p['card']} " + (f"{p['removed']} line removed" if 'removed' in p else f"{p['line']} line {p['file']} ({p['seconds']} s)"))))


def _music_commands(sub):
    from . import music
    m = sub.add_parser("music", help="soundtracks for menus, moments and boards").add_subparsers(dest="cmd", required=True)
    n = m.add_parser("add", help="a track from any audio file (converted to OGG)")
    n.add_argument("--mod", required=True); n.add_argument("--name", required=True); n.add_argument("--file", required=True)
    n.add_argument("--context", action="append", required=True, help="where it plays (repeat); see: tesl music contexts")
    n.add_argument("--mode", default="replace", choices=["replace", "rotation"]); n.add_argument("--volume", type=float, default=1.0)
    n.set_defaults(fn=_simple(lambda a: music.add_track(a.mod, a.name, a.file, a.context, a.mode, a.volume),
        lambda p: print(f"{p['mod']}: track {p['track']['name']} ({p['track']['seconds']} s) for {', '.join(p['track']['contexts'])} ({p['track']['mode']})")))
    ls = m.add_parser("list", help="tracks in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: music.list_tracks(a.mod), lambda p: [print(f"{x['slug']:24} {x['name']}  {x['mode']}  {', '.join(x['contexts'])}") for x in p["tracks"]]))
    cx = m.add_parser("contexts", help="where tracks can play"); cx.add_argument("--mod")
    cx.set_defaults(fn=_simple(lambda a: {"contexts": music.contexts(a.mod)}, lambda p: [print(f"{x['context']:40} {x['label']}") for x in p["contexts"]]))
    rm = m.add_parser("remove", help="remove a track"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: music.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _board_edit_commands(b):
    from . import board_edit as be
    flag = lambda s: None if s is None else s.lower() in ("1", "true", "yes", "on")
    mp = b.add_parser("map", help="what can be edited on a game board (objects, lights, effects, animations, textures)")
    mp.add_argument("--base", required=True, choices=list(be.BOARD_NAMES))
    mp.set_defaults(fn=_simple(lambda a: be.board_map(a.base), lambda p: [print(f"{k:10} {x['path'][:70]:70} {x['label']}") for k in ("objects", "lights", "effects", "animations")
                                                                          for x in p[k]] + [print(f"texture    {t['texture']:40} {t['label']}") for t in p["textures"]]))
    ed = b.add_parser("edit", help="change a board's existing objects, textures, lights, effects, animations").add_subparsers(dest="what", required=True)
    def common(p):
        p.add_argument("--mod", required=True); p.add_argument("--board", required=True); p.add_argument("--reset", action="store_true", help="undo this edit")
    o = ed.add_parser("object", help="hide/move/rotate/resize/tint/glow/retexture an object (paths: tesl board map)"); common(o)
    o.add_argument("--path", required=True); o.add_argument("--hide"); o.add_argument("--pos"); o.add_argument("--rot"); o.add_argument("--scale")
    o.add_argument("--offset", help="move by x,y,z board units"); o.add_argument("--tint", help="#rrggbb or r,g,b"); o.add_argument("--glow"); o.add_argument("--image", help="new colour texture")
    o.set_defaults(fn=_simple(lambda a: be.edit_object(a.mod, a.board, a.path, flag(a.hide), a.pos, a.rot, a.scale, a.offset, a.tint, a.glow, a.image, a.reset), lambda p: print(f"{p['object']}: {p['edit']}")))
    t = ed.add_parser("texture", help="a texture everywhere it is used on the board"); common(t); t.add_argument("--texture", required=True); t.add_argument("--image")
    t.set_defaults(fn=_simple(lambda a: be.edit_texture(a.mod, a.board, a.texture, a.image, a.reset), lambda p: print(f"{p['texture']}: {p['file']}")))
    l = ed.add_parser("light", help="one light"); common(l); l.add_argument("--path", required=True); l.add_argument("--enabled"); l.add_argument("--color")
    l.add_argument("--intensity", type=float); l.add_argument("--range", type=float)
    l.set_defaults(fn=_simple(lambda a: be.edit_light(a.mod, a.board, a.path, flag(a.enabled), a.color, a.intensity, a.range, a.reset), lambda p: print(f"{p['light']}: {p['edit']}")))
    lg = ed.add_parser("lighting", help="every light on the board"); common(lg); lg.add_argument("--brightness", type=float); lg.add_argument("--tint")
    lg.set_defaults(fn=_simple(lambda a: be.edit_lighting(a.mod, a.board, a.brightness, a.tint, a.reset), lambda p: print(f"lighting: {p['lighting']}")))
    fx = ed.add_parser("effect", help="a particle effect"); common(fx); fx.add_argument("--path", required=True); fx.add_argument("--enabled"); fx.add_argument("--color")
    fx.add_argument("--speed", type=float); fx.add_argument("--rate", type=float, help="amount, x the original"); fx.add_argument("--size", type=float, help="x the original")
    fx.set_defaults(fn=_simple(lambda a: be.edit_effect(a.mod, a.board, a.path, flag(a.enabled), a.color, a.speed, a.rate, a.size, a.reset), lambda p: print(f"{p['effect']}: {p['edit']}")))
    an = ed.add_parser("animation", help="an animated object"); common(an); an.add_argument("--path", required=True); an.add_argument("--enabled"); an.add_argument("--speed", type=float)
    an.set_defaults(fn=_simple(lambda a: be.edit_animation(a.mod, a.board, a.path, flag(a.enabled), a.speed, a.reset), lambda p: print(f"{p['animation']}: {p['edit']}")))
    ad = b.add_parser("add", help="add your own models, images, lights, particle effects").add_subparsers(dest="what", required=True)
    def place(p):
        p.add_argument("--mod", required=True); p.add_argument("--board", required=True); p.add_argument("--name")
        p.add_argument("--x", type=float, help="spot on the board picture, 0 (left) .. 1"); p.add_argument("--y", type=float, help="0 (top) .. 1")
        p.add_argument("--pos", help="or x,y,z in board units"); p.add_argument("--motion", choices=be.MOTIONS); p.add_argument("--motion-speed", type=float); p.add_argument("--motion-amount", type=float)
    m = ad.add_parser("model", help="a 3D model: OBJ, GLB/glTF, or FBX/.blend/DAE/3DS/STL/PLY/USD (converted with Blender)"); place(m)
    m.add_argument("--file", required=True); m.add_argument("--fit", type=float, default=10.0, help="width on the table in board units (the table is about 100 wide)")
    m.add_argument("--rot"); m.add_argument("--texture"); m.add_argument("--tint"); m.add_argument("--glow")
    m.set_defaults(fn=_simple(lambda a: be.add_model(a.mod, a.board, a.file, a.name, a.x, a.y, a.pos, a.rot, a.fit, None, a.texture, a.tint, a.glow, a.motion, a.motion_speed, a.motion_amount),
        lambda p: print(f"{p['board']}: added {p['added']['slug']} ({p['model']}) at {p['added']['pos']}")))
    im = ad.add_parser("image", help="a flat image on the table (decal, rug, banner)"); place(im); im.add_argument("--file", required=True)
    im.add_argument("--width", type=float, default=12.0); im.add_argument("--rot"); im.add_argument("--tint"); im.add_argument("--glow")
    im.set_defaults(fn=_simple(lambda a: be.add_image(a.mod, a.board, a.file, a.name, a.x, a.y, a.pos, a.width, a.rot, a.tint, a.glow, a.motion, a.motion_speed, a.motion_amount),
        lambda p: print(f"{p['board']}: added {p['added']['slug']} at {p['added']['pos']}")))
    li = ad.add_parser("light", help="a point or spot light"); place(li); li.add_argument("--kind", default="point", choices=["point", "spot"]); li.add_argument("--color", default="#ffcc88")
    li.add_argument("--intensity", type=float, default=1.5); li.add_argument("--range", type=float, default=15.0); li.add_argument("--height", type=float, default=6.0)
    li.set_defaults(fn=_simple(lambda a: be.add_light(a.mod, a.board, a.name, a.x, a.y, a.pos, a.height, a.kind, a.color, a.intensity, a.range, 45.0, None, a.motion, a.motion_speed, a.motion_amount),
        lambda p: print(f"{p['board']}: added {p['added']['slug']} at {p['added']['pos']}")))
    pe = ad.add_parser("effect", help="a particle effect: " + ", ".join(be.PRESETS)); place(pe); pe.add_argument("--preset", required=True, choices=be.PRESETS)
    pe.add_argument("--color"); pe.add_argument("--rate", type=float); pe.add_argument("--size", type=float); pe.add_argument("--speed", type=float); pe.add_argument("--area", type=float)
    pe.set_defaults(fn=_simple(lambda a: be.add_effect(a.mod, a.board, a.preset, a.name, a.x, a.y, a.pos, 0.5, a.color, a.rate, a.size, a.speed, a.area, a.motion),
        lambda p: print(f"{p['board']}: added {p['added']['slug']} at {p['added']['pos']}")))
    mv = b.add_parser("move", help="move or change something you added"); place(mv); mv.add_argument("--item", required=True); mv.add_argument("--rot"); mv.add_argument("--fit", type=float)
    mv.add_argument("--tint"); mv.add_argument("--glow")
    mv.set_defaults(fn=_simple(lambda a: be.move_added(a.mod, a.board, a.item, a.x, a.y, a.pos, a.rot, a.fit, None, a.motion, a.motion_speed, a.motion_amount, a.tint, a.glow),
        lambda p: print(f"{p['board']}: {p['added']['slug']} {p['added']}")))
    rm = b.add_parser("take", help="remove something you added"); rm.add_argument("--mod", required=True); rm.add_argument("--board", required=True); rm.add_argument("--item", required=True)
    rm.set_defaults(fn=_simple(lambda a: be.remove_added(a.mod, a.board, a.item), lambda p: print(f"{p['board']}: removed {p['removed']}")))
    sh = b.add_parser("edits", help="a board's edits"); sh.add_argument("--mod", required=True); sh.add_argument("--board", required=True)
    sh.set_defaults(fn=_simple(lambda a: be.edits(a.mod, a.board), lambda p: print(json.dumps(p["edits"], indent=1))))


def _board_commands(sub):
    from . import boards
    b = sub.add_parser("board", help="new boards (re-skins of the game's five playmats)").add_subparsers(dest="cmd", required=True)
    n = b.add_parser("new", help="a board on one of the five bases: a new table image (cropped to 2:1) and/or edits")
    n.add_argument("--mod", required=True); n.add_argument("--name", required=True); n.add_argument("--image", help="new table painting (omit to keep the base's)")
    n.add_argument("--base", default="Original", choices=list(boards.BASES)); n.add_argument("--mode", default="rotation", choices=["rotation", "replace"])
    _board_edit_commands(b)
    n.add_argument("--size", type=int, default=2048, choices=[2048, 4096])
    n.set_defaults(fn=_simple(lambda a: boards.new_board(a.mod, a.name, a.image, a.base, a.mode, a.size),
        lambda p: print(f"{p['mod']}: board {p['board']['name']} on {p['board']['base']} ({p['board']['mode']})")))
    ls = b.add_parser("list", help="boards in a mod"); ls.add_argument("--mod", required=True)
    ls.set_defaults(fn=_simple(lambda a: boards.list_boards(a.mod), lambda p: [print(f"{x['slug']:24} {x['name']}  {x['base']} {x['mode']}") for x in p["boards"]]))
    rm = b.add_parser("remove", help="remove a board"); rm.add_argument("--mod", required=True); rm.add_argument("--name", required=True)
    rm.set_defaults(fn=_simple(lambda a: boards.remove(a.mod, a.name), lambda p: print(f"{p['mod']}: removed {p['removed']}")))


def _settings_cmd(a):
    from . import settings
    if a.set:
        changes = {}
        for pair in a.set:
            k, _, v = pair.partition("=")
            changes[k.strip()] = v
        settings.save(changes)
    return {**settings.load(), "blender_found": settings.find_blender(), "ffmpeg_found": settings.find_tool("ffmpeg"), "file": str(settings.path())}


def build_parser():
    p = argparse.ArgumentParser(prog="tesl", description="TESL Forge (no game files are modified)")
    p.add_argument("--version", action="version", version=__version__)
    p.add_argument("--game", help="game folder (default: next to the suite)")
    p.add_argument("--json", action="store_true", help="machine-readable output for agents")
    sub = p.add_subparsers(dest="area", required=True)
    sub.add_parser("info", help="locate the game and the workspace").set_defaults(fn=cmd_info)
    st = sub.add_parser("settings", help="this computer's settings (extra game folders, Blender / ffmpeg paths): show, or --set key=value")
    st.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="game_dirs / steam_dirs (separate several with ;), blender, ffmpeg, ffprobe; an empty value = detect automatically")
    st.set_defaults(fn=_simple(_settings_cmd, lambda p: [print(f"{k:13} {v}") for k, v in p.items()]))
    sv = sub.add_parser("serve", help="the suite's app and local API in your browser (127.0.0.1 only)")
    sv.add_argument("--port", type=int, default=8765); sv.add_argument("--no-browser", action="store_true")
    sv.set_defaults(fn=lambda a: (__import__("tesl_suite.api", fromlist=["serve"]).serve(a.port, not a.no_browser, a.game), 0)[1])
    wn = sub.add_parser("window", help="the suite's app in its own window (closing it stops TESL Forge)")
    wn.add_argument("--debug", action="store_true", help="allow the browser developer tools")
    wn.set_defaults(fn=lambda a: __import__("tesl_suite.window", fromlist=["main"]).main(a.game, a.debug))
    a = sub.add_parser("assets", help="asset index and extraction").add_subparsers(dest="cmd", required=True)
    a.add_parser("index", help="rebuild the asset index from bundle manifests").set_defaults(fn=cmd_index)
    from . import catalog
    fd = a.add_parser("find", help="find assets by plain words, with labels (what each is and how a mod can change it)")
    fd.add_argument("words", nargs="*"); fd.add_argument("--category", choices=[k for k, _ in catalog.CATEGORIES]); fd.add_argument("--kind")
    fd.add_argument("--changeable", action="store_true", help="only assets a mod can change"); fd.add_argument("--limit", type=int, default=40)
    fd.set_defaults(fn=_simple(lambda a: catalog.search(find_install(a.game), " ".join(a.words) or None, a.category, a.kind, a.changeable, a.limit),
        lambda p: [print(f"{x['category_label']:18} {x['label'][:70]:70} {('[' + x['change'] + ']') if x['change'] else '':11} {x['path']}") for x in p["assets"]]
                  + [print(f"{p['total']} found")]))
    for name, fn, helptext in (("list", cmd_list, "list indexed assets"), ("export", cmd_export, "extract assets (original resolution)")):
        q = a.add_parser(name, help=helptext)
        q.add_argument("--kind", choices=list(assets.KINDS) + ["other"])
        q.add_argument("--contains")
        q.add_argument("--regex")
        q.add_argument("--bundle", help="bundle path prefix, e.g. contentpack000/cardtextures")
        q.add_argument("--limit", type=int, default=0)
        if name == "export":
            q.add_argument("--out")
        q.set_defaults(fn=fn)
    ca = a.add_parser("export-card-art", help="card art with card names and a manifest")
    ca.add_argument("--contains"); ca.add_argument("--collectible", action="store_true"); ca.add_argument("--limit", type=int, default=0)
    ca.add_argument("--out"); ca.add_argument("--data", help="original card JSON (.jsonl.gz)")
    ca.set_defaults(fn=cmd_card_art)
    c = sub.add_parser("cards", help="card catalog").add_subparsers(dest="cmd", required=True)
    cl = c.add_parser("list", help="list cards")
    cl.add_argument("--contains"); cl.add_argument("--set"); cl.add_argument("--collectible", action="store_true")
    cl.add_argument("--limit", type=int, default=0); cl.add_argument("--data")
    cl.set_defaults(fn=cmd_cards)
    _mod_commands(sub)
    _replace_commands(sub)
    _avatar_commands(sub)
    _cardback_commands(sub)
    _board_commands(sub)
    _music_commands(sub)
    _sound_commands(sub)
    _emote_commands(sub)
    _mode_commands(sub)
    _story_commands(sub)
    _opponent_commands(sub)
    _playtest_commands(sub)
    _pack_commands(sub)
    _translate_commands(sub)
    _bulk_commands(sub)
    pv = sub.add_parser("preview", help="cards drawn by the game itself (starts TESL: Everlasting hidden; the game must be closed)")
    pv.add_argument("--mod", required=True); pv.add_argument("--card", action="append", help="only these cards (name or id); repeat")
    def run_preview(a):
        from . import previews
        r = previews.render(find_install(a.game), a.mod, a.card, wait=True)
        _emit(a, r, lambda p: (print(p.get("message", "")), [print("  ", x) for x in p.get("problems", [])],
                               print(f"pictures in {previews.folder(a.mod)}")))
        return 0 if r.get("state") == "done" else 1
    pv.set_defaults(fn=run_preview)
    f = sub.add_parser("search", help="search every mod (cards, decks, avatars, opponents, boards, music, sounds, modes, stories, replaced images)")
    f.add_argument("query")
    def run_search(a):
        from . import search
        _emit(a, search.search(a.query), lambda p: [print(f"{h['kind']:16} {h['name']:40} {h['mod']}{'  (' + h['note'] + ')' if h.get('note') else ''}") for h in p["results"]] or print("no results"))
        return 0
    f.set_defaults(fn=run_search)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    from .game import write_location_pointer
    write_location_pointer()
    try:
        from . import fsutil
        with fsutil.operation("tesl " + " ".join(a for a in (argv if argv is not None else sys.argv[1:]) if not a.startswith("--"))[:80]):
            return args.fn(args) or 0
    except Exception as ex:
        if args.json:
            print(json.dumps({"error": f"{type(ex).__name__}: {ex}"}))
        else:
            print(f"error: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
