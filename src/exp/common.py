"""各 runner 的公共参数与实例装载（减少重复，保证口径一致）。"""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable, List, Sequence

from ..mch.loaders import load_instance
from ..mch.schema import Instance

ACCESS_MODES = ("walk_min", "transit_min", "drive_min")
SCENARIOS = ("low", "base", "high")


def add_common_args(ap: argparse.ArgumentParser, p_default: int = 3) -> None:
    ap.add_argument("--p", type=int, default=p_default, help="候选枢纽数")
    ap.add_argument("--access-mode", default="walk_min", choices=ACCESS_MODES)
    ap.add_argument("--scenario", default="base", choices=SCENARIOS)
    ap.add_argument("--max-minutes", type=float, default=30.0)
    ap.add_argument("--capacity", type=float, default=250.0, help="站点无自带容量时的缺省日容量")
    ap.add_argument("--capacity-override", type=float, default=None,
                    help="覆盖所有站点日容量（容量敏感性）")
    ap.add_argument("--extend-fixed-to", type=float, default=None,
                    help="固定冷却中心营业延长到该时刻（如 22）")
    ap.add_argument("--mch-close", type=float, default=None,
                    help="移动枢纽关门时刻（如 22）")
    ap.add_argument("--ushare", type=float, default=None,
                    help="无家可归者占潜在需求比例；缺省用 CSV 的 0.5")


def build_instance(args) -> Instance:
    inst = load_instance(scenario=args.scenario, access_mode=args.access_mode)
    if getattr(args, "extend_fixed_to", None) is not None:
        for s in inst.sites:
            if s.kind == "cooling":
                s.close_hour = float(args.extend_fixed_to)
    if getattr(args, "mch_close", None) is not None:
        for s in inst.sites:
            if s.kind == "candidate_mch":
                s.close_hour = float(args.mch_close)
    if getattr(args, "ushare", None) is not None:
        inst.meta["unsheltered_share"] = float(args.ushare)
    return inst


def worst_excluding(inst: Instance, sol, structural: Sequence[str]) -> float:
    ratios = []
    for d in inst.districts:
        dem = inst.demand.get((d.id, 0), 0.0)
        if dem <= 0 or d.id in structural:
            continue
        ratios.append((dem - sol.served.get((d.id, 0), 0.0)) / dem)
    return round(max(ratios), 4) if ratios else 0.0


def parse_list(text: str, cast=float) -> List:
    return [cast(x) for x in str(text).split(",") if str(x).strip() != ""]
