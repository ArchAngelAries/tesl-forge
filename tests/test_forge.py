"""TESL Forge tests (standard library only).

Run from the TESL Forge folder:  .venv\\Scripts\\python.exe -X utf8 -m unittest discover -s tests -v
Tests work on throwaway copies of the sample mod (mods/zz-test-*) and remove them afterwards; they never change the
sample mod, other mods or the enabled-mod list. Tests that need the game's card data are skipped when the game is not found.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from tesl_suite import assets, bulk, compat, details, fsutil, mods, opponents, packs, search, settings, starters, translations
from tesl_suite.game import workspace

try:
    from tesl_suite import api
    GAME = api._game()
except Exception:   # no game install on this computer
    GAME = None

SAMPLE = "sample-skyrim"


def needs_sample(test):
    return unittest.skipIf(not (mods.mod_dir(SAMPLE) / "mod.json").is_file(),
                           "the sample mod is not installed (install TESL-Forge-Sample-Mod from Load order to run this)")(test)


def needs_game(test):
    return unittest.skipIf(GAME is None, "the game install was not found")(test)


class TempMod:
    """A copy of the sample mod (own ids) that is deleted afterwards, with its undo history."""
    def __init__(self, copy: bool = True):
        self.id = "zz-test-" + uuid.uuid4().hex[:8]
        self.copy = copy

    def __enter__(self):
        self.active_before = mods.DEPLOY.read_bytes() if mods.DEPLOY.is_file() else None
        if self.copy:
            starters.copy_mod(SAMPLE, self.id, "Test copy")
        else:
            mods.new_mod(self.id, "Test mod")
        return self.id

    def __exit__(self, *exc):
        shutil.rmtree(mods.mod_dir(self.id), ignore_errors=True)
        shutil.rmtree(workspace() / "history" / self.id, ignore_errors=True)
        if self.active_before is not None:
            mods.DEPLOY.write_bytes(self.active_before)


class FileSafety(unittest.TestCase):
    def test_atomic_write_undo_redo_keeps_bytes(self):
        with TempMod(copy=False) as mid:
            p = mods.mod_dir(mid) / "note.json"
            p.write_bytes(b'{"a": 1}\r\n')
            before = p.read_bytes()
            with fsutil.operation("change"):
                fsutil.atomic_write(p, '{"a": 2}\n')
            self.assertEqual(p.read_text(encoding="utf-8"), '{"a": 2}\n')
            fsutil.undo(mid)
            self.assertEqual(p.read_bytes(), before, "undo restores the exact bytes, line endings included")
            fsutil.redo(mid)
            self.assertEqual(p.read_text(encoding="utf-8"), '{"a": 2}\n')

    def test_trash_is_undoable(self):
        with TempMod(copy=False) as mid:
            p = mods.mod_dir(mid) / "gone.txt"
            p.write_text("x", encoding="utf-8")
            with fsutil.operation("delete"):
                fsutil.trash(p, mid)
            self.assertFalse(p.exists())
            fsutil.undo(mid)
            self.assertTrue(p.exists())


class Compatibility(unittest.TestCase):
    def test_version_ranges(self):
        for v, r, ok in [("1.2.3", "*", True), ("1.2.3", ">=1.2", True), ("1.1.9", ">=1.2", False), ("1.9.0", "^1.2", True),
                         ("2.0.0", "^1.2", False), ("1.2.9", "~1.2.3", True), ("1.3.0", "~1.2.3", False), ("1.4.0", ">=1.2 <1.5", True)]:
            self.assertEqual(compat.satisfies(v, r), ok, f"{v} in {r}")

    @needs_sample
    def test_features_need_engine_levels(self):
        f = compat.features(SAMPLE)
        for feat in ("cards", "stories", "AI opponents", "card packs"):
            self.assertIn(feat, f)
        self.assertGreaterEqual(compat.required_engine(f), 54)
        self.assertEqual(compat.multiplayer_class(["music", "boards"]), "local")
        self.assertEqual(compat.multiplayer_class(["avatars"]), "cosmetic")
        self.assertEqual(compat.multiplayer_class(["cards"]), "gameplay")


class Starters(unittest.TestCase):
    @needs_sample
    def test_copy_gets_own_ids_and_references(self):
        with TempMod() as mid:
            src = {c["ResourceId"]["Id"] for c in mods.mod_cards(SAMPLE)}
            dst = {c["ResourceId"]["Id"] for c in mods.mod_cards(mid)}
            self.assertEqual(len(src), len(dst))
            self.assertFalse(src & dst, "copied cards need new ids")
            deck = json.loads((mods.mod_dir(mid) / "decks" / "skyrim-heroes.json").read_text(encoding="utf-8"))
            self.assertTrue(deck["type_name"].startswith(f"mod.{mid}."))
            self.assertTrue(all(e["id"] in dst or e["id"] not in src for e in deck["cards"]), "deck points at the copy's cards")
            mode = json.loads((mods.mod_dir(mid) / "modes" / "modes.json").read_text(encoding="utf-8"))["modes"][0]
            self.assertEqual(mode.get("ai"), f"{mid}/draugr-warlord")


class Details(unittest.TestCase):
    def test_details_and_release(self):
        with TempMod(copy=False) as mid:
            d = details.update(mid, {"dependencies": [{"id": "base-pack", "version": ">=1.2"}], "conflicts": "old-mod other-mod"})
            self.assertEqual(d["dependencies"], [{"id": "base-pack", "version": ">=1.2"}])
            self.assertEqual(d["conflicts"], ["old-mod", "other-mod"])
            for bad in ({"version": "1.2"}, {"conflicts": [mid]}, {"conflicts": ["base-pack"]}, {"dependencies": [{"id": "x-y", "version": "soon"}]}):
                with self.assertRaises(ValueError):
                    details.update(mid, bad)
            r = details.add_change(mid, "First release", "minor")
            self.assertEqual(r["version"], "1.1.0")
            self.assertIn("First release", details.changelog_md(mid))
            with self.assertRaises(ValueError):
                details.add_change(mid, "")


class Content(unittest.TestCase):
    @needs_sample
    @needs_game
    def test_sample_mod_is_valid(self):
        v = mods.validate(GAME, SAMPLE)
        self.assertTrue(v["valid"], v["errors"])

    @needs_sample
    @needs_game
    def test_keyword_written_twice_is_flagged(self):
        from tesl_suite import edits
        with TempMod() as mid:
            card = next(c for c in mods.mod_cards(mid) if c["Name"] == "Whiterun Wolfcaller")
            twice = lambda: [w for w in mods.validate(GAME, mid)["warnings"] if "shown twice" in w]
            self.assertEqual(twice(), [])
            edits.edit_card(GAME, mid, card["ResourceId"]["UniqueName"], text="<b>Guard</b><br>When it attacks, deal 3 damage.")
            self.assertEqual(len(twice()), 1)

    def test_problem_locations(self):
        self.assertEqual(mods.locate("deck heroes: 49 cards")["view"], "decks")
        self.assertEqual(mods.locate("AI opponent Elder: portrait file missing: x"), {"view": "opponents", "item": "Elder"})
        self.assertEqual(mods.locate("pack starter: no cards")["view"], "packs")
        self.assertEqual(mods.locate("translation de: 3 of 9 texts")["view"], "translations")
        self.assertEqual(mods.locate("saga/act-1: x", [], ["saga"])["view"], "stories")

    @needs_sample
    def test_opponent_rules(self):
        with TempMod() as mid:
            r = opponents.save_opponent(mid, {"name": "Test Rival", "portrait": "avatar:draugr", "difficulty": "Expert", "temperament": "Playful"})
            self.assertEqual(r["key"], f"{mid}/test-rival")
            for bad in ({"name": "B", "difficulty": "Godlike"}, {"name": "B", "temperament": "Grumpy"}, {"name": "B", "portrait": "avatar:nobody"}):
                with self.assertRaises(ValueError):
                    opponents.save_opponent(mid, bad)
            opponents.remove(mid, "Test Rival")
            self.assertNotIn(f"{mid}/test-rival", opponents.keys([mid]))

    @needs_sample
    @needs_game
    def test_pack_rules(self):
        with TempMod() as mid:
            r = packs.save_pack(GAME, mid, {"name": "Mix", "pool": ["0_Core", "Skyrim"], "price": 120, "odds": {"common": 1, "rare": 1}})
            self.assertEqual(r["store_key"], f"modpack:{mid}/mix")
            for bad in ({"name": "B", "pool": ["Nope"]}, {"name": "B", "cards": 13}, {"name": "B", "cards_list": [{"card": "Not A Real Card"}]},
                        {"name": "B", "odds": {"common": 0}}, {"name": "B", "price": -1}):
                with self.assertRaises(ValueError):
                    packs.save_pack(GAME, mid, bad)

    @needs_sample
    def test_translations_round_trip(self):
        with TempMod() as mid:
            texts = translations.strings(mid)
            self.assertIn("Whiterun Wolfcaller", texts)
            r = translations.import_csv(mid, "fr", "english,fr\nWhiterun Wolfcaller,Invocateur de loups\nNot in mod,x\n")
            self.assertEqual(r["not_in_mod"], ["Not in mod"])
            rows = {x["english"]: x["translation"] for x in translations.table(mid, "fr")["rows"]}
            self.assertEqual(rows["Whiterun Wolfcaller"], "Invocateur de loups")
            self.assertIn("Invocateur de loups", translations.export_csv(mid, "fr"))
            with self.assertRaises(ValueError):
                translations.save(mid, "../evil", {"a": "b"})

    @needs_sample
    def test_preview_items_match_engine_names(self):
        from tesl_suite import previews
        items = previews.extras(SAMPLE)
        kinds = {k for _, k, _, _ in items}
        self.assertEqual(kinds, {"backs", "decks", "boards"}, items)
        for line, kind, slug, name in items:
            self.assertIn(line.split(":", 1)[0], ("back", "deck", "board"))
            self.assertNotIn("/", name)   # the engine writes board keys (<mod>/<slug>) with '_' in file names
        self.assertEqual(previews._file_safe('a/b\\c:d*e'), "a_b_c_d_e")

    @needs_sample
    def test_search_finds_across_kinds(self):
        r = search.search("draugr")
        kinds = {h["kind"] for h in r["results"] if h["mod"] == SAMPLE}
        self.assertTrue({"cards", "AI opponents"} <= kinds, kinds)
        with self.assertRaises(ValueError):
            search.search("x")


class ApiSafety(unittest.TestCase):
    """The local API answers only this computer's own app."""
    @classmethod
    def setUpClass(cls):
        from tesl_suite import api as api_mod
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), api_mod.Handler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close()

    def call(self, path, method="GET", headers=None, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method=method, headers=headers or {},
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()

    def test_lists_mods(self):
        status, body = self.call("/api/mods")
        self.assertEqual(status, 200)
        listed = [m["id"] for m in json.loads(body)["mods"]]
        if (mods.mod_dir(SAMPLE) / "mod.json").is_file():
            self.assertIn(SAMPLE, listed)

    def test_foreign_host_refused(self):
        self.assertEqual(self.call("/api/mods", headers={"Host": "evil.example"})[0], 403)

    def test_cross_site_change_refused(self):
        status, _ = self.call(f"/api/mods/{SAMPLE}/undo", "POST", {"Origin": "https://evil.example", "Content-Type": "application/json"}, {})
        self.assertEqual(status, 403)

    def test_path_traversal_refused(self):
        status, _ = self.call("/mod-file/../deploy/active-mods.json")
        self.assertIn(status, (400, 403, 404))
        status, _ = self.call("/api/mods/..%2Fdeploy")
        self.assertIn(status, (400, 403, 404))


class DeckSpecs(unittest.TestCase):
    """Deck lists: ";" / new lines / a real list / a JSON array, and card names that contain commas."""

    def names(self, spec):
        return [(c["Name"], n) for c, n in mods.deck_entries(GAME, spec)]

    @needs_game
    def test_semicolons_and_new_lines(self):
        want = [("Miraak, Dragonborn", 2), ("Fiery Imp", 3), ("Ayrenn, Dominion Queen", 1)]
        self.assertEqual(self.names("Miraak, Dragonborn x2; Fiery Imp x3; Ayrenn, Dominion Queen"), want)
        self.assertEqual(self.names("Miraak, Dragonborn x2\nFiery Imp x3\nAyrenn, Dominion Queen"), want)

    @needs_game
    def test_real_lists(self):
        want = [("Miraak, Dragonborn", 2), ("Fiery Imp", 3)]
        self.assertEqual(self.names(["Miraak, Dragonborn x2", "Fiery Imp x3"]), want)
        self.assertEqual(self.names([{"name": "Miraak, Dragonborn", "count": 2}, {"name": "Fiery Imp", "count": 3}]), want)
        self.assertEqual(self.names(json.dumps(["Miraak, Dragonborn x2", "Fiery Imp x3"])), want)
        self.assertEqual(self.names([["Miraak, Dragonborn", 2], ["Fiery Imp", 3]]), want)
        fiery = mods.find_card(GAME, "Fiery Imp")["ResourceId"]["Id"]
        self.assertEqual(self.names([{"id": fiery, "count": 2}]), [("Fiery Imp", 2)])

    @needs_game
    def test_old_comma_specs_still_work(self):
        self.assertEqual(self.names("Fiery Imp x3, Fiery Imp"), [("Fiery Imp", 3), ("Fiery Imp", 1)])
        self.assertEqual(self.names("Fiery Imp x3, Miraak, Dragonborn x2, Fiery Imp"),
                         [("Fiery Imp", 3), ("Miraak, Dragonborn", 2), ("Fiery Imp", 1)])
        self.assertEqual(self.names("Miraak, Dragonborn, Fiery Imp x2"), [("Miraak, Dragonborn", 1), ("Fiery Imp", 2)])

    @needs_game
    def test_unknown_card_is_a_clear_error(self):
        with self.assertRaises(ValueError) as cm:
            mods.deck_entries(GAME, "Fiery Imp x3; No Such Card Anywhere")
        self.assertIn("No Such Card Anywhere", str(cm.exception))
        with self.assertRaises(ValueError):
            mods.deck_entries(GAME, "")

    @needs_game
    def test_api_passes_lists_through(self):
        spec = [{"name": "Miraak, Dragonborn", "count": 2}]
        self.assertEqual(api._deck_spec(spec), spec)
        self.assertEqual(api._deck_spec("A x2, B"), "A x2, B")
        self.assertEqual(self.names(api._deck_spec(spec)), [("Miraak, Dragonborn", 2)])


class Settings(unittest.TestCase):
    """Machine-specific places come from the settings file, the registry, the environment or PATH: never from the code."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-settings-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        p = mock.patch.object(settings, "path", lambda: self.tmp / "workspace" / "settings.json")
        p.start()
        self.addCleanup(p.stop)

    def test_defaults_are_empty(self):
        s = settings.load()
        self.assertEqual((s["game_dirs"], s["steam_dirs"], s["blender"], s["ffmpeg"]), ([], [], "", ""))

    def test_save_roundtrip_keeps_other_keys(self):
        f = settings.path()
        f.parent.mkdir(parents=True)
        f.write_text(json.dumps({"game_dirs": ["X:/one"], "future_key": 5}), encoding="utf-8")
        out = settings.save({"steam_dirs": "X:/s1;X:/s2"})
        self.assertEqual(out["steam_dirs"], ["X:/s1", "X:/s2"])
        self.assertEqual(out["game_dirs"], ["X:/one"])
        self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["future_key"], 5)
        settings.remember_game_dir("X:/two")
        self.assertEqual(settings.get("game_dirs"), ["X:/two", "X:/one"])

    def test_unknown_key_and_missing_file_refused(self):
        with self.assertRaises(ValueError):
            settings.save({"nonsense": 1})
        with self.assertRaises(ValueError):
            settings.save({"blender": str(self.tmp / "nope" / "blender.exe")})

    def test_game_dirs_feed_the_candidates(self):
        from tesl_suite import game
        settings.save({"game_dirs": [str(self.tmp / "my-tesl")]})
        self.assertIn(self.tmp / "my-tesl", game._candidates())

    def test_blender_setting_beats_search_and_search_uses_environment(self):
        exe = self.tmp / "pf" / "Blender Foundation" / "Blender 4.2" / "blender.exe"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(b"")
        with mock.patch("shutil.which", return_value=None), mock.patch.dict(os.environ, {v: str(self.tmp / "pf") for v in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")}):
            self.assertEqual(settings.find_blender(), str(exe))
            other = self.tmp / "mine" / "blender.exe"
            other.parent.mkdir()
            other.write_bytes(b"")
            settings.save({"blender": str(other)})
            self.assertEqual(settings.find_blender(), str(other))

    def test_ffmpeg_setting(self):
        exe = self.tmp / "ff" / "ffmpeg.exe"
        exe.parent.mkdir()
        exe.write_bytes(b"")
        with mock.patch("shutil.which", return_value=None):
            self.assertIsNone(settings.find_tool("ffmpeg"))
            settings.save({"ffmpeg": str(exe)})
            self.assertEqual(settings.find_tool("ffmpeg"), str(exe))

    def test_no_machine_paths_in_the_code(self):
        root = Path(__file__).resolve().parent.parent
        rx = re.compile(r"\b[A-Za-z]:[\\/]+(?:Program Files|Users|Gaming|Games|Steam|SteamLibrary)|[\\/]Users[\\/][A-Za-z0-9._-]+[\\/]", re.I)
        offenders = []
        for folder in ("tesl_suite", "tools"):
            for f in (root / folder).rglob("*"):
                rel = f.relative_to(root).parts
                if f.suffix in (".py", ".js", ".html", ".cmd", ".iss") and rel[:2] != ("tesl_suite", "data") and f.name != "privacy_scan.py":
                    for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                        if rx.search(line):
                            offenders.append(f"{f.relative_to(root)}:{n}: {line.strip()[:80]}")
        self.assertEqual(offenders, [])


class Caching(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="forge-cache-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        for target, name, value in ((mods, "MODS", self.tmp / "mods"), (compat, "_fp_cache_file", lambda: self.tmp / "fp.json")):
            p = mock.patch.object(target, name, value)
            p.start()
            self.addCleanup(p.stop)
        compat._FP_CACHE.clear()
        mods._CARD_FILES.clear()
        self.root = self.tmp / "mods" / "zz-cache"
        (self.root / "cards").mkdir(parents=True)
        (self.root / "mod.json").write_text('{"id": "zz-cache"}', encoding="utf-8")
        (self.root / "art.bin").write_bytes(b"abc" * 1000)
        self.card = self.root / "cards" / "a.json"
        self.card.write_text(json.dumps({"Name": "A", "ResourceId": {"Id": 1, "UniqueName": "a"}}), encoding="utf-8")

    def naive(self):
        import hashlib
        h = hashlib.sha256()
        for p in sorted(x for x in self.root.rglob("*") if x.is_file()):
            h.update(p.relative_to(self.root).as_posix().encode("utf-8") + b"\0")
            h.update(p.read_bytes())
        return h.hexdigest()

    def test_fingerprint_value_is_unchanged_and_reused(self):
        first = compat.fingerprint("zz-cache")
        self.assertEqual(first, self.naive())
        with mock.patch.object(Path, "read_bytes", side_effect=AssertionError("hashed again")):
            self.assertEqual(compat.fingerprint("zz-cache"), first)
            compat._FP_CACHE.clear()      # a new run: remembered in the cache file
            self.assertEqual(compat.fingerprint("zz-cache"), first)

    def test_fingerprint_follows_changes(self):
        before = compat.fingerprint("zz-cache")
        (self.root / "art.bin").write_bytes(b"abd" * 1000)       # same size; the modification time differs
        os.utime(self.root / "art.bin", ns=(10**18, 10**18))
        after = compat.fingerprint("zz-cache")
        self.assertNotEqual(before, after)
        self.assertEqual(after, self.naive())
        (self.root / "new.txt").write_text("x", encoding="utf-8")
        self.assertEqual(compat.fingerprint("zz-cache"), self.naive())

    def test_card_files_are_read_once_until_they_change(self):
        self.assertEqual(mods.mod_cards("zz-cache")[0]["Name"], "A")
        with mock.patch.object(Path, "read_text", side_effect=AssertionError("read again")):
            cards = mods.mod_cards("zz-cache")
            cards[0]["Name"] = "changed by caller"
            self.assertEqual(mods.mod_cards("zz-cache")[0]["Name"], "A", "callers get their own copies")
            self.assertEqual(mods.mod_cards_shared("zz-cache")[0]["Name"], "A")
        self.card.write_text(json.dumps({"Name": "B", "ResourceId": {"Id": 1, "UniqueName": "a"}}), encoding="utf-8")
        os.utime(self.card, ns=(10**18, 10**18))
        self.assertEqual(mods.mod_cards("zz-cache")[0]["Name"], "B")

    def test_asset_lookups_are_built_once(self):
        index = {"entries": [{"path": "Assets/X/One.png", "kind": "texture", "bundle": "b"}, {"path": "Assets/X/Two.png", "kind": "texture", "bundle": "b"}]}
        calls = []

        def key(e):
            calls.append(1)
            return e["path"].lower()
        t1 = assets.lookup(index, "t", key)
        t2 = assets.lookup(index, "t", key)
        self.assertIs(t1, t2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(assets.by_path(index)["assets/x/two.png"]["bundle"], "b")
        self.assertIs(assets.by_path(index), assets.by_path(index))

    def test_asset_index_is_parsed_once(self):
        f = self.tmp / "asset-index.json"
        f.write_text(json.dumps({"game": "G", "entries": []}), encoding="utf-8")
        fake = type("G", (), {"root": "G"})()
        with mock.patch.object(assets, "index_path", lambda: f):
            assets._INDEX_CACHE.clear()
            a = assets.load_index(fake)
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("parsed again")):
                self.assertIs(assets.load_index(fake), a)
            f.write_text(json.dumps({"game": "G", "entries": [{"path": "p", "kind": "other", "bundle": "b"}]}), encoding="utf-8")
            os.utime(f, ns=(10**18, 10**18))
            self.assertEqual(len(assets.load_index(fake)["entries"]), 1)


class BulkSounds(unittest.TestCase):
    @needs_game
    def test_files_are_matched_by_name_with_a_result_each(self):
        from tesl_suite import sounds
        snd = next(s for s in sounds.catalog(GAME) if s["id"].startswith("announcer:") and len(s["clips"]) == 1)
        calls = []
        with mock.patch.object(sounds, "replace_sound", lambda g, m, sid, files, vol=1.0: calls.append((sid, files))), \
                mock.patch.object(bulk, "read_mod", lambda m: {}), mock.patch.object(bulk, "mod_cards", lambda m: []):
            r = bulk.sounds_by_name(GAME, "x", {snd["clips"][0] + ".wav": "/tmp/a.wav", "nothing matches this.wav": "/tmp/b.wav"})
        self.assertEqual(calls, [(snd["id"], ["/tmp/a.wav"])])
        self.assertEqual([x["file"] for x in r["rows"]], [snd["clips"][0] + ".wav"])
        self.assertEqual([x["file"] for x in r["failed"]], ["nothing matches this.wav"])


if __name__ == "__main__":
    unittest.main()


class SmallFrames(unittest.TestCase):
    """Deck-list band centred on the face; history/hover shift never leaves part of the frame empty."""
    def test_values(self):
        from tesl_suite.framing import small_frames
        f = small_frames(0.15)
        self.assertAlmostEqual(0.41 + f["ListImageOffsetY"] + 0.09, 0.15, places=3)
        self.assertLessEqual(abs(f["HistoryLogItemImageOffsetY"]), (f["HistoryLogItemImageScale"] - 1) / 2 + 1e-9)
        self.assertEqual(f["HangerImageOffsetY"], 0.0)   # scale 1 leaves no room to move
        self.assertGreaterEqual(small_frames(0.0)["ListImageOffsetY"], -0.41)

