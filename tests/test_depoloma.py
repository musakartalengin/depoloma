"""Tests for the scan engine and the findings. Standard library only:

    python -m unittest discover -s tests -v

Every test builds its own small tree in a temporary folder.
"""
import os
import posixpath
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from depoloma import cleaner, insights, report, rules, system  # noqa: E402
from depoloma import scanner as scanner_mod  # noqa: E402
from depoloma.scanner import F_PROJECT, F_REGEN, Scanner  # noqa: E402

KB = 1024
MB = 1024 * KB


def make(root, rel, size=0, age_days=0):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)
    if age_days:
        t = time.time() - age_days * 86400
        os.utime(path, (t, t))
    return path


def scan(root, threads=2):
    # inherit_context=False: the temp folder lives under a "temp files" rule, which would
    # (correctly) switch project detection off for everything below it.
    return Scanner([root], ruleset=rules.RuleSet(home=os.path.expanduser("~")), threads=threads,
                   inherit_context=False).run()


def child(node, name):
    for c in node.children or ():
        if c.name == name:
            return c
    raise AssertionError("no child %r in %r" % (name, node.name))


class ScannerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_sizes_and_counts(self):
        make(self.root, "a/big.bin", 3 * MB)
        make(self.root, "a/small.txt", 10 * KB)
        make(self.root, "b/c/d.dat", 300 * KB)
        s = scan(self.root)
        r = s.root_nodes[0]
        self.assertEqual(s.state, "done")
        self.assertEqual(r.nfiles, 3)
        self.assertEqual(r.ndirs, 3)
        written = 3 * MB + 10 * KB + 300 * KB
        self.assertGreaterEqual(r.size, written)
        self.assertLess(r.size, written + 64 * KB)          # only cluster rounding on top
        a = child(r, "a")
        self.assertEqual([f[0] for f in a.files], ["big.bin"])   # ≥ 1 MiB files are kept by name
        self.assertEqual(a.small_n, 1)

    def test_same_totals_with_any_thread_count(self):
        for i in range(40):
            make(self.root, "d%d/sub%d/f.bin" % (i % 7, i), 40 * KB)
        totals = set()
        for threads in (1, 2, 6):
            r = scan(self.root, threads).root_nodes[0]
            totals.add((r.size, r.nfiles, r.ndirs))
        self.assertEqual(len(totals), 1, totals)

    def test_project_and_regenerable_parts(self):
        make(self.root, "work/shop/package.json", 200)
        make(self.root, "work/shop/src/index.js", 20 * KB)
        make(self.root, "work/shop/node_modules/lib/index.js", 600 * KB)
        make(self.root, "work/notes/readme.txt", 5 * KB)
        s = scan(self.root)
        shop = child(child(s.root_nodes[0], "work"), "shop")
        self.assertTrue(shop.flags & F_PROJECT)
        self.assertIn("node", [k for k in insights.project_kinds(shop.proj[0])])
        nm = child(shop, "node_modules")
        self.assertTrue(nm.flags & F_REGEN)
        self.assertEqual(nm.rule.id, "node_modules")
        self.assertEqual(shop.proj[1], nm.size)                  # regenerable bytes = node_modules
        self.assertFalse(child(child(s.root_nodes[0], "work"), "notes").flags & F_PROJECT)
        self.assertEqual(s.rule_totals["node_modules"], [1, nm.size])

    def test_activity_ignores_regenerable_folders(self):
        make(self.root, "old/package.json", 100, age_days=400)
        make(self.root, "old/main.js", 30 * MB, age_days=400)
        make(self.root, "old/node_modules/x/x.js", 300 * KB)      # fresh, but must not count as activity
        s = scan(self.root)
        old = child(s.root_nodes[0], "old")
        self.assertLess(old.newest_src, time.time() - 399 * 86400)
        self.assertGreater(old.newest, time.time() - 86400)
        summary = insights.build_summary(s, [])
        stale = [f for f in summary["findings"] if f["id"] == "stale_projects"]
        self.assertEqual(len(stale), 1)
        self.assertEqual(stale[0]["items"][0]["name"], "old")

    def test_tiny_folders_are_folded_but_still_counted(self):
        for i in range(30):
            make(self.root, "l1/l2/l3/l4/l5/tiny%d/f.txt" % i, 2 * KB)
        make(self.root, "l1/l2/l3/l4/l5/large/f.bin", 2 * MB)
        s = scan(self.root)
        r = s.root_nodes[0]
        self.assertEqual(r.nfiles, 31)
        l5 = s.find(os.path.join(self.root, "l1", "l2", "l3", "l4", "l5"))
        self.assertEqual([c.name for c in l5.children], ["large"])
        self.assertEqual(l5.tiny_n, 30)
        # on Linux / macOS a folder also owns the blocks of its directory entry (as `du` counts them)
        own = 0 if os.name == "nt" else os.lstat(os.path.join(self.root, "l1", "l2", "l3", "l4", "l5")).st_blocks * 512
        self.assertEqual(l5.size, sum(c.size for c in l5.children) + l5.tiny_b + own)

    def test_summary_adds_up(self):
        make(self.root, "docs/a.pdf", 2 * MB)
        make(self.root, "proj/Cargo.toml", 100)
        make(self.root, "proj/src/main.rs", 1200 * KB)          # projects under 1 MB are not listed
        s = scan(self.root)
        summary = insights.build_summary(s, [])
        self.assertEqual(sum(c["size"] for c in summary["cats"]), s.root_nodes[0].size)
        self.assertEqual(summary["files"], 3)
        self.assertEqual([p["name"] for p in summary["projects"]], ["proj"])
        self.assertEqual(summary["bigfiles"], [])                # nothing ≥ 20 MB here
        node = insights.node_json(s, s.root_nodes[0], deep=True)
        self.assertEqual({i["name"] for i in node["items"]}, {"docs", "proj"})

    def test_cancel_keeps_a_consistent_tree(self):
        for i in range(50):
            make(self.root, "x%d/f.bin" % i, 10 * KB)
        sc = Scanner([self.root], threads=2, inherit_context=False)
        sc.cancel()
        sc.run()
        self.assertEqual(sc.state, "cancelled")
        self.assertIsNotNone(insights.build_summary(sc, []))


