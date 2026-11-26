"""端到端 + 单元测试。跑法：python3 -m unittest discover -s tests -v"""
import html
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import publish as pub
from core import render
from core.config import load_config
from core.score import build_candidates, extractive_summary, score_item, tokens, jaccard
from core.sources import collect, fetch_rss
from core.store import Store, Item

import serve  # noqa: E402  (需要在 sys.path 设置之后导入)

CFG = load_config(ROOT / "config.json")


def raw(source="hn", title="t", url="https://x.com/a", eng=100, ago=1.0, **kw):
    return {"source": source, "source_label": source, "title": title, "url": url,
            "summary": kw.pop("summary", ""), "engagement": eng,
            "published": int(time.time() - ago * 3600),
            "weight": kw.pop("weight", 1.0), "half_life_h": kw.pop("half_life_h", 24)}


class TestScoring(unittest.TestCase):
    def test_time_decay(self):
        now = int(time.time())
        fresh = dict(raw(eng=500, ago=1)); fresh["published"] = now - 3600
        old = dict(fresh); old["published"] = now - 72 * 3600
        self.assertGreater(score_item(fresh, CFG, now), score_item(old, CFG, now))

    def test_engagement_ordering(self):
        now = int(time.time())
        hi = score_item(raw(eng=900, ago=2), CFG, now)
        lo = score_item(raw(eng=5, ago=2), CFG, now)
        self.assertGreater(hi, lo)

    def test_block_keyword(self):
        self.assertEqual(score_item(raw(title="We are hiring engineers"), CFG), 0.0)

    def test_boost_keyword(self):
        now = int(time.time())
        plain = score_item(raw(title="some random post", ago=2), CFG, now)
        boosted = score_item(raw(title="自动化 side project 月入 $2k", ago=2), CFG, now)
        self.assertGreater(boosted, plain)

    def test_summary_truncated(self):
        s = extractive_summary("句子一。" * 60, 60)
        self.assertLessEqual(len(s), 62)
        self.assertTrue(s.endswith("…"))


class TestDedupe(unittest.TestCase):
    def test_same_url_different_utm(self):
        items = [raw(url="https://a.com/p?utm_source=x", title="Same story here"),
                 raw(url="https://a.com/p", title="Same story here")]
        out = build_candidates(items, CFG, [])
        self.assertEqual(len(out), 1)

    def test_near_duplicate_title(self):
        items = [raw(url="https://b.com/1", title="I built a $4k/mo side project with a Chrome extension"),
                 raw(url="https://c.com/2", title="I built a $4k/mo side project with a Chrome extension!")]
        self.assertEqual(len(build_candidates(items, CFG, [])), 1)

    def test_known_title_suppressed_via_store(self):
        cands = build_candidates([raw(url="https://d.com/1", title="Known story")], CFG, ["Known story"])
        self.assertEqual(len(cands), 0)

    def test_jaccard(self):
        self.assertEqual(jaccard(tokens("hello python world"), tokens("hello python world")), 1.0)
        self.assertEqual(jaccard(set(), tokens("hello")), 0.0)


class TestRenderSafety(unittest.TestCase):
    """外部 feed 是不可信输入，标题/URL 里的标签必须被转义。"""

    def test_xss_escaped(self):
        bad = {"uid": "x", "source": "s", "source_label": "<img src=x onerror=alert(1)>",
               "title": '<script>alert("xss")</script> 赚钱', "url": 'https://a.com/" onmouseover="alert(1)',
               "summary": "<b>hi</b>", "engagement": 1, "published": 1700000000, "score": 1.0}
        h = render.item_card(bad)
        self.assertNotIn("<script>", h)
        self.assertNotIn("<img", h)
        self.assertIn("&lt;script&gt;", h)

    def test_locked_card_has_no_link(self):
        it = {"uid": "x", "source": "s", "source_label": "s", "title": "付费标题",
              "url": "https://secret.example/paid", "summary": "秘密", "engagement": 1,
              "published": 1700000000, "score": 1.0}
        h = render.item_card(it, locked=True)
        self.assertNotIn("https://secret.example/paid", h)
        self.assertNotIn("秘密", h)
        self.assertIn("付费标题", h)


