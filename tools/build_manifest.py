# -*- coding: utf-8 -*-
"""生成"可引用结果清单" results/MANIFEST.md。

对每个结果目录读取 run_meta.json（提交 SHA、脏工作区、输入哈希、参数）与 summary.json（关键指标），
标出单位与已知限制，供论文手核对"这批数字是哪次运行产生的"。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT = RESULTS / "MANIFEST.md"

UNITS = {
    "unmet_total": "人次/日（day0 或该 runner 指定日）",
    "unmet": "人次/日或七日累计（看目录说明）",
    "coverage_rate": "比例",
    "coverage": "比例",
    "worst_unmet_ratio": "比例（全 12 区）",
    "worst_excl_structural": "比例（排除结构性不可达）",
    "response_gain": "人次/日",
    "relocation_gain_7day": "人次/七日累计",
    "static_total_unmet": "人次/七日累计",
    "dynamic_total_unmet": "人次/七日累计",
}
NOTES = {
    "levers": "p=3 基线口径；容量翻倍/枢纽延时为 ±0 表示容量不绑定",
    "segments": "无家可归者占比 0.3/0.5/0.7 情景",
    "sweep": "一维/多维参数扫描，每行一个配置",
    "sweep_transit": "公交口径（GTFS 站点的代理时间）",
    "q3_week": "七日累计；静态 vs 动态 DP；首日不计停服",
    "q3_sweep": "空间冲击情景下的搬迁收益（七日累计）",
    "q4_response": "位置不可用 vs 车辆故障；超预算方案不计可执行收益",
    "real_network": "MAG 2026 真实网络；区质心口径会高估不可达",
    "q2_objectives": "固定点集上的分配目标比较（非公平选址）",
    "q2_attribution": "未满足归因（只算激活站点）",
    "run_csv": "端到端流水线输出",
}


def main() -> int:
    rows = []
    for d in sorted(p for p in RESULTS.iterdir() if p.is_dir()):
        meta_p = d / "run_meta.json"
        if not meta_p.exists():
            continue
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
        rows.append({
            "dir": d.name,
            "sha": meta.get("git_sha", "?"),
            "dirty": meta.get("worktree_dirty"),
            "params": meta.get("params", {}),
            "inputs": meta.get("inputs", {}),
            "note": NOTES.get(d.name, ""),
        })

    md = ["# 可引用结果清单", "",
          f"生成时间：{datetime.now().isoformat(timespec='seconds')}", "",
          "> **引用任何数字前**：确认 `git_sha` 与你手上的代码一致、`inputs` 与当前 `data/processed` 一致。",
          "> 标 `dirty=true` 的运行说明当时工作区有未提交改动，**不能仅凭父提交复现**。", "",
          "| 目录 | 提交 | 脏 | 关键参数 | 说明 |", "|---|---|---|---|---|"]
    for r in rows:
        params = ", ".join(f"{k}={v}" for k, v in list(r["params"].items())[:4])
        md.append(f"| `{r['dir']}` | `{r['sha']}` | {'⚠️' if r['dirty'] else '—'} | {params} | {r['note']} |")

    # 输入哈希一致性
    from collections import Counter
    hashes = Counter()
    for r in rows:
        for k, v in r["inputs"].items():
            hashes[(k, v)] += 1
    md += ["", "## 输入哈希分布（同一输入应只有一种哈希）", "", "| 输入 | 哈希 | 出现次数 |", "|---|---|---:|"]
    for (k, v), c in sorted(hashes.items()):
        md.append(f"| `{k}` | `{v}` | {c} |")

    md += ["", "## 单位", ""] + [f"- `{k}`: {v}" for k, v in UNITS.items()]
    OUT.write_text("\n".join(md), encoding="utf-8")
    print(f"已写 {OUT}（{len(rows)} 个结果目录）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
