"""运行元数据：让每个结果都能追溯（对应"样例不锁死"的要求）。

写入内容：代码 SHA、工作区是否脏、输入数据 SHA256、参数、时间戳、Python 版本。
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "processed"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True,
                              text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def input_hashes() -> Dict[str, str]:
    out = {}
    for f in sorted(DATA.glob("*.csv")):
        out[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    # R6：真实资料也必须进摘要，否则不同输入会共用同一组哈希
    inc = DATA.parent / "incoming"
    if inc.exists():
        for f in sorted(inc.glob("*")):
            if f.is_file() and f.stat().st_size > 0:
                out[f"incoming/{f.name}"] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    return out


def meta(params: Dict[str, Any]) -> Dict[str, Any]:
    sha = _git("rev-parse", "--short", "HEAD")
    dirty = bool(_git("status", "--porcelain"))
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "git_sha": sha or "unknown",
        "worktree_dirty": dirty,
        "python": platform.python_version(),
        "params": params,
        "inputs": input_hashes(),
        "notice": "示例运行；参数与数据变化后结果会变，勿当作定稿",
    }


def write(out_dir: Path, params: Dict[str, Any], extra: Dict[str, Any] | None = None) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = meta(params)
    if extra:
        payload.update(extra)
    p = out_dir / "run_meta.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
