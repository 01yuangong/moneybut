"""渲染层（精简版）。全部函数体都是平铺语句，不含 for/if 缩进块，粘贴不易坏。"""
from __future__ import annotations

import html
import json
import time

CSS = """
:root{--bg:#0e1116;--card:#161b22;--line:#252c36;--fg:#e6edf3;--mut:#8b949e;--acc:#3fb950;--brand:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.7 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:24px 18px 80px}
header.top{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:26px}
.logo{font-size:22px;font-weight:800}.tag{color:var(--mut);font-size:14px;margin-top:6px}
.issue{color:var(--mut);font-size:13px;margin-top:10px}
h1{font-size:24px;margin:26px 0 6px}h2{font-size:17px;margin:34px 0 12px;color:var(--brand)}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin:12px 0}
.item h3{margin:0 0 8px;font-size:16.5px;line-height:1.5}
.meta{color:var(--mut);font-size:12.5px;display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.badge{background:#1f2630;border:1px solid var(--line);border-radius:999px;padding:1px 9px}
.sum{color:#c9d1d9;font-size:14.5px;margin:0;line-height:1.75}
.orig{display:inline-block;margin-top:9px;font-size:12px;color:var(--mut);text-decoration:none;border-bottom:1px dotted #3d444d}
.paywall{border:1px dashed #3d444d;border-radius:14px;padding:26px 20px;margin:26px 0;text-align:center}
.paywall p{color:var(--mut);font-size:14px;margin:6px 0 16px}
.btn{display:inline-block;background:var(--acc);color:#04170a;font-weight:800;padding:12px 26px;border-radius:999px;text-decoration:none}
.ghostline{color:var(--mut);font-size:12.5px;margin-top:12px}
.locked{filter:blur(5px);user-select:none;pointer-events:none;opacity:.55}
footer{border-top:1px solid var(--line);margin-top:44px;padding-top:18px;color:var(--mut);font-size:12.5px}
footer a,.nav a{color:var(--brand);text-decoration:none}
.nav{display:flex;gap:14px;font-size:13.5px;margin-top:12px}
ul.arch{list-style:none;padding:0}ul.arch li{border-bottom:1px solid var(--line);padding:12px 0;font-size:15px}
ul.arch a{color:var(--fg);text-decoration:none}ul.arch .d{color:var(--mut);font-size:12.5px}
"""


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def fmt_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _head(cfg: dict, title: str, desc: str, canonical: str) -> str:
    lang = cfg["site"].get("lang", "zh-CN")
    block = (f'<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8">'
             '<meta name="viewport" content="width=device-width,initial-scale=1">'
             f'<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">'
             f'<link rel="canonical" href="{esc(canonical)}">'
             f'<meta property="og:title" content="{esc(title)}">'
             f'<meta property="og:description" content="{esc(desc)}">'
             '<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">'
             f'<style>{CSS}</style></head><body><div class="wrap">')
    return block


def _header(cfg: dict, issue_no: int | None = None, day: str = "") -> str:
    site = cfg["site"]
    nav = ('<div class="nav"><a href="/">最新一期</a><a href="/archive.html">往期</a>'
           '<a href="/feed.xml">RSS</a><a href="/about.html">关于/合作</a></div>')
    iss = f'<div class="issue">第 {issue_no:04d} 期 · {esc(day)}</div>' if issue_no else ""
    return (f'<header class="top"><div class="logo">{esc(site["name"])}</div>'
            f'<div class="tag">{esc(site.get("tagline",""))}</div>{iss}{nav}</header>')


def _footer(cfg: dict) -> str:
    m = cfg["monetize"]
    return (f'<footer>内容均来自公开 RSS，只做摘要与链接跳转，版权归原作者。<br>'
            f'联系：{esc(m.get("contact",""))} · '
            f'<a href="{esc(m.get("buy_url","#"))}" rel="noopener">看完整版</a>'
            f'</footer></div></body></html>')


