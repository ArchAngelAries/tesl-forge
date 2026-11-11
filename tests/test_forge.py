"""TESL Forge tests (standard library only).

Run from the TESL Forge folder:  .venv\\Scripts\\python.exe -X utf8 -m unittest discover -s tests -v
Tests work on throwaway copies of the sample mod (mods/zz-test-*) and remove them afterwards; they never change the
sample mod, other mods or the enabled-mod list. Tests that need the game's card data are skipped when the game is not found.
"""
from __future__ import annotations

import json
import shutil
import threading
import unittest
import urllib.error
import urllib.request
import uuid
from http.server import ThreadingHTTPServer

from tesl_suite import compat, details, fsutil, mods, opponents, packs, search, starters, translations
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


if __name__ == "__main__":
    unittest.main()
