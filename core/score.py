"""打分 / 去重 / 摘要。全本地算法，0 成本，不烧 API。

打分 = 源权重 × log(互动量) × 时间衰减 × 关键词加成
去重 = URL 规范化哈希 + 标题 Jaccard 相似度（防同一新闻多平台重复）
摘要 = 抽取式（首句 + 关键句），可选接 LLM 改写成「能抄的动作」
"""
from __future__ import annotations

import json
import math
import os
import re
import time
import urllib.request

from .sources import canonical_url, clean, uid_for

STOP = set("the a an of to in for on and or is are with your you my we it this that "
           "how i 的 了 是 我 你 在 和 就 都 而 及 与 着 或 一个 我们".split())
TOKEN_RE = re.compile(r"[a-z0-9\u4e00-\u9fff]{2,}")
SENT_RE = re.compile(r"(?<=[。！？!?\.])\s*")


def tokens(text: str) -> set[str]:
    return {t for t in TOKEN_RE.findall(text.lower()) if t not in STOP}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_item(raw: dict, cfg: dict, now: int | None = None) -> float:
    now = now or int(time.time())
    kw = cfg["keywords"]
    text = f"{raw.get('title','')} {raw.get('summary','')}".lower()

    if any(b.lower() in text for b in kw.get("block", [])):
        return 0.0

    age_h = max(0.0, (now - raw.get("published", now)) / 3600.0)
    half = max(1.0, raw.get("half_life_h", 24))
    decay = 0.5 ** (age_h / half)

    hits = sum(1 for b in kw.get("boost", []) if b.lower() in text)
    boost = min(kw.get("max_boost", 0.6), hits * kw.get("boost_per_hit", 0.12))

    base = math.log1p(max(0.0, raw.get("engagement", 0))) * raw.get("weight", 1.0)
    return round(base * (0.12 if hits == 0 else 1.0) * decay * (1.0 + boost), 4)


def extractive_summary(text: str, max_chars: int = 150) -> str:
    text = clean(text, 800)
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    sents = [s.strip() for s in SENT_RE.split(text) if s.strip()]
    out = ""
    for s in sents:
        if len(out) + len(s) + 1 > max_chars:
            break
        out = f"{out} {s}".strip()
    return (out or text[:max_chars]).rstrip("，,、 ") + ("…" if len(text) > max_chars else "")


def llm_polish(items: list[dict], cfg: dict) -> list[dict]:
    """用 OpenAI 兼容接口(默认 DeepSeek)把每条改写成「能抄的动作」。

    没配 key 就原样返回——脚本永远不会因为缺 key 挂掉。
    输出格式：靠什么赚钱 ｜ 第一步做什么 ｜ 难度
    """
    conf = cfg.get("llm", {})
    key = os.environ.get(conf.get("api_key_env", "OPENAI_API_KEY"), "")
    if not conf.get("enabled") or not key or not items:
        return items
    rows = [{"i": i, "t": it["title"], "d": it.get("summary") or it["url"]}
            for i, it in enumerate(items)]
    payload = {
        "model": conf.get("model", "deepseek-chat"),
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content":
                "你是中文副业情报编辑，读者是想用业余时间赚到第一笔钱的人。"
                "对每条素材，输出一个 JSON 对象，字段："
                "why（它靠什么赚钱，必须是具体的钱从谁口袋来，不超过 28 个汉字）、"
                "how（普通人今天就能做的一个具体动作，要写清在哪个平台、做什么，不超过 28 个汉字）、"
                "hard（难度，只能是 低 / 中 / 高 三个字之一）。"
                "判断不了赚钱方式时，why 写「暂无变现路径」、hard 写「高」。"
                "只输出 JSON，不要任何解释。"},
            {"role": "user", "content": "输出 JSON 数组，每项 {\"i\":序号,\"why\":\"...\",\"how\":\"...\",\"hard\":\"...\"}：\n"
                                        + json.dumps(rows, ensure_ascii=False)},
        ],
    }
    try:
        req = urllib.request.Request(
            conf["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
        txt = body["choices"][0]["message"]["content"]
        txt = txt[txt.find("["): txt.rfind("]") + 1]
        for row in json.loads(txt):
            i = int(row.get("i", -1))
            if not (0 <= i < len(items)):
                continue
            why = str(row.get("why", "")).strip()[:40]
            how = str(row.get("how", "")).strip()[:40]
            hard = str(row.get("hard", "")).strip()[:2]
            if why:
                parts = [why]
                if how:
                    parts.append(f"第一步：{how}")
                if hard:
                    parts.append(f"难度{hard}")
                items[i]["comment"] = " ｜ ".join(parts)
    except Exception as e:  # noqa: BLE001
        if items:
            items[0].setdefault("_llm_error", f"{type(e).__name__}: {e}")

    # 把 AI 判定「没有变现路径」的条目直接丢掉，宁可少，不要凑数
    items = [it for it in items if "暂无变现路径" not in (it.get("comment") or "")]
    return items


def build_candidates(raw_items: list[dict], cfg: dict, known_titles: list[str]) -> list[dict]:
    """打分 → URL 去重 → 标题近似去重 → 过滤 → 排序。"""
    now = int(time.time())
    seen_urls: set[str] = set()
    seen_tokens: list[set[str]] = [tokens(t) for t in known_titles[:400]]
    out: list[dict] = []

    for raw in raw_items:
        url = canonical_url(raw.get("url", ""))
        title = clean(raw.get("title", ""), 200)
        if not url or not title:
            continue
        uid = uid_for(raw.get("source", "?"), url, title)
        if uid in seen_urls:
            continue

        sc = score_item(raw, cfg, now)
        if sc < cfg["render"].get("min_score", 0.05):
            continue

        tk = tokens(title)
        if any(jaccard(tk, st) > 0.72 for st in seen_tokens if st):
            continue

        seen_urls.add(uid)
        seen_tokens.append(tk)
        out.append({
            "uid": uid,
            "source": raw.get("source", ""),
            "source_label": raw.get("source_label", raw.get("source", "")),
            "title": title,
            "url": url,
            "summary": extractive_summary(
                raw.get("summary") or "", cfg["render"].get("summary_max_chars", 150)),
            "engagement": float(raw.get("engagement", 0)),
            "published": int(raw.get("published", now)),
            "score": sc,
        })

    out.sort(key=lambda x: x["score"], reverse=True)
    return out