def item_card(it: dict, locked: bool = False) -> str:
    badge = f'<span class="badge">🔥 {int(it["engagement"])}</span>' if it.get("engagement") else ""
    meta = (f'<div class="meta"><span class="badge">{esc(it.get("source_label",""))}</span>'
            f'{badge}<span>{fmt_time(it["published"])}</span></div>')
    if locked:
        return (f'<div class="item locked"><h3>{esc(it["title"])}</h3>{meta}'
                f'<p class="sum">［完整版可见 · 含直达链接与变现路径拆解］</p></div>')
    body = it.get("comment") or it.get("summary") or "（这条暂无解读）"
    orig = (f'<a class="orig" href="{esc(it["url"])}" target="_blank" '
            'rel="nofollow noopener">查看原文 ↗</a>')
    return (f'<div class="item"><h3>{esc(it["title"])}</h3>{meta}'
            f'<p class="sum">{esc(body)}</p>{orig}</div>')


def paywall_block(cfg: dict, hidden: int) -> str:
    m = cfg["monetize"]
    return (f'<div class="paywall"><h3>🔒 本期还有 {hidden} 条（完整版）</h3>'
            '<p>每天筛出 8 条「国内能直接抄的搞钱动作」，每条写清钱从谁来、'
            '在哪个平台做、第一步做什么。</p>'
            f'<a class="btn" href="{esc(m.get("buy_url","#"))}" target="_blank" '
            f'rel="noopener sponsored">￥{m.get("price_cny", 39)} / 月 · 解锁全部</a>'
            f'<div class="ghostline">已订阅？加 {esc(m.get("contact",""))} 领专属链接</div></div>')

def render_issue(cfg: dict, issue: dict, items_free: list[dict],
                 items_paid: list[dict], canonical: str = "") -> str:
    site = cfg["site"]
    day = issue["day"]
    title = f'{site["name"]} 第{issue["issue_no"]:04d}期 · {day}'
    desc = f'{day} 精选 {len(items_free) + len(items_paid)} 条国内副业/小生意/自动化搞钱情报'
    cards = "".join(item_card(it) for it in items_free)
    locked = item_card(items_paid[0], locked=True) if items_paid else ""
    pay = paywall_block(cfg, len(items_paid)) if items_paid else ""
    body = [_head(cfg, title, desc, canonical or site["base_url"]),
            _header(cfg, issue["issue_no"], day),
            f'<h1>{esc(day)} · 今日情报</h1>',
            f'<p class="tag">共 {len(items_free) + len(items_paid)} 条，免费 {len(items_free)} 条。</p>',
            cards]
    if items_paid:
        body += ['<h2>完整版 · 剩下的硬货</h2>', locked, pay]
    body.append(_footer(cfg))
    return "".join(body)


def render_paid(cfg: dict, issue: dict, items: list[dict]) -> str:
    site = cfg["site"]
    cards = "".join(item_card(it) for it in items)
    return "".join([_head(cfg, f'{site["name"]} 完整版 第{issue["issue_no"]:04d}期',
                          "完整版内容", f'{site["base_url"]}/paid/'),
                    _header(cfg, issue["issue_no"], issue["day"]),
                    '<h1>完整版 · 全部条目</h1>',
                    f'<p class="tag">共 {len(items)} 条。请勿外传。</p>',
                    cards, _footer(cfg)])


def render_archive(cfg: dict, issues: list[dict]) -> str:
    site = cfg["site"]
    lis = "".join(f'<li><a href="/issues/issue-{i["issue_no"]:04d}.html">'
                  f'第 {i["issue_no"]:04d} 期 · {esc(i["title"])}</a>'
                  f'<div class="d">{esc(i["day"])}</div></li>' for i in issues)
    return "".join([_head(cfg, f'往期存档 · {site["name"]}', "全部往期",
                          f'{site["base_url"]}/archive.html'),
                    _header(cfg), f'<h1>往期存档</h1><ul class="arch">{lis}</ul>',
                    _footer(cfg)])


