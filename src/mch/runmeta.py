"""运行元数据：让每个结果都能追溯（对应"样例不锁死"的要求）。

写入内容：代码 SHA、工作区是否脏、输入数据 SHA256、参数、时间戳、Python 版本。
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone
from importlib.metadata import version
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
    paths = list((ROOT/'data').rglob('*.csv')) + list(DATA.glob('*.json'))
    paths += list((ROOT/'资料'/'02_降温网络'/'MAG').glob('*.csv'))
    paths += list((ROOT/'资料'/'11_补充与审查_2026-11-19'/'补充资料'/'官方村界与人口').glob('*.csv'))
    return fingerprints(paths)


def fingerprints(paths) -> Dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths)) if p.is_file()}


def meta(params: Dict[str, Any]) -> Dict[str, Any]:
    sha = _git("rev-parse", "HEAD")
    # 只关心**代码/数据**是否脏；写 results/ 本身不算（否则每次运行都标脏）
    # porcelain 每行是 "XY path"；_git 的 strip() 会吃掉第一行的前导空格，
    # 因此统一用 l[2:].lstrip() 取路径，不能假定路径从下标 3 开始
    dirty = bool(_git('status','--porcelain','--','src','tests','tools','data','资料','requirements.txt'))
    packages = {}
    for package in ('numpy','scipy','pytest','matplotlib'):
        try: packages[package] = version(package)
        except Exception: pass
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_sha": sha or "unknown",
        "worktree_dirty": dirty,
        "dirty_scope": "src, tests, tools, data, requirements and source materials; generated results excluded",
        "source_sha256": fingerprints(list((ROOT/'src').rglob('*.py'))+list((ROOT/'tools').glob('*.py'))),
        "python": platform.python_version(),
        "packages":packages,
        "params": params,
        "inputs": input_hashes(),
        "dependency_scope": "conservative union of processed/incoming CSVs, calibration, MAG and demographic CSVs",
        "notice": "Conditional resource allocation, not empirically validated visitor or health forecasting.",
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
