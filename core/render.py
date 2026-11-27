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