def render_about(cfg: dict) -> str:
    site, m = cfg["site"], cfg["monetize"]
    sources = "、".join(s.get("label", "") for s in cfg.get("sources", []) if s.get("enabled", True))
    text = (f'<p>{esc(site["name"])} 每天自动汇总 {esc(sources)} 等公开源里'
            '与「副业 / 小生意 / 自动化」相关的内容，做中文摘要并按可执行性排序。'
            '全部内容只做摘要和原文跳转，不转载全文，尊重原作者版权。</p>')
    plan = (f'<h2>订阅</h2><p>免费版每天 {cfg["render"]["free_items"]} 条；'
            f'完整版全部条目 + 每周「可抄清单」。价格 ￥{m.get("price_cny", 39)}/月。</p>'
            f'<p><a class="btn" href="{esc(m.get("buy_url","#"))}">看完整版</a></p>')
    contact = (f'<h2>合作</h2><p>联系：{esc(m.get("contact",""))}。'
               '广告位会明确标注「广告」，不接博彩、借贷、灰产。</p>')
    return "".join([_head(cfg, f'关于 · {site["name"]}', "关于本简报",
                          f'{site["base_url"]}/about.html'),
                    _header(cfg), '<h1>关于</h1>', text, plan, contact, _footer(cfg)])


def render_go(cfg: dict, affs: list[dict]) -> dict[str, str]:
    page = ('<!doctype html><html><head><meta charset="utf-8"><title>跳转中…</title>'
            '<meta name="robots" content="noindex">'
            '<meta http-equiv="refresh" content="0;url={url}"></head>'
            '<body style="background:#0e1116;color:#8b949e;padding:40px">'
            '正在跳转… 若未自动跳转请点 <a style="color:#58a6ff" href="{url}">这里</a>。'
            '</body></html>')
    return {f"a{i}.html": page.replace("{url}", esc(a.get("url", "#")))
            for i, a in enumerate(affs)}


def feed_xml(cfg: dict, issues: list[dict], items_by_issue: dict[int, list[dict]] | None = None) -> str:
    site = cfg["site"]
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    items = "".join(f'<item><title>{esc(i["title"])}</title>'
                    f'<link>{site["base_url"]}/issues/issue-{i["issue_no"]:04d}.html</link>'
                    f'<pubDate>{time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(i["created_at"]))}</pubDate>'
                    '</item>' for i in issues[:20])
    return (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>'
            f'<title>{esc(site["name"])}</title><link>{esc(site["base_url"])}</link>'
            f'<description>{esc(site.get("tagline",""))}</description>'
            f'<language>zh-cn</language><lastBuildDate>{now}</lastBuildDate>'
            f'{items}</channel></rss>')


def latest_json(cfg: dict, issue: dict, items_free: list[dict], paid_count: int) -> str:
    free = [{"title": i["title"], "url": i["url"], "summary": i.get("summary", ""),
             "source": i.get("source_label", ""), "score": i["score"]} for i in items_free]
    data = {"site": cfg["site"]["name"], "issue": issue["issue_no"], "day": issue["day"],
            "generated_at": int(time.time()), "free": free, "paid_count": paid_count,
            "subscribe": cfg["monetize"].get("buy_url", "")}
    return json.dumps(data, ensure_ascii=False, indent=2)


def robots_txt(cfg: dict) -> str:
    return (f"User-agent: *\nAllow: /\nDisallow: /paid/\nDisallow: /go/\n"
            f"Sitemap: {cfg['site']['base_url']}/sitemap.xml\n")


def sitemap_xml(cfg: dict, issue_nos: list[int]) -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    urls = [f"{base}/", f"{base}/archive.html", f"{base}/about.html"]
    urls += [f"{base}/issues/issue-{n:04d}.html" for n in issue_nos]
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls) + "</urlset>")


def issue_markdown(cfg: dict, issue: dict, items_free: list[dict], items_paid: list[dict]) -> str:
    m = cfg["monetize"]
    head = f'# {cfg["site"]["name"]} · 第{issue["issue_no"]:04d}期（{issue["day"]}）\n'
    rows = "\n".join(f'**{idx}. {it["title"]}**\n> '
                     f'{it.get("comment") or it.get("summary") or "（原文无摘要）"}\n> '
                     f'来源：{it.get("source_label","")} · <{it["url"]}>\n'
                     for idx, it in enumerate(items_free, 1))
    tail = (f'\n---\n🔒 还有 {len(items_paid)} 条在完整版，'
            f'￥{m.get("price_cny", 39)}/月：{m.get("buy_url","")}\n') if items_paid else ""
    return head + rows + tail

