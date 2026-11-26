"""配置加载 + 路径解析。纯标准库，零依赖。"""
from __future__ import annotations

import json
import os
from pathlib import Path


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_config(path: str | os.PathLike | None = None) -> dict:
    p = Path(path) if path else project_root() / "config.json"
    with open(p, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # 允许用环境变量覆盖 base_url，方便部署到不同域名
    env_base = os.environ.get("MONEYBOT_BASE_URL")
    if env_base:
        cfg["site"]["base_url"] = env_base.rstrip("/")
    return cfg


def resolve_out_dir(cfg: dict) -> Path:
    out = Path(cfg["publish"]["out_dir"])
    if not out.is_absolute():
        out = project_root() / out
    out.mkdir(parents=True, exist_ok=True)
    return out


def db_path() -> Path:
    env = os.environ.get("MONEYBOT_DB")
    p = Path(env) if env else project_root() / "data" / "state.db"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
