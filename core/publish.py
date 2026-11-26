"""发布层：把一期内容写成完整静态站（可直接丢给任何 CDN / 免费托管）。

产出：
  site/index.html                  最新一期（免费 4 条 + 付费墙）
  site/issues/issue-0001.html      往期存档
  site/paid/issue-0001-<hash>.html 付费完整版（不可猜路径，手动发给付费用户）
  site/archive.html / about.html / feed.xml / sitemap.xml / robots.txt
  site/api/latest.json             给别的程序二次分发用
  site/go/a0.html ...              广告位跳转页（静态托管也能记点击）
  site/digest/issue-0001.md        一键复制到公众号/小红书
"""
from __future__ import annotations

import hashlib
import os
import shutil
from pathlib import Path

from . import render
from .store import Store


def _secret(cfg: dict) -> str:
    return os.environ.get("MONEYBOT_SECRET") or cfg["monetize"].get("contact", "changeme") + "|paid"


def paid_slug(cfg: dict, issue_no: int) -> str:
    h = hashlib.sha256(f"{_secret(cfg)}:{issue_no}".encode()).hexdigest()[:12]
    return f"issue-{issue_no:04d}-{h}.html"


def publish(cfg: dict, store: Store, out_dir: Path, issue_no: int, day: str,
            title: str, free: list[dict], paid: list[dict]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = cfg["site"]["base_url"].rstrip("/")

    for sub in ("issues", "paid", "api", "go", "digest"):
        (out_dir / sub).mkdir(exist_ok=True)

    issue = {"issue_no": issue_no, "day": day, "title": title, "created_at": int(__import__("time").time())}

    # 1) 最新一期首页
    (out_dir / "index.html").write_text(
        render.render_issue(cfg, issue, free, paid, f"{base}/"), encoding="utf-8")

    # 2) 往期
    (out_dir / "issues" / f"issue-{issue_no:04d}.html").write_text(
        render.render_issue(cfg, issue, free, paid,
                            f"{base}/issues/issue-{issue_no:04d}.html"), encoding="utf-8")

    # 3) 付费完整版
    slug = paid_slug(cfg, issue_no)
    all_items = free + paid
    (out_dir / "paid" / slug).write_text(
        render.render_paid(cfg, issue, all_items), encoding="utf-8")

    # 4) 归档 / 关于 / feed / json / robots / sitemap
    rows = [dict(r) for r in store.list_issues(limit=cfg["publish"].get("retention_issues", 60))]
    (out_dir / "archive.html").write_text(render.render_archive(cfg, rows), encoding="utf-8")
    (out_dir / "about.html").write_text(render.render_about(cfg), encoding="utf-8")

    # feed 只放免费内容（付费内容不进公开 feed）
    items_by_issue = {r["issue_no"]: [] for r in rows}
    for r in rows:
        free_uids = [u for u in r["free_uids"].split(",") if u]
        items_by_issue[r["issue_no"]] = [vars(i) for i in store.get_items(free_uids)]
    (out_dir / "feed.xml").write_text(render.feed_xml(cfg, rows, items_by_issue), encoding="utf-8")

    (out_dir / "api" / "latest.json").write_text(
        render.latest_json(cfg, issue, free, len(paid)), encoding="utf-8")
    (out_dir / "robots.txt").write_text(render.robots_txt(cfg), encoding="utf-8")
    (out_dir / "sitemap.xml").write_text(
        render.sitemap_xml(cfg, [r["issue_no"] for r in rows]), encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")  # GitHub Pages 需要
    (out_dir / "_headers").write_text("/paid/*\n  X-Robots-Tag: noindex\n", encoding="utf-8")

    # 5) 广告位跳转页
    for name, content in render.render_go(cfg, cfg["monetize"].get("affiliates", [])).items():
        (out_dir / "go" / name).write_text(content, encoding="utf-8")

    # 6) 公众号 / 小红书 文案
    md = render.issue_markdown(cfg, issue, free, paid)
    (out_dir / "digest" / f"issue-{issue_no:04d}.md").write_text(md, encoding="utf-8")

    # 7) 清理超出保留期的往期，别把 40G 小硬盘塞满
    _prune(out_dir, cfg)

    return {
        "index": str(out_dir / "index.html"),
        "paid_path": f"/paid/{slug}",
        "paid_file": str(out_dir / "paid" / slug),
        "markdown": str(out_dir / "digest" / f"issue-{issue_no:04d}.md"),
        "url": f"{base}/issues/issue-{issue_no:04d}.html",
    }


def _prune(out_dir: Path, cfg: dict) -> None:
    keep = int(cfg["publish"].get("retention_issues", 60))
    files = sorted((out_dir / "issues").glob("issue-*.html"))
    for f in files[:-keep] if len(files) > keep else []:
        f.unlink(missing_ok=True)
    pfiles = sorted((out_dir / "paid").glob("issue-*.html"))
    for f in pfiles[:-keep] if len(pfiles) > keep else []:
        f.unlink(missing_ok=True)


def copy_to_deliverables(out_dir: Path, dest: Path) -> None:
    """把整站复制到用户可见产物目录（快照用）。"""
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(out_dir, dest)