class RuleTests(unittest.TestCase):
    def test_linux_rules(self):
        rs = rules.RuleSet("linux")
        self.assertEqual(rs.match_path("/var/lib/docker").id, "docker_data")
        self.assertEqual(rs.match_path("/home/ada/.cache").id, "shared_cache")
        self.assertEqual(rs.match_path("/home/ada/.cache/pip").id, "pip_cache")
        self.assertEqual(rs.match_path("/home/ada/work/app/node_modules").id, "node_modules")
        self.assertIsNone(rs.match_path("/home/ada/work/app"))

    def test_windows_rules(self):
        rs = rules.RuleSet("win", home=r"C:\Users\Ada")
        self.assertEqual(rs.match_path(r"C:\Windows").id, "windows")
        self.assertEqual(rs.match_path(r"C:\Users\Ada\AppData\Local\Temp").id, "user_temp")
        self.assertEqual(rs.match_path(r"D:\Users\Bob\AppData\Local\Google\Chrome\User Data\Default\Cache").id, "app_cache")
        self.assertEqual(rs.match_path(r"C:\Users\Ada\Downloads").id, "downloads")
        self.assertIsNone(rs.match_path(r"C:\Windows\Temp\Downloads"))

    def test_every_rule_is_explained_in_both_languages(self):
        for plat in ("win", "mac", "linux"):
            for rid, tx in rules.RuleSet(plat).texts().items():
                for lang in ("tr", "en"):
                    title, what = tx[lang][0], tx[lang][1]
                    self.assertTrue(title and what, "%s (%s) needs a title and a description" % (rid, lang))
                self.assertIn(tx["act"], rules.ACTS)

    def test_ai_tools_and_fake_caches_are_recognised(self):
        rs = rules.RuleSet("win", home=r"C:\Users\Ada")
        home = "C:\\Users\\Ada\\"
        expect = {
            ".claude": "ai_context", ".codex": "ai_context", ".gemini": "ai_context",
            r"AppData\Local\Temp\claude": "ai_context",
            r"AppData\Roaming\Code\User\workspaceStorage": "ai_context",
            r"AppData\Roaming\Cursor\User\globalStorage": "ai_context",
            r"AppData\Roaming\Claude": "ai_app", r"AppData\Roaming\Antigravity": "ai_app",
            r"AppData\Local\Packages\OpenAI.Codex_2p2nqsd0c76g0": "ai_app",
            r"AppData\Local\Packages\OpenAI.ChatGPT-Desktop_2p2nqsd0c76g0": "ai_app",
            r"AppData\Local\Packages\Claude_pzs8sxrjxfjjc": "ai_app",
            r"AppData\Local\CapCut\User Data\Cache": "capcut_data",
            r"AppData\Local\Google\Chrome\User Data\Default\Cache": "app_cache",
        }
        for rel, rid in expect.items():
            self.assertEqual(rs.match_path(home + rel).id, rid, rel)
        for rel in (r"AppData\Local\Microsoft\TokenBroker\Cache", r"AppData\Local\CapCut\User Data\CEF\Cache",
                    r"AppData\Local\Google\AndroidStudio2026.1.1\caches", r"AppData\Local\Microsoft\Olk\cache",
                    r"AppData\Roaming\LibreOffice\4\user\uno_packages\cache"):
            self.assertEqual(rs.match_path(home + rel, hidden=True).id, "not_a_cache", rel)
            self.assertIsNone(rs.match_path(home + rel), rel)             # and it does not fall through to "app cache"
        self.assertIsNone(rs.match_path(home + r"AppData\Local\Packages\Microsoft.WindowsStore_8wekyb3d8bbwe"))
        for rid in ("ai_context", "ai_app", "maven_repo", "deno_cache", "capcut_data"):
            self.assertFalse(rs.rules[rid].clean, rid)
        self.assertEqual(rs.guard_above(home + r"AppData\Roaming\Claude\Partitions\x\Cache", home).id, "ai_app")
        self.assertEqual(rs.guard_above(home + r"AppData\Local\Programs\Python\Python311\Lib\site-packages\pip\_vendor\cachecontrol\caches", home).id,
                         "site_packages")
        self.assertIsNone(rs.guard_above(home + r"AppData\Local\Google\Chrome\User Data\Default\Cache", home))

    def test_what_counts_as_not_a_cache(self):
        self.assertFalse(rules.looks_like_data(["index", "data_0", "data_1", "f_0001a2", "Cache_Data", "js", "wasm"]))
        for names in (["Local Storage", "Cache"], ["IndexedDB"], ["000003.log", "CURRENT", "LOCK"], ["ressdk.db"],
                      ["state.vscdb"], ["__init__.py", "file_cache.py"], ["helper.dll"], ["a.tbres"], ["package.json", "lib"]):
            self.assertTrue(rules.looks_like_data(names), names)

    def test_file_rules(self):
        rs = rules.RuleSet("win")
        self.assertEqual(rs.file_rule("hiberfil.sys")["id"], "hiberfil")
        self.assertEqual(rs.file_rule("ext4.vhdx")["id"], "vdisk")
        self.assertIsNone(rs.file_rule("notes.txt"))
        self.assertEqual(rules.ext_group("mp4"), "video")


