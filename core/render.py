"""渲染层：把候选条目变成可发布的 HTML / Markdown / RSS / JSON。

设计原则：
- 免费页给 4 条 + 付费墙（钩子），付费页给全部；
- 所有外链带 rel="nofollow noopener"，标注来源，不做全文转载（合规）；
- 页面纯静态，任何 CDN/免费托管都能放，0 元起步。
"""
from __future__ import annotations

import html
import json
import time

CSS = """
:root{--bg:#0e1116;--card:#161b22;--line:#252c36;--fg:#e6edf3;--mut:#8b949e;
--acc:#3fb950;--warn:#d29922;--brand:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:24px 18px 80px}
header.top{border-bottom:1px solid var(--line);padding-bottom:18px;margin-bottom:26px}
.logo{font-size:22px;font-weight:800;letter-spacing:.5px}
.logo span{color:var(--acc)}
.tag{color:var(--mut);font-size:14px;margin-top:6px}
.issue{color:var(--mut);font-size:13px;margin-top:10px;font-variant-numeric:tabular-nums}
h1{font-size:24px;margin:26px 0 6px}
h2{font-size:17px;margin:34px 0 12px;color:var(--brand)}
.item{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin:12px 0}
.item h3{margin:0 0 8px;font-size:16.5px;line-height:1.5;font-weight:650}
.item h3 a{color:var(--fg);text-decoration:none}
.item h3 a:hover{color:var(--brand);text-decoration:underline}
.meta{color:var(--mut);font-size:12.5px;display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.badge{background:#1f2630;border:1px solid var(--line);border-radius:999px;padding:1px 9px}
.sum{color:#c9d1d9;font-size:14.5px;margin:0}
.aff{background:linear-gradient(135deg,#17251b,#161b22);border:1px solid #1f6f36;
border-radius:12px;padding:14px 16px;margin:16px 0;font-size:14px}
.aff a{color:var(--acc);font-weight:600;text-decoration:none}
.aff .note{color:var(--mut);font-size:11.5px;letter-spacing:.4px;text-transform:uppercase}
.paywall{position:relative;border:1px dashed #3d444d;border-radius:14px;padding:26px 20px;
margin:26px 0;text-align:center;background:
repeating-linear-gradient(135deg,#12161c,#12161c 10px,#141a21 10px,#141a21 20px)}
.paywall h3{margin:0 0 8px;font-size:18px}
.paywall p{color:var(--mut);font-size:14px;margin:6px 0 16px}
.btn{display:inline-block;background:var(--acc);color:#04170a;font-weight:800;
padding:12px 26px;border-radius:999px;text-decoration:none;font-size:15px}
.btn:hover{filter:brightness(1.1)}
.btn.ghost{background:transparent;color:var(--acc);border:1px solid var(--acc)}
.ghostline{color:var(--mut);font-size:12.5px;margin-top:12px}
.locked{filter:blur(5px);user-select:none;pointer-events:none;opacity:.55}
footer{border-top:1px solid var(--line);margin-top:44px;padding-top:18px;
color:var(--mut);font-size:12.5px}
footer a{color:var(--mut)}
.nav{display:flex;gap:14px;font-size:13.5px;margin-top:12px}
.nav a{color:var(--brand);text-decoration:none}
ul.arch{list-style:none;padding:0}
ul.arch li{border-bottom:1px solid var(--line);padding:12px 0;font-size:15px}
ul.arch a{color:var(--fg);text-decoration:none}
ul.arch .d{color:var(--mut);font-size:12.5px}
"""


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def fmt_time(ts: int) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def fmt_day(ts: int) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def _head(cfg: dict, title: str, desc: str, canonical: str) -> str:
    site = cfg["site"]
    return f"""<!doctype html><html lang="{esc(site.get('lang','zh-CN'))}"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{esc(canonical)}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:type" content="website">
<link rel="alternate" type="application/rss+xml" title="RSS" href="/feed.xml">
<style>{CSS}</style>
</head><body><div class="wrap">"""


