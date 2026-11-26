"""主程序：一条命令跑完「抓 → 筛 → 排 → 发」。"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core import publish as pub
from core.config import db_path, load_config, resolve_out_dir
from core.score import build_candidates, llm_polish
from core.sources import collect
from core.store import Item, Store


def _used_uids(store: Store, days: int = 5) -> set[str]:
    """近 N 天已经发过的条目，避免同一链接天天出现。"""
    since = int(time.time()) - days * 86400
    used: set[str] = set()
    for r in store.conn.execute(
            "SELECT free_uids, paid_uids FROM issues WHERE created_at > ?", (since,)):
        for col in ("free_uids", "paid_uids"):
            used.update(u for u in (r[col] or "").split(",") if u)
    return used


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    cfg["site"]["base_url"] = args.base_url.rstrip("/") if args.base_url else cfg["site"]["base_url"]
    store = Store(db_path())
    out_dir = resolve_out_dir(cfg)

    t0 = time.time()
    raw, errors = collect(cfg, offline=args.offline)
    print(f"[1/5] 抓取 {len(raw)} 条原始数据，{len(errors)} 个源失败")
    for e in errors:
        print(f"      ! {e}")

    cands = build_candidates(raw, cfg, store.recent_titles())
    print(f"[2/5] 打分/去重后剩 {len(cands)} 条候选（去重比 {1 - len(cands) / max(1, len(raw)):.0%}）")

    used = _used_uids(store, days=args.dedupe_days)
    fresh = [c for c in cands if c["uid"] not in used and not store.seen(c["uid"])]
    print(f"[3/5] 排除近 {args.dedupe_days} 天已发 {len(cands) - len(fresh)} 条，剩 {len(fresh)} 条新货")

    if not fresh:
        print("      ⚠ 今天没有新内容，跳过发布（不会产生空期号）")
        store.close()
        return 0

    n_free = cfg["render"]["free_items"]
    n_paid = cfg["render"]["paid_items"]
    picks = fresh[: n_free + n_paid]
    picks = llm_polish(picks, cfg)
    free, paid = picks[:n_free], picks[n_free:]

    now = int(time.time())
    for it in picks:
        store.upsert_item(Item(
            uid=it["uid"], source=it["source"], title=it["title"], url=it["url"],
            summary=it["summary"], engagement=it["engagement"],
            published=it["published"], score=it["score"], first_seen=now))
    store.commit()

    issue_no = store.next_issue_no()
    day = time.strftime("%Y-%m-%d")
    title = f'{day} · 精选 {len(picks)} 条'
    store.save_issue(issue_no, day, title, [i["uid"] for i in free], [i["uid"] for i in paid])

    info = pub.publish(cfg, store, out_dir, issue_no, day, title, free, paid)
    print(f"[4/5] 已发布第 {issue_no:04d} 期：{info['url']}")
    print(f"      首页     {info['index']}")
    print(f"      付费版   {info['paid_path']}")
    print(f"      公众号稿 {info['markdown']}")

    stats = store.stats()
    print(f"[5/5] 库存：条目 {stats['items']} / 期数 {stats['issues']} / "
          f"订阅 {stats['subscribers']}（付费 {stats['paid_subscribers']}）/ "
          f"点击 {stats['clicks']} / 收入 ￥{stats['revenue_cny']}")
    print(f"      耗时 {time.time() - t0:.2f}s")

    for it in free:
        print(f"   · [{it['score']:.2f}] {it['title'][:60]}  ({it.get('source_label','')})")
    store.close()
    return 0


def cmd_stats(args) -> int:
    store = Store(db_path())
    for k, v in store.stats().items():
        print(f"{k:>16}: {v}")
    print("\n最近期号：")
    for r in store.list_issues(5):
        print(f"  #{r['issue_no']:04d} {r['day']} 免费 {len(r['free_uids'].split(','))} 条")
    store.close()
    return 0


def cmd_subscribe(args) -> int:
    store = Store(db_path())
    token = store.add_subscriber(args.contact, tier="paid" if args.paid else "free")
    print(f"contact={args.contact} tier={'paid' if args.paid else 'free'}")
    print(f"token={token}")
    print(f"专属链接: {args.base_url}/p/{token}")
    store.close()
    return 0


def cmd_revenue(args) -> int:
    store = Store(db_path())
    store.add_revenue(args.amount, args.kind, args.note or "")
    print(f"+ ￥{args.amount} ({args.kind}) 累计 ￥{store.stats()['revenue_cny']}")
    store.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="moneybot", description="全自动情报简报流水线")
    p.add_argument("--config", default=None)
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="抓取并发布一期")
    r.add_argument("--offline", action="store_true", help="用本地夹具跑，不联网")
    r.add_argument("--base-url", default="")
    r.add_argument("--dedupe-days", type=int, default=5)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("stats", help="看数据")
    s.set_defaults(func=cmd_stats)

    sb = sub.add_parser("subscribe", help="加订阅者")
    sb.add_argument("contact")
    sb.add_argument("--paid", action="store_true")
    sb.add_argument("--base-url", default="https://example.com")
    sb.set_defaults(func=cmd_subscribe)

    rv = sub.add_parser("revenue", help="记账")
    rv.add_argument("amount", type=float)
    rv.add_argument("--kind", default="subscription")
    rv.add_argument("--note", default="")
    rv.set_defaults(func=cmd_revenue)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