class CleanerTests(unittest.TestCase):
    """The clean-up may only ever empty confirmed cache folders inside the profile it was given."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = os.path.realpath(self._tmp.name)
        self.home = os.path.join(self.root, "home", "u")
        self.outside = os.path.join(self.root, "outside")
        make(self.root, "outside/secret.txt", 5 * KB)
        make(self.root, "home/u/docs/keep.txt", 400 * KB)
        make(self.root, "home/u/.npm/_cacache/a.bin", 300 * KB)
        make(self.root, "home/u/.npm/_cacache/sub/b.bin", 200 * KB)
        make(self.root, "home/u/AppData/Local/App/Cache/x.bin", 2 * MB)
        make(self.root, "home/u/work/shop/package.json", 100)
        make(self.root, "home/u/work/shop/node_modules/lib/index.js", 600 * KB)
        self.rules = rules.RuleSet(home=self.home)
        self.cleaner = cleaner.Cleaner(self.rules, [self.home])

    def tearDown(self):
        self._tmp.cleanup()

    def scan(self):
        self.scanner = Scanner([self.root], ruleset=self.rules, threads=2, inherit_context=False).run()
        return self.scanner

    def node(self, *parts):
        n = self.scanner.find(os.path.join(self.home, *parts))
        self.assertIsNotNone(n, parts)
        return n

    def run_plan(self, *nodes):
        plan = self.cleaner.plan(self.scanner, [n.id for n in nodes])
        self.cleaner.start(plan["token"])
        for _ in range(400):
            if self.cleaner.status()["state"] != "running":
                break
            time.sleep(0.02)
        return plan, self.cleaner.status()

    def test_only_marked_caches_are_accepted(self):
        self.scan()
        ids = [self.node(".npm").id, self.node("AppData", "Local", "App", "Cache").id,
               self.node("work", "shop", "node_modules").id, self.node("docs").id, self.scanner.root_nodes[0].id]
        plan = self.cleaner.plan(self.scanner, ids + [10 ** 9, "x", None])
        self.assertEqual(sorted(os.path.basename(t["path"]) for t in plan["targets"]), [".npm", "Cache"])
        self.assertEqual({r["why"] for r in plan["rejected"]}, {"rule"})
        self.assertEqual(len(plan["rejected"]), 3)

    def test_empties_the_folder_and_nothing_else(self):
        self.scan()
        plan, st = self.run_plan(self.node(".npm"))
        self.assertEqual(st["state"], "done")
        self.assertEqual(st["files"], 2)
        self.assertEqual(st["freed"], 500 * KB)
        self.assertEqual(os.listdir(os.path.join(self.home, ".npm")), [])           # folder stays, content gone
        self.assertTrue(os.path.isfile(os.path.join(self.home, "docs", "keep.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "AppData", "Local", "App", "Cache", "x.bin")))
        self.assertTrue(os.path.isfile(os.path.join(self.home, "work", "shop", "node_modules", "lib", "index.js")))

    def test_every_clean_up_is_written_to_the_log(self):
        self.scan()
        log = os.path.join(self.root, "state", "depoloma", "cleanup-log.txt")
        self.cleaner.log_path = log
        npm = os.path.join(self.home, ".npm")
        cache = os.path.join(self.home, "AppData", "Local", "App", "Cache")
        plan = self.cleaner.plan(self.scanner, [self.node(".npm").id])
        self.cleaner.start(plan["token"], lang="tr")
        for _ in range(400):
            if self.cleaner.status()["state"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(self.cleaner.status()["log"], log)
        with open(log, encoding="utf-8") as fh:
            first = fh.read()
        self.assertIn("Temizlik başladı: 1 klasör", first)
        self.assertIn(npm, first)
        self.assertIn("[kural: npm_cache]", first)
        self.assertIn("Bitti", first)
        self.assertIn("500,0 KB boşaldı", first)
        self.assertNotIn(cache, first)
        # a second clean-up is appended, the first record stays
        self.scan()
        plan, st = self.run_plan(self.node("AppData", "Local", "App", "Cache"))
        with open(log, encoding="utf-8") as fh:
            both = fh.read()
        self.assertTrue(both.startswith(first))
        self.assertIn("Clean-up started: 1 folders", both)
        self.assertIn(cache, both)

    def test_a_log_that_cannot_be_written_does_not_stop_the_clean_up(self):
        self.scan()
        make(self.root, "blocker", 10)                          # a file where the log folder would have to be
        self.cleaner.log_path = os.path.join(self.root, "blocker", "cleanup-log.txt")
        plan, st = self.run_plan(self.node(".npm"))
        self.assertEqual(st["state"], "done")
        self.assertTrue(st.get("logError"))
        self.assertEqual(os.listdir(os.path.join(self.home, ".npm")), [])

    def test_a_confirmation_works_once_and_cannot_be_invented(self):
        self.scan()
        with self.assertRaises(ValueError):
            self.cleaner.start("made-up-token")
        plan, st = self.run_plan(self.node(".npm"))
        with self.assertRaises(ValueError):
            self.cleaner.start(plan["token"])
        self.assertTrue(os.path.isfile(os.path.join(self.home, "AppData", "Local", "App", "Cache", "x.bin")))

    def test_only_inside_the_given_profile(self):
        self.scan()
        other = cleaner.Cleaner(self.rules, [os.path.join(self.root, "home", "someone-else")])
        plan = other.plan(self.scanner, [self.node(".npm").id])
        self.assertEqual(plan["targets"], [])
        self.assertEqual(plan["rejected"][0]["why"], "outside")
        self.assertFalse(other.eligible(self.node(".npm"), os.path.join(self.home, ".npm")))

    def _link(self, target, link):
        if os.name == "nt":
            import _winapi
            _winapi.CreateJunction(target, link)
        else:
            os.symlink(target, link, target_is_directory=True)

    def test_links_inside_are_removed_not_followed(self):
        link = os.path.join(self.home, ".npm", "_cacache", "elsewhere")
        self._link(self.outside, link)
        self.scan()
        plan, st = self.run_plan(self.node(".npm"))
        self.assertEqual(st["state"], "done")
        self.assertFalse(os.path.lexists(link))                                      # the link is gone…
        self.assertTrue(os.path.isfile(os.path.join(self.outside, "secret.txt")))    # …what it pointed to is not
        self.assertEqual(os.listdir(os.path.join(self.home, ".npm")), [])

    def test_a_folder_swapped_for_a_link_is_refused_at_delete_time(self):
        self.scan()
        target = os.path.join(self.home, ".npm")
        plan = self.cleaner.plan(self.scanner, [self.node(".npm").id])
        os.rename(target, target + "-moved")
        self._link(self.outside, target)                                             # same path now points outside
        self.cleaner.start(plan["token"])
        for _ in range(400):
            if self.cleaner.status()["state"] != "running":
                break
            time.sleep(0.02)
        st = self.cleaner.status()
        self.assertEqual(st["targets"][0]["why"], "link")
        self.assertEqual(st["files"], 0)
        self.assertTrue(os.path.isfile(os.path.join(self.outside, "secret.txt")))

    def test_read_only_files_go_too(self):
        path = make(self.root, "home/u/.npm/_cacache/locked-down.bin", 10 * KB)
        os.chmod(path, 0o444)
        self.scan()
        plan, st = self.run_plan(self.node(".npm"))
        self.assertFalse(os.path.exists(path))
        self.assertEqual(st["skipped"], 0)

    @unittest.skipUnless(os.name == "nt", "files in use can only be locked on Windows")
    def test_files_in_use_are_skipped(self):
        self.scan()
        busy = os.path.join(self.home, ".npm", "_cacache", "a.bin")
        with open(busy, "rb"):
            plan, st = self.run_plan(self.node(".npm"))
        self.assertTrue(os.path.isfile(busy))
        self.assertEqual(st["skipped"], 1)
        self.assertEqual(st["files"], 1)
        self.assertEqual(st["state"], "done")

    def test_folders_worth_keeping_inside_a_cache_are_left_alone(self):
        game = make(self.root, "home/u/AppData/Local/App/Cache/steamapps/common/game/data.bin", 300 * KB)
        self.scan()
        plan, st = self.run_plan(self.node("AppData", "Local", "App", "Cache"))
        self.assertTrue(os.path.isfile(game))
        self.assertEqual(st["protected"], 1)
        self.assertFalse(os.path.exists(os.path.join(self.home, "AppData", "Local", "App", "Cache", "x.bin")))

    @unittest.skipUnless(os.name == "nt", "the temp-folder rule is Windows-only")
    def test_temp_keeps_anything_touched_recently(self):
        old = time.time() - 10 * 86400
        base = "home/u/AppData/Local/Temp/"
        make(self.root, base + "old-unit/a.bin", 300 * KB, age_days=10)
        make(self.root, base + "old-unit/deep/b.bin", 10 * KB, age_days=10)
        make(self.root, base + "mixed-unit/old.bin", 10 * KB, age_days=10)
        make(self.root, base + "mixed-unit/new.bin", 10 * KB)
        make(self.root, base + "new-unit/c.bin", 10 * KB)
        make(self.root, base + "old.tmp", 10 * KB, age_days=10)
        make(self.root, base + "new.tmp", 10 * KB)
        temp = os.path.join(self.home, "AppData", "Local", "Temp")
        for d in ("old-unit/deep", "old-unit"):
            os.utime(os.path.join(temp, *d.split("/")), (old, old))
        self.scan()
        plan, st = self.run_plan(self.node("AppData", "Local", "Temp"))
        self.assertEqual(plan["targets"][0]["keepDays"], 7)
        self.assertEqual(sorted(os.listdir(temp)), ["mixed-unit", "new-unit", "new.tmp"])
        self.assertEqual(sorted(os.listdir(os.path.join(temp, "mixed-unit"))), ["new.bin", "old.bin"])
        self.assertEqual(st["files"], 3)
        self.assertEqual(st["kept"], 3)

    def offered(self):
        """Every folder of the scan the UI would put a tick box on."""
        return {os.path.relpath(n.path(), self.home).replace("\\", "/")
                for n in self.scanner.nodes if self.cleaner.offerable(n, n.path())}

    def rule_of(self, *parts):
        node = self.scanner.find(os.path.join(self.home, *parts))
        return node.rule.id if node is not None and node.rule is not None else None

    def test_ai_tool_folders_are_never_offered(self):
        make(self.root, "home/u/.claude/projects/p/session.jsonl", 300 * KB)
        make(self.root, "home/u/AppData/Roaming/Claude/Cache/Cache_Data/f_0001", 400 * KB)
        make(self.root, "home/u/AppData/Roaming/Claude/claude-code-sessions/s.json", 300 * KB)
        make(self.root, "home/u/AppData/Local/Packages/OpenAI.Codex_2p2nq/LocalCache/Roaming/Codex/Cache/Cache_Data/f", 400 * KB)
        make(self.root, "home/u/AppData/Roaming/Code/User/workspaceStorage/abc/state.vscdb", 300 * KB)
        make(self.root, "home/u/AppData/Roaming/Code/Cache/Cache_Data/f_0001", 400 * KB)
        self.scan()
        self.assertEqual(self.rule_of(".claude"), "ai_context")
        self.assertEqual(self.rule_of("AppData", "Roaming", "Claude"), "ai_app")
        self.assertEqual(self.rule_of("AppData", "Local", "Packages", "OpenAI.Codex_2p2nq"), "ai_app")   # matched by prefix
        self.assertEqual(self.rule_of("AppData", "Roaming", "Code", "User", "workspaceStorage"), "ai_context")
        self.assertIsNone(self.rule_of("AppData", "Roaming", "Claude", "Cache"))          # not even labelled as a cache
        self.assertEqual(self.rule_of("AppData", "Roaming", "Code", "Cache"), "app_cache")
        self.assertEqual(self.offered(), {".npm", "AppData/Local/App/Cache", "AppData/Roaming/Code/Cache"})
        # and even if such a folder were asked for directly, the cleaner says no
        generic = self.rules.rules["app_cache"]
        self.assertEqual(self.cleaner.refusal(generic, os.path.join(self.home, "AppData", "Roaming", "Claude", "Cache")), "guarded")
        plan = self.cleaner.plan(self.scanner, [self.node("AppData", "Roaming", "Claude", "Cache").id, self.node(".claude").id])
        self.assertEqual(plan["targets"], [])

    def test_folders_named_cache_that_hold_data_or_code_are_refused(self):
        make(self.root, "home/u/AppData/Local/Editor/Cache/Local Storage/leveldb/000003.log", 300 * KB)   # a browser profile
        make(self.root, "home/u/AppData/Local/Editor/Cache/Cache_Data/f_0001", 300 * KB)
        make(self.root, "home/u/AppData/Local/Tool/Cache/v1/store.db", 400 * KB)                           # a database, one level down
        make(self.root, "home/u/AppData/Local/Lib/pkg/caches/__init__.py", 300 * KB)                       # program code
        make(self.root, "home/u/AppData/Local/Py/Lib/site-packages/thing/Cache/blob.bin", 400 * KB)       # inside installed code
        self.scan()
        self.assertIsNone(self.rule_of("AppData", "Local", "Editor", "Cache"))
        self.assertIsNone(self.rule_of("AppData", "Local", "Lib", "pkg", "caches"))
        self.assertIsNone(self.rule_of("AppData", "Local", "Py", "Lib", "site-packages", "thing", "Cache"))
        tool = self.node("AppData", "Local", "Tool", "Cache")
        self.assertEqual(tool.rule.id, "app_cache")                       # looks fine at first glance…
        self.assertFalse(self.cleaner.offerable(tool, tool.path()))      # …but the closer look refuses it
        plan = self.cleaner.plan(self.scanner, [tool.id])
        self.assertEqual((plan["targets"], plan["rejected"][0]["why"]), ([], "not-cache"))
        self.assertEqual(self.offered(), {".npm", "AppData/Local/App/Cache"})
        generic = self.rules.rules["app_cache"]
        for parts in (("Editor", "Cache"), ("Lib", "pkg", "caches")):
            path = os.path.join(self.home, "AppData", "Local", *parts)
            self.assertEqual(self.cleaner.refusal(generic, path), "not-cache", path)
        inside_code = os.path.join(self.home, "AppData", "Local", "Py", "Lib", "site-packages", "thing", "Cache")
        self.assertEqual(self.cleaner.refusal(generic, inside_code), "guarded")

    @unittest.skipUnless(os.name == "nt", "the temp-folder rule is Windows-only")
    def test_temp_cleaning_spares_ai_tool_scratchpads(self):
        old = time.time() - 30 * 86400
        base = "home/u/AppData/Local/Temp/"
        make(self.root, base + "claude/proj/session/scratchpad/notes.md", 300 * KB, age_days=30)
        make(self.root, base + "old-junk/a.bin", 300 * KB, age_days=30)
        temp = os.path.join(self.home, "AppData", "Local", "Temp")
        for d in ("claude/proj/session/scratchpad", "claude/proj/session", "claude/proj", "claude", "old-junk"):
            os.utime(os.path.join(temp, *d.split("/")), (old, old))
        self.scan()
        self.assertEqual(self.rule_of("AppData", "Local", "Temp", "claude"), "ai_context")
        plan, st = self.run_plan(self.node("AppData", "Local", "Temp"))
        self.assertEqual(sorted(os.listdir(temp)), ["claude"])                       # a month old, and still there
        self.assertTrue(os.path.isfile(os.path.join(temp, "claude", "proj", "session", "scratchpad", "notes.md")))
        self.assertEqual(st["protected"], 1)
        self.assertEqual(st["files"], 1)

    def test_rules_marked_cleanable_are_narrow(self):
        allowed_unanchored = {"steamapps/shadercache"}       # still only cleaned when inside the user's profile
        for plat in ("win", "mac", "linux"):
            for rule in rules.RuleSet(plat).rules.values():
                if not rule.clean:
                    continue
                self.assertEqual(rule.act, "safe", rule.id)
                self.assertIsNone(rule.has, rule.id)
                self.assertFalse(rule.inproj or rule.hidden or rule.child, rule.id)
                for pat in rule.pats:
                    self.assertTrue(pat.startswith("~/") or pat in allowed_unanchored,
                                    "%s: cleanable pattern %r must start at the user profile" % (rule.id, pat))
                    self.assertGreaterEqual(len(pat.split("/")), 2, pat)


class _Stat(object):
    def __init__(self, mode, size, mtime, dev, ino, nlink, blocks):
        self.st_mode, self.st_size, self.st_mtime = mode, size, mtime
        self.st_dev, self.st_ino, self.st_nlink, self.st_blocks = dev, ino, nlink, blocks


class _Entry(object):
    def __init__(self, name, path, st):
        self.name, self.path, self._st = name, path, st

    def stat(self, follow_symlinks=True):
        return self._st


class _Listing(list):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeLinux(object):
    """An in-memory Linux filesystem: just enough of `os` for the scanner (scandir + lstat),
    so the POSIX code paths and the Ubuntu rules can be tested on any machine."""

    name = "posix"
    sep = "/"
    path = posixpath

    def __init__(self):
        self.now = time.time()
        self.tree = {"/": {"t": "d", "dev": 1, "kids": {}}}
        self.denied = set()
        self._ino = 1000

    @staticmethod
    def cpu_count():
        return 2

    def mkdir(self, path, dev=None):
        node, cur = self.tree["/"], ""
        for part in [p for p in path.split("/") if p]:
            cur += "/" + part
            if cur not in self.tree:
                self.tree[cur] = node["kids"][part] = {"t": "d", "dev": node["dev"], "kids": {}}
            node = self.tree[cur]
        if dev is not None:
            node["dev"] = dev
        return node

    def file(self, path, size, age_days=0, blocks=None, ino=None, nlink=1):
        parent = self.mkdir(posixpath.dirname(path))
        self._ino += 1
        parent["kids"][posixpath.basename(path)] = {
            "t": "f", "size": size, "mtime": self.now - age_days * 86400, "dev": parent["dev"],
            "blocks": (size + 511) // 512 if blocks is None else blocks, "ino": ino or self._ino, "nlink": nlink}

    def symlink(self, path):
        self.mkdir(posixpath.dirname(path))["kids"][posixpath.basename(path)] = {"t": "l"}

    def _stat(self, n):
        if n["t"] == "d":
            return _Stat(0o040755, 4096, self.now, n["dev"], 0, 2, 8)          # a folder takes one 4 KB block
        if n["t"] == "l":
            return _Stat(0o120777, 10, self.now, 1, 0, 1, 0)
        return _Stat(0o100644, n["size"], n["mtime"], n["dev"], n["ino"], n["nlink"], n["blocks"])

    def stat(self, path):
        return self._stat(self.tree[path])

    def scandir(self, path):
        if path in self.denied:
            raise PermissionError(13, "Permission denied", path)
        if path not in self.tree:
            raise FileNotFoundError(2, "No such file or directory", path)
        return _Listing(_Entry(name, posixpath.join(path, name), self._stat(n))
                        for name, n in self.tree[path]["kids"].items())


class UbuntuSimulationTests(unittest.TestCase):
    """A typical Ubuntu disk, simulated: what is counted, what is skipped, how folders are labelled."""

    GB = 1 << 30

    @classmethod
    def setUpClass(cls):
        GB = cls.GB
        fs = cls.fs = FakeLinux()
        fs.file("/usr/lib/x86_64-linux-gnu/libbig.so", 3 * GB)
        fs.file("/usr/share/ollama/.ollama/models/blobs/sha256-abc", 5 * GB)
        fs.file("/var/cache/apt/archives/pkg.deb", 800 * MB)
        fs.file("/var/log/journal/system.journal", 2 * GB)
        fs.file("/var/lib/snapd/snaps/firefox_4000.snap", 250 * MB)
        fs.mkdir("/var/lib/docker")
        fs.denied.add("/var/lib/docker")                                   # root only
        fs.file("/swap.img", 4 * GB)
        fs.mkdir("/proc", dev=5)                                           # other filesystems: never crossed
        fs.file("/proc/kcore", 100 * GB)
        fs.mkdir("/mnt/c", dev=9)
        fs.file("/mnt/c/pagefile.sys", 10 * GB)
        fs.mkdir("/snap/firefox/4000", dev=7)
        fs.file("/snap/firefox/4000/usr/lib/firefox/libxul.so", GB)
        fs.file("/home/ada/Downloads/ubuntu-24.04.iso", 5 * GB, age_days=400)
        fs.file("/home/ada/.cache/pip/http/a/wheel.bin", 600 * MB)
        fs.file("/home/ada/.cache/mozilla/firefox/p/cache2/entries/e1", 900 * MB)
        fs.file("/home/ada/.cache/huggingface/hub/model.safetensors", 4 * GB)
        fs.file("/home/ada/.cache/sometool/blob.bin", 300 * MB)
        fs.file("/home/ada/snap/firefox/common/.cache/mozilla/firefox/x/cache2/e", 700 * MB)
        fs.file("/home/ada/snap/firefox/common/.mozilla/firefox/x/places.sqlite", 50 * MB)
        fs.file("/home/ada/.config/Code/Cache/Cache_Data/f1", 400 * MB)
        fs.file("/home/ada/.config/Code/User/settings.json", 2 * KB)
        fs.file("/home/ada/.config/libreoffice/4/user/uno_packages/cache/extension.oxt", 200 * MB)
        fs.file("/home/ada/.var/app/org.gimp.GIMP/cache/tiles.bin", 200 * MB)
        fs.file("/home/ada/.npm/_cacache/content-v2/x", GB)
        fs.file("/home/ada/.local/share/Trash/files/old.zip", 2 * GB)
        fs.file("/home/ada/projects/shop/package.json", 300, age_days=400)
        fs.file("/home/ada/projects/shop/src/index.js", 20 * MB, age_days=400)
        fs.file("/home/ada/projects/shop/node_modules/lib/index.js", 1500 * MB, age_days=390)
        fs.file("/home/ada/a/one.bin", GB, ino=77, nlink=2)                 # the same file under two names
        fs.file("/home/ada/b/two.bin", GB, ino=77, nlink=2)
        fs.file("/home/ada/vm/disk.img", 50 * GB, blocks=10 * GB // 512)    # sparse: 50 GB long, 10 GB on disk
        fs.symlink("/home/ada/link-to-usr")
        cls.rules = rules.RuleSet("linux", home="/home/ada")
        with mock.patch.multiple("depoloma.scanner", IS_WIN=False, SEP="/", os=fs), \
                mock.patch("depoloma.insights.os", fs):
            cls.sc = Scanner(["/"], ruleset=cls.rules, threads=3).run()
            cls.cleaner = cleaner.Cleaner(cls.rules, ["/home/ada"])
            volume = {"path": "/", "total": 500 * GB, "free": 100 * GB, "used": 380 * GB, "fs": "ext4"}
            cls.summary = insights.build_summary(cls.sc, [volume], can_clean=cls.cleaner.eligible)
            cls.paths = {}
            stack = list(cls.sc.root_nodes)
            while stack:
                n = stack.pop()
                cls.paths[n.path()] = n
                stack.extend(n.children or ())

    def rule(self, path):
        node = self.paths.get(path)
        self.assertIsNotNone(node, "not in the tree: " + path)
        return node.rule.id if node.rule is not None else None

    def test_scan_finished_and_other_filesystems_are_not_crossed(self):
        self.assertEqual(self.sc.state, "done")
        root = self.sc.root_nodes[0]
        self.assertLess(root.size, 50 * self.GB)                 # /proc (100 GB), /mnt/c and /snap mounts are not in it
        self.assertGreater(root.size, 40 * self.GB)
        for mount in ("/proc", "/mnt/c", "/snap/firefox/4000"):
            self.assertTrue(self.paths[mount].flags & scanner_mod.F_MOUNT, mount)
            self.assertEqual(self.paths[mount].size, 0)
        self.assertTrue(self.paths["/var/lib/docker"].flags & scanner_mod.F_DENIED)
        self.assertEqual(self.sc.ndenied, 1)

    def test_sizes_are_what_is_really_on_disk(self):
        GB = self.GB
        self.assertEqual(self.paths["/home/ada/vm"].size, 10 * GB + 4096)          # sparse file + the folder itself
        both = self.paths["/home/ada/a"].size + self.paths["/home/ada/b"].size
        self.assertEqual(both, GB + 2 * 4096)                                       # hard link counted once
        self.assertEqual(self.sc.root_nodes[0].linked, GB)
        self.assertNotIn("/home/ada/link-to-usr", self.paths)                       # a symlink is a file, not followed

    def test_ubuntu_folders_are_recognised(self):
        expected = {
            "/usr": "lin_system", "/var": "lin_var", "/var/cache/apt": "lin_apt_cache", "/var/log": "lin_logs",
            "/var/lib/snapd": "lin_snap", "/var/lib/docker": "docker_data", "/usr/share/ollama": "ai_models",
            "/home": "users", "/home/ada": "home", "/home/ada/Downloads": "downloads",
            "/home/ada/.cache": "shared_cache", "/home/ada/.cache/pip": "pip_cache",
            "/home/ada/.cache/mozilla": "app_cache", "/home/ada/.cache/huggingface": "ai_models",
            "/home/ada/.cache/sometool": "cache_entry",
            "/home/ada/snap": "snap_home", "/home/ada/snap/firefox/common/.cache": "app_cache",
            "/home/ada/snap/firefox/common/.mozilla": "browser_profile",
            "/home/ada/.config": "linux_config", "/home/ada/.config/Code": "vscode_data",
            "/home/ada/.config/Code/Cache": "app_cache",
            "/home/ada/.config/libreoffice/4/user/uno_packages/cache": "not_a_cache",
            "/home/ada/.var/app/org.gimp.GIMP/cache": "app_cache", "/home/ada/.npm": "npm_cache",
            "/home/ada/.local/share/Trash": "mac_trash",
            "/home/ada/projects/shop/node_modules": "node_modules",
        }
        for path, rid in expected.items():
            self.assertEqual(self.rule(path), rid, path)
        shop = self.paths["/home/ada/projects/shop"]
        self.assertTrue(shop.flags & F_PROJECT)
        self.assertEqual(shop.proj[1], self.paths["/home/ada/projects/shop/node_modules"].size)

    def test_findings_and_what_may_be_cleaned(self):
        s = self.summary
        self.assertEqual(sum(c["size"] for c in s["cats"]), self.sc.root_nodes[0].size)
        found = {f["id"]: f for f in s["findings"]}
        for rid in ("app_cache", "pip_cache", "npm_cache", "lin_apt_cache", "lin_logs", "ai_models", "cache_entry",
                    "mac_trash", "node_modules", "old_downloads", "stale_projects", "file:swapfile"):
            self.assertIn(rid, found)
        self.assertNotIn("shared_cache", found)                  # the container itself is not a finding
        offered = {it["path"] for f in s["findings"] for it in f["items"] if it.get("clean")}
        self.assertEqual(offered, {
            "/home/ada/.cache/pip", "/home/ada/.cache/mozilla", "/home/ada/snap/firefox/common/.cache",
            "/home/ada/.config/Code/Cache", "/home/ada/.var/app/org.gimp.GIMP/cache", "/home/ada/.npm"})
        for rid in ("lin_apt_cache", "lin_logs", "cache_entry", "mac_trash", "ai_models", "node_modules"):
            self.assertFalse(found[rid].get("clean"), rid)        # root-owned, unknown or not a cache
        system = [c for c in s["cats"] if c["key"] == "system"][0]["size"]
        self.assertGreater(system, 9 * self.GB)                  # /usr, /var data and the swap file
        self.assertGreater(s["hidden"], 300 * self.GB)           # used 380 GB, most of it not readable here

    def test_report_speaks_linux(self):
        texts = self.rules.texts()
        text = report.text_report(self.summary, texts, "tr", platform="linux")
        self.assertIn("Sistem", text)
        self.assertNotIn("Windows ve sistem", text)
        self.assertIn("/home/ada", text)


class SystemTests(unittest.TestCase):
    def test_linux_package_lists(self):
        dpkg = "firefox\t1:1snap1\t120\tii \nlinux-image-6.8\t6.8.0\t250000\tii \nold-pkg\t1.0\t5000\trc \nbroken\t1\tx\tii \n"
        pk = system.parse_dpkg(dpkg)
        self.assertEqual([p["name"] for p in pk], ["firefox", "linux-image-6.8", "broken"])   # "rc" = removed
        self.assertEqual(pk[1]["estimated"], 250000 * 1024)
        self.assertEqual(pk[2]["estimated"], 0)
        fp = system.parse_flatpak("GIMP\torg.gimp.GIMP\t2.10\t1.2 GB\nBad\t\t1\t3 MB\nX\torg.x\t1\t?\n")
        self.assertEqual([(p["name"], p["estimated"]) for p in fp], [("GIMP", 1200000000), ("X", 0)])
        with tempfile.TemporaryDirectory() as d:
            for name, size in (("firefox_1.snap", 3000), ("firefox_2.snap", 4000), ("core22_9.snap", 500), ("x.txt", 9)):
                with open(os.path.join(d, name), "wb") as fh:
                    fh.write(b"x" * size)
            snaps = {p["name"]: p for p in system.snap_packages(d)}
        self.assertEqual(snaps["firefox"]["estimated"], 7000)             # both kept revisions count
        self.assertEqual(snaps["firefox"]["version"], "×2")
        self.assertEqual(set(snaps), {"firefox", "core22"})

    def test_which_program_a_cache_belongs_to(self):
        home = os.path.join("C:\\", "Users", "Ada") if os.name == "nt" else "/home/ada"

        def j(*parts):
            return os.path.join(home, *parts)
        self.assertEqual(system.app_of(j("AppData", "Roaming", "Claude", "Cache"), home),
                         ("Claude", j("AppData", "Roaming", "Claude")))
        self.assertEqual(system.app_of(j("AppData", "Local", "Google", "Chrome", "User Data", "Default", "Cache"), home),
                         ("Chrome", j("AppData", "Local", "Google", "Chrome")))
        self.assertEqual(system.app_of(j("AppData", "Local", "Packages", "MSTeams_8wekyb3d8bbwe", "LocalCache", "Cache"), home),
                         ("MSTeams", j("AppData", "Local", "Packages", "MSTeams_8wekyb3d8bbwe")))
        self.assertEqual(system.app_of(j(".config", "Code", "Cache"), home), ("Code", j(".config", "Code")))
        self.assertEqual(system.app_of(j(".cache", "pip"), home), ("pip", j(".cache", "pip")))
        self.assertEqual(system.app_of(j(".gradle", "caches"), home), (".gradle", j(".gradle")))
        self.assertIsNone(system.app_of(os.path.join(os.path.dirname(home), "Bob", ".npm"), home))
        self.assertIsNone(system.app_of(home, home))

    def test_linux_mounts(self):
        text = ("/dev/nvme0n1p2 / ext4 rw 0 0\nproc /proc proc rw 0 0\n/dev/loop3 /snap/core22/1 squashfs ro 0 0\n"
                "/dev/nvme0n1p1 /boot/efi vfat rw 0 0\n/dev/sda1 /home ext4 rw 0 0\n"
                "/dev/sdb1 /media/ada/USB\\040DISK exfat rw 0 0\ntmpfs /run tmpfs rw 0 0\n"
                "/dev/sdc1 /run/media/ada/key vfat rw 0 0\nC:\\\\ /mnt/c 9p rw 0 0\n")
        self.assertEqual(system.linux_mounts(text), [("/", "ext4"), ("/home", "ext4"), ("/media/ada/USB DISK", "exfat"),
                                                     ("/run/media/ada/key", "vfat")])
        self.assertEqual(system.linux_mounts(""), [("/", "")])

    def test_du_tree(self):
        text = "2048\t/\n1500\t/home\n1400\t/home/u\n100\t/home/u/tiny\n500\t/usr\n"
        tree = system.du_tree(text, min_bytes=200 * KB)
        self.assertEqual(tree["size"], 2048 * KB)
        self.assertEqual([c["path"] for c in tree["children"]], ["/home", "/usr"])
        self.assertEqual([c["path"] for c in tree["children"][0]["children"]], ["/home/u"])
        self.assertEqual(tree["children"][0]["children"][0]["children"], [])

    def test_volumes(self):
        vols = system.volumes()
        self.assertTrue(vols)
        for v in vols:
            self.assertGreater(v["total"], 0)
            self.assertTrue(os.path.isdir(v["path"]))


if __name__ == "__main__":
    unittest.main()