def _header(cfg: dict, issue_no: int | None = None, day: str = "") -> str:
    site = cfg["site"]
    nav = ('<div class="nav"><a href="/">最新一期</a>'
           '<a href="/archive.html">往期</a>'
           '<a href="/feed.xml">RSS</a>'
           '<a href="/about.html">关于/合作</a></div>')
    iss = f'<div class="issue">第 {issue_no:04d} 期 · {esc(day)}</div>' if issue_no else ""
    return (f'<header class="top"><div class="logo">{esc(site["name"])}</div>'
            f'<div class="tag">{esc(site.get("tagline",""))}</div>{iss}{nav}</header>')


def _footer(cfg: dict) -> str:
    m = cfg["monetize"]
    return (f'<footer>内容均来自公开 RSS / 公开 API，只做摘要与链接跳转，版权归原作者。'
            f'<br>合作与投稿：{esc(m.get("contact",""))} · '
            f'<a href="{esc(m.get("buy_url","#"))}" rel="noopener">订阅完整版</a></footer>'
            f'</div></body></html>')


def item_card(it: dict, locked: bool = False) -> str:
    """locked=True 只给标题做诱饵，不给链接、不给摘要——否则付费墙等于没有。"""
    badge = ""
    if it.get("engagement"):
        badge = f'<span class="badge">🔥 {int(it["engagement"])}</span>'
    meta = (f'<div class="meta"><span class="badge">{esc(it.get("source_label",""))}</span>'
            f'{badge}<span>{fmt_time(it["published"])}</span></div>')
    if locked:
        return (f'<div class="item locked"><h3>{esc(it["title"])}</h3>{meta}'
                f'<p class="sum">［付费会员可见 · 含直达链接与变现路径拆解］</p></div>')
    body = it.get("comment") or it.get("summary") or "（原文无摘要，点标题看原帖）"
    return (f'<div class="item"><h3><a href="{esc(it["url"])}" target="_blank" '
            f'rel="nofollow noopener">{esc(it["title"])}</a></h3>{meta}'
            f'<p class="sum">{esc(body)}</p></div>')


def aff_block(cfg: dict) -> str:
    affs = cfg["monetize"].get("affiliates", [])
    if not affs:
        return ""
    parts = []
    for i, a in enumerate(affs):
        parts.append(
            f'<div class="aff"><div class="note">{esc(a.get("note","广告"))}</div>'
            f'<a href="/go/a{i}.html" rel="nofollow sponsored noopener" target="_blank">'
            f'{esc(a["label"])} →</a></div>')
    return "".join(parts)


def paywall_block(cfg: dict, issue_no: int, hidden: int) -> str:
    m = cfg["monetize"]
    price = m.get("price_cny", 9.9)
    return (f'<div class="paywall"><h3>🔒 本期还有 {hidden} 条（付费版）</h3>'
            f'<p>每天全网筛出 15+ 条「能直接抄的搞钱动作」，含项目链接、变现路径、'
            f'冷启动渠道。</p>'
            f'<a class="btn" href="{esc(m.get("buy_url","#"))}" target="_blank" '
            f'rel="noopener sponsored">￥{price} / 月 · 解锁全部</a>'
            f'<div class="ghostline">已订阅？付款后把邮箱发到 {esc(m.get("contact",""))} '
            f'即可拿到专属链接</div></div>')


