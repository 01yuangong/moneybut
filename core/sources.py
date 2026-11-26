"""原生抓取层：只用标准库 urllib + xml，不需要 pip install 任何东西。

全部走各平台**公开**接口 / 公开 RSS，遵守 robots 与限速，不登录、不破解、
不抓取需要授权的内容。offline 模式从 data/fixtures 读取固定样本，
样本里的 time_ago_h 会被换算成「距现在多少小时」，保证任何时候跑测试
都能得到稳定的时间衰减结果。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = ("Mozilla/5.0 (compatible; SideHustleRadar/1.0; +https://example.com/bot) "
      "python-urllib")
FIXTURE_DIR = Path(__file__).resolve().parent.parent / "data" / "fixtures"
TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")


def clean(text: str | None, limit: int = 400) -> str:
    if not text:
        return ""
    t = urllib.parse.unquote(str(text))
    t = TAG_RE.sub(" ", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    t = WS_RE.sub(" ", t).strip()
    return t[:limit]


def http_get(url: str, timeout: float = 12.0, retries: int = 2) -> bytes:
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA, "Accept": "*/*", "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return raw
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
            last = e
            time.sleep(1.2 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {last}")


def _fixture(name: str):
    p = FIXTURE_DIR / name
    if not p.exists():
        raise FileNotFoundError(f"offline fixture missing: {p}")
    raw = p.read_bytes()
    return json.loads(raw) if p.suffix == ".json" else raw


def _ago(raw: dict, key: str = "published") -> int:
    """fixture 里的 time_ago_h → 绝对时间戳；没有就用原字段。"""
    h = raw.get("time_ago_h")
    if h is not None:
        return int(time.time() - float(h) * 3600)
    return int(raw.get(key) or time.time())


def canonical_url(url: str) -> str:
    if not url:
        return ""
    u = urllib.parse.urlsplit(url.strip())
    q = urllib.parse.parse_qsl(u.query)
    keep = [(k, v) for k, v in q
            if not k.lower().startswith(("utm_", "ref", "fbclid", "spm"))]
    return urllib.parse.urlunsplit(
        (u.scheme or "https", u.netloc.lower(), u.path.rstrip("/"),
         urllib.parse.urlencode(keep), ""))


def uid_for(source: str, url: str, title: str) -> str:
    base = canonical_url(url) or f"{source}:{title.strip().lower()}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


# ---------------- 各源实现 ----------------

def fetch_hackernews(cfg: dict, offline: bool) -> list[dict]:
    if offline:
        data = _fixture("hn.json")
    else:
        ids = json.loads(http_get(
            "https://hacker-news.firebaseio.com/v0/topstories.json"))[: cfg["limit"]]
        data = []
        for i in ids:
            try:
                data.append(json.loads(http_get(
                    f"https://hacker-news.firebaseio.com/v0/item/{i}.json", timeout=8)))
            except RuntimeError:
                continue
            time.sleep(0.05)
    out = []
    for it in data[: cfg["limit"]]:
        if not it or it.get("type") not in (None, "story"):
            continue
        url = it.get("url") or f"https://news.ycombinator.com/item?id={it.get('id')}"
        out.append({
            "source": cfg["id"],
            "title": clean(it.get("title"), 200),
            "url": url,
            "summary": clean(it.get("text"), 300),
            "engagement": float(it.get("score") or 0) + float(it.get("descendants") or 0) * 0.5,
            "published": _ago(it, "time"),
        })
    return out


def fetch_reddit(cfg: dict, offline: bool) -> list[dict]:
    if offline:
        data = _fixture(f"reddit_{cfg['sub']}.json")
    else:
        url = (f"https://www.reddit.com/r/{cfg['sub']}/top.json"
               f"?t=day&limit={cfg['limit']}&raw_json=1")
        data = json.loads(http_get(url))
    out = []
    for child in data.get("data", {}).get("children", [])[: cfg["limit"]]:
        d = child.get("data", {})
        if d.get("stickied") or d.get("over_18"):
            continue
        link = d.get("url_overridden_by_dest") or (
            "https://www.reddit.com" + d.get("permalink", ""))
        out.append({
            "source": cfg["id"],
            "title": clean(d.get("title"), 200),
            "url": link,
            "summary": clean(d.get("selftext"), 300),
            "engagement": float(d.get("score") or 0) + float(d.get("num_comments") or 0) * 0.6,
            "published": _ago(d, "created_utc"),
        })
    return out


def fetch_github(cfg: dict, offline: bool) -> list[dict]:
    if offline:
        data = _fixture("github.json")
    else:
        since = time.strftime("%Y-%m-%d", time.gmtime(
            time.time() - cfg.get("since_days", 7) * 86400))
        q = urllib.parse.quote(f"created:>{since} stars:>20")
        data = json.loads(http_get(
            f"https://api.github.com/search/repositories?q={q}"
            f"&sort=stars&order=desc&per_page={cfg['limit']}", timeout=15))
    out = []
    for r in data.get("items", [])[: cfg["limit"]]:
        if r.get("archived"):
            continue
        desc = clean(r.get("description"), 200)
        out.append({
            "source": cfg["id"],
            "title": f'{clean(r.get("full_name"), 80)} — {desc[:60]}',
            "url": r.get("html_url") or "",
            "summary": desc,
            "engagement": float(r.get("stargazers_count") or 0) * 1.2
                          + float(r.get("forks_count") or 0) * 1.5,
            "published": _ago(r, "created_at_ts"),
        })
    return out


def fetch_rss(cfg: dict, offline: bool) -> list[dict]:
    raw = _fixture(f"rss_{cfg['id']}.xml") if offline else http_get(cfg["url"], timeout=15)
    root = ET.fromstring(raw)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    out = []
    entries = root.findall(".//item") or root.findall(".//atom:entry", ns)
    for e in entries[: cfg["limit"]]:
        title = clean(e.findtext("title") or
                      e.findtext("atom:title", default="", namespaces=ns), 200)
        link = e.findtext("link") or ""
        if not link:
            le = e.find("atom:link", ns)
            link = (le.get("href") if le is not None else "") or ""
        desc = (e.findtext("description")
                or e.findtext("atom:summary", default="", namespaces=ns) or "")
        date = (e.findtext("pubDate")
                or e.findtext("atom:updated", default="", namespaces=ns) or "")
        ts = time.time()
        for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
                    "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                ts = time.mktime(time.strptime(date.strip(), fmt))
                break
            except (ValueError, TypeError):
                continue
        out.append({
            "source": cfg["id"],
            "title": title,
            "url": link,
            "summary": clean(desc, 300),
            "engagement": 8.0,
            "published": int(ts),
        })
    return out


FETCHERS = {"hackernews": fetch_hackernews, "reddit": fetch_reddit,
            "github": fetch_github, "rss": fetch_rss}


def collect(cfg: dict, offline: bool = False) -> tuple[list[dict], list[str]]:
    """抓所有启用的源，返回 (原始条目, 错误列表)。单源失败不影响整体。"""
    raw: list[dict] = []
    errors: list[str] = []
    for src in cfg["sources"]:
        if not src.get("enabled", True):
            continue
        fn = FETCHERS.get(src["type"])
        if not fn:
            errors.append(f"unknown source type: {src['type']}")
            continue
        try:
            got = fn(src, offline)
            for g in got:
                g["weight"] = src.get("weight", 1.0)
                g["half_life_h"] = src.get("half_life_h", 24)
                g["source_label"] = src.get("label", src["id"])
            raw.extend(got)
        except Exception as e:  # noqa: BLE001 - 单源失败必须被吞掉
            errors.append(f"{src['id']}: {type(e).__name__}: {e}")
    return raw, errors