class TestRSS(unittest.TestCase):
    def test_atom_entry_parsed(self):
        xml = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
        <entry><title>Atom item</title><link href="https://atom.example/1"/>
        <summary>hello</summary><updated>2024-05-01T10:00:00Z</updated></entry></feed>"""
        import core.sources as src
        orig = src._fixture
        src._fixture = lambda name: xml
        try:
            got = fetch_rss({"id": "t", "url": "http://x", "limit": 5}, offline=True)
        finally:
            src._fixture = orig
        self.assertEqual(got[0]["title"], "Atom item")
        self.assertEqual(got[0]["url"], "https://atom.example/1")

    def test_bad_xml_raises(self):
        import core.sources as src
        orig = src._fixture
        src._fixture = lambda name: b"not xml"
        try:
            with self.assertRaises(Exception):
                fetch_rss({"id": "t", "url": "http://x", "limit": 5}, offline=True)
        finally:
            src._fixture = orig


class TestPipeline(unittest.TestCase):
    """完整链路：抓 → 筛 → 发，验证付费墙不泄露。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls.tmp, "t.db")
        cls.out = Path(cls.tmp) / "site"
        cls.cfg = json.loads(json.dumps(CFG))
        cls.cfg["publish"]["out_dir"] = str(cls.out)
        cls.store = Store(cls.db)

        raw_items, errs = collect(cls.cfg, offline=True)
        assert not errs, errs
        cands = build_candidates(raw_items, cls.cfg, [])
        picks = cands[: cls.cfg["render"]["free_items"] + cls.cfg["render"]["paid_items"]]
        now = int(time.time())
        for it in picks:
            cls.store.upsert_item(Item(uid=it["uid"], source=it["source"], title=it["title"],
                                       url=it["url"], summary=it["summary"],
                                       engagement=it["engagement"], published=it["published"],
                                       score=it["score"], first_seen=now))
        cls.store.commit()
        cls.free = picks[: cls.cfg["render"]["free_items"]]
        cls.paid = picks[cls.cfg["render"]["free_items"]:]
        cls.store.save_issue(1, "2024-01-01", "t", [i["uid"] for i in cls.free],
                             [i["uid"] for i in cls.paid])
        cls.info = pub.publish(cls.cfg, cls.store, cls.out, 1, "2024-01-01", "t",
                               cls.free, cls.paid)

    def read(self, rel):
        return (self.out / rel).read_text(encoding="utf-8")

    def test_files_exist(self):
        for rel in ["index.html", "issues/issue-0001.html", "archive.html", "about.html",
                    "feed.xml", "api/latest.json", "robots.txt", "sitemap.xml",
                    "go/a0.html", "digest/issue-0001.md"]:
            self.assertTrue((self.out / rel).exists(), rel)
        self.assertTrue(Path(self.info["paid_file"]).exists())

    def test_paywall_no_leak(self):
        idx = self.read("index.html")
        for it in self.paid:
            self.assertNotIn(it["url"], idx)
            self.assertNotIn(it["summary"][:20] or "___", idx)
        self.assertIn("paywall", idx)

    def test_feed_and_api_free_only(self):
        feed = self.read("feed.xml")
        api = json.loads(self.read("api/latest.json"))
        for it in self.paid:
            self.assertNotIn(it["url"], feed)
        self.assertEqual(api["paid_count"], len(self.paid))
        self.assertEqual(len(api["free"]), len(self.free))

    def test_paid_page_has_all(self):
        paid_html = html.unescape(Path(self.info["paid_file"]).read_text(encoding="utf-8"))
        for it in self.free + self.paid:
            self.assertIn(it["title"][:30], paid_html)

    def test_robots_disallow_paid(self):
        self.assertIn("Disallow: /paid/", self.read("robots.txt"))

    def test_markdown_digest(self):
        md = self.read("digest/issue-0001.md")
        self.assertIn("付费版", md)
        self.assertIn(self.free[0]["title"][:20], md)

    def test_sitemap_valid_xml(self):
        import xml.etree.ElementTree as ET
        ET.fromstring(self.read("sitemap.xml"))
        ET.fromstring(self.read("feed.xml"))

    def test_idempotent_rebuild(self):
        before = len(list(self.out.rglob("*.html")))
        pub.publish(self.cfg, self.store, self.out, 1, "2024-01-01", "t", self.free, self.paid)
        self.assertEqual(before, len(list(self.out.rglob("*.html"))))


class TestServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        os.environ["MONEYBOT_DB"] = os.path.join(cls.tmp, "srv.db")
        serve.CFG = json.loads(json.dumps(CFG))
        serve.CFG["site"]["base_url"] = "http://127.0.0.1:0"
        serve.ROOT = Path(cls.tmp) / "site"
        serve.ROOT.mkdir(parents=True)
        (serve.ROOT / "index.html").write_text("<h1>ok</h1>", encoding="utf-8")
        serve.STORE = Store(os.environ["MONEYBOT_DB"])
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), serve.Handler)
        cls.port = cls.srv.server_address[1]
        cls.th = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.th.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def url(self, p):
        return f"http://127.0.0.1:{self.port}{p}"

    def test_static(self):
        with urllib.request.urlopen(self.url("/")) as r:
            self.assertEqual(r.status, 200)
            self.assertIn(b"ok", r.read())

    def test_traversal_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.url("/../config.json"))
        self.assertIn(cm.exception.code, (403, 404))

    def test_subscribe(self):
        req = urllib.request.Request(self.url("/api/subscribe"),
                                     data=json.dumps({"contact": "boss@example.com"}).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as r:
            body = json.loads(r.read())
        self.assertTrue(body["ok"])
        self.assertTrue(body["token"])

    def test_subscribe_rejects_junk(self):
        req = urllib.request.Request(self.url("/api/subscribe"),
                                     data=json.dumps({"contact": ""}).encode())
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(req)
        self.assertEqual(cm.exception.code, 400)

    def test_go_redirect_and_click_logged(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            op.open(self.url("/go/a0"))
        self.assertEqual(cm.exception.code, 302)
        self.assertEqual(cm.exception.headers["Location"],
                         serve.CFG["monetize"]["affiliates"][0]["url"])
        n = serve.STORE.conn.execute("SELECT COUNT(*) c FROM clicks").fetchone()["c"]
        self.assertGreaterEqual(n, 1)

    def test_stats_requires_admin(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.url("/api/stats"))
        self.assertEqual(cm.exception.code, 401)

    def test_paid_token_flow(self):
        token = serve.STORE.add_subscriber("vip@example.com", tier="paid")
        serve.STORE.save_issue(1, "2024-01-01", "t", "u1", "u2")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(NoRedirect)
        with self.assertRaises(urllib.error.HTTPError) as cm:
            op.open(self.url(f"/p/{token}"))
        self.assertEqual(cm.exception.code, 302)
        self.assertIn("/paid/", cm.exception.headers["Location"])

    def test_bad_token_403(self):
        with self.assertRaises(urllib.error.HTTPError) as cm:
            urllib.request.urlopen(self.url("/p/deadbeef"))
        self.assertEqual(cm.exception.code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