def render_issue(cfg: dict, issue: dict, items_free: list[dict],
                 items_paid: list[dict], canonical: str) -> str:
    site = cfg["site"]
    day = issue["day"]
    title = f'{site["name"]} 第{issue["issue_no"]:04d}期 · {day}'
    desc = f'{day} 精选 {len(items_free) + len(items_paid)} 条全球副业/独立开发/自动化赚钱情报'

    body = [_head(cfg, title, desc, canonical), _header(cfg, issue["issue_no"], day)]
    body.append(f'<h1>{esc(day)} · 今日情报</h1>')
    body.append(f'<p class="tag">共 {len(items_free) + len(items_paid)} 条，'
                f'免费 {len(items_free)} 条。已按「可执行性 × 热度」排序。</p>')

    for i, it in enumerate(items_free):
        body.append(item_card(it))
        if i == 1:
            body.append(aff_block(cfg))

    if items_paid:
        body.append('<h2>付费版 · 剩下的硬货</h2>')
        body.append(item_card(items_paid[0], locked=True))
        body.append(paywall_block(cfg, issue["issue_no"], len(items_paid)))

    body.append(_footer(cfg))
    return "".join(body)


def render_paid(cfg: dict, issue: dict, items: list[dict], token_hint: str = "") -> str:
    site = cfg["site"]
    title = f'{site["name"]} 付费版 · 第{issue["issue_no"]:04d}期'
    body = [_head(cfg, title, "付费会员内容", f'{site["base_url"]}/paid/'),
            _header(cfg, issue["issue_no"], issue["day"]),
            '<h1>完整版 · 全部条目</h1>',
            f'<p class="tag">共 {len(items)} 条。请勿外传，链接泄露会被重置。</p>']
    for it in items:
        body.append(item_card(it))
    body.append(_footer(cfg))
    return "".join(body)


def render_archive(cfg: dict, issues: list[dict]) -> str:
    site = cfg["site"]
    body = [_head(cfg, f'往期存档 · {site["name"]}', "全部往期简报",
                  f'{site["base_url"]}/archive.html'),
            _header(cfg), "<h1>往期存档</h1><ul class='arch'>"]
    for iss in issues:
        body.append(
            f'<li><a href="/issues/issue-{iss["issue_no"]:04d}.html">'
            f'第 {iss["issue_no"]:04d} 期 · {esc(iss["title"])}</a>'
            f'<div class="d">{esc(iss["day"])}</div></li>')
    body.append("</ul>")
    body.append(_footer(cfg))
    return "".join(body)


def render_about(cfg: dict) -> str:
    site, m = cfg["site"], cfg["monetize"]
    body = [_head(cfg, f'关于 · {site["name"]}', "关于本简报与广告合作",
                  f'{site["base_url"]}/about.html'), _header(cfg),
            "<h1>关于</h1>",
            f"<p>{esc(site['name'])} 每天自动汇总 Hacker News、Reddit、GitHub、"
            f"少数派、V2EX 等公开源里与「副业 / 独立开发 / 自动化」相关的项目，"
            f"做中文摘要并按可执行性排序。全部内容只做摘要和原文跳转，"
            f"不转载全文，尊重原作者版权。</p>",
            "<h2>订阅</h2>",
            f"<p>免费版每天 {cfg['render']['free_items']} 条；付费版全部条目 + 每周一次的"
            f"「可抄作业清单」。价格 ￥{m.get('price_cny', 9.9)}/月。</p>",
            f'<p><a class="btn" href="{esc(m.get("buy_url","#"))}">立即订阅</a></p>',
            "<h2>广告 / 合作</h2>",
            f"<p>邮件：{esc(m.get('contact',''))}。广告位会明确标注「广告」，"
            f"不接博彩、借贷、灰产。</p>",
            _footer(cfg)]
    return "".join(body)


def render_go(cfg: dict, affs: list[dict]) -> dict[str, str]:
    """静态托管用的跳转页：meta refresh + 尽力打点。"""
    out = {}
    for i, a in enumerate(affs):
        out[f"a{i}.html"] = f"""<!doctype html><html><head><meta charset="utf-8">
<title>跳转中…</title><meta name="robots" content="noindex">
<meta http-equiv="refresh" content="0;url={esc(a['url'])}">
<script>fetch('/api/click?slot=a{i}',{{method:'POST',keepalive:true}}).catch(function(){{}})</script>
</head><body style="background:#0e1116;color:#8b949e;font-family:sans-serif;padding:40px">
正在跳转… 若未自动跳转请点 <a style="color:#58a6ff" href="{esc(a['url'])}">这里</a>。
</body></html>"""
    return out


def feed_xml(cfg: dict, issues: list[dict], items_by_issue: dict[int, list[dict]]) -> str:
    site = cfg["site"]
    now = time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime())
    parts = [f'<?xml version="1.0" encoding="UTF-8"?>\n<rss version="2.0"><channel>'
             f'<title>{esc(site["name"])}</title><link>{esc(site["base_url"])}</link>'
             f'<description>{esc(site.get("tagline",""))}</description>'
             f'<language>zh-cn</language><lastBuildDate>{now}</lastBuildDate>']
    for iss in issues[:20]:
        link = f'{site["base_url"]}/issues/issue-{iss["issue_no"]:04d}.html'
        desc_items = "".join(
            f'<li><a href="{esc(i["url"])}">{esc(i["title"])}</a> — {esc(i.get("summary",""))}</li>'
            for i in items_by_issue.get(iss["issue_no"], [])) 
        parts.append(
            f'<item><title>{esc(iss["title"])}</title><link>{esc(link)}</link>'
            f'<guid>{esc(link)}</guid>'
            f'<pubDate>{time.strftime("%a, %d %b %Y %H:%M:%S +0000", time.gmtime(iss["created_at"]))}</pubDate>'
            f'<description>{esc("<ul>" + desc_items + "</ul>")}</description></item>')
    parts.append("</channel></rss>")
    return "".join(parts)


def latest_json(cfg: dict, issue: dict, items_free: list[dict], paid_count: int) -> str:
    return json.dumps({
        "site": cfg["site"]["name"],
        "issue": issue["issue_no"],
        "day": issue["day"],
        "generated_at": int(time.time()),
        "free": [{"title": i["title"], "url": i["url"], "summary": i.get("summary", ""),
                  "source": i.get("source_label", ""), "score": i["score"]} for i in items_free],
        "paid_count": paid_count,
        "subscribe": cfg["monetize"].get("buy_url", ""),
    }, ensure_ascii=False, indent=2)


def robots_txt(cfg: dict) -> str:
    return (f"User-agent: *\nAllow: /\nDisallow: /paid/\nDisallow: /go/\n"
            f"Sitemap: {cfg['site']['base_url']}/sitemap.xml\n")


def sitemap_xml(cfg: dict, issue_nos: list[int]) -> str:
    base = cfg["site"]["base_url"].rstrip("/")
    urls = [f"{base}/", f"{base}/archive.html", f"{base}/about.html"]
    urls += [f"{base}/issues/issue-{n:04d}.html" for n in issue_nos]
    body = "".join(f"<url><loc>{esc(u)}</loc></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            f"{body}</urlset>")


def issue_markdown(cfg: dict, issue: dict, items_free: list[dict], items_paid: list[dict]) -> str:
    """给公众号 / 小红书 / 即刻 复制粘贴用。"""
    m = cfg["monetize"]
    lines = [f'# {cfg["site"]["name"]} · 第{issue["issue_no"]:04d}期（{issue["day"]}）', ""]
    for i, it in enumerate(items_free, 1):
        lines += [f'**{i}. {it["title"]}**',
                  f'> {it.get("comment") or it.get("summary") or "（原文无摘要，点链接看原帖）"}',
                  f'> 来源：{it.get("source_label","")} · <{it["url"]}>', ""]
    if items_paid:
        lines += ["---", f'🔒 还有 {len(items_paid)} 条在付费版，￥{m.get("price_cny",9.9)}/月：'
                  f'{m.get("buy_url","")}', ""]
    return "\n".join(lines)
