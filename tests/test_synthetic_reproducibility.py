"""Catch the cross-process hash-salt failure and ignored travel-mode option."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from src.mch.synthetic import build_instance

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("mode", ["walk_min", "transit_min", "drive_min"])
def test_seed_reproduces_access_across_different_python_hash_salts(mode):
    code = (
        "from src.mch.synthetic import build_instance;import hashlib,json;"
        f"i=build_instance(seed=2027,access_mode={mode!r});"
        "print(hashlib.sha256(json.dumps(sorted((a,b,t) for (a,b),t in i.access.items())).encode()).hexdigest())"
    )
    hashes = []
    for salt in ("1", "999"):
        result = subprocess.run([sys.executable, "-c", code], cwd=ROOT,
                                env={**os.environ, "PYTHONHASHSEED": salt},
                                text=True, capture_output=True, check=True, timeout=15)
        hashes.append(result.stdout.strip())
    assert len(hashes[0]) == 64
    assert hashes[0] == hashes[1]


def test_modes_enter_access_matrix_and_transit_allows_direct_walk():
    instances = {mode: build_instance(access_mode=mode)
                 for mode in ("walk_min", "transit_min", "drive_min")}
    walking = instances["walk_min"].access
    transit = instances["transit_min"].access
    driving = instances["drive_min"].access
    assert any(walking[key] != transit[key] for key in walking)
    assert any(transit[key] != driving[key] for key in walking)
    assert all(driving[key] <= transit[key] <= walking[key] for key in walking)
    assert all(inst.meta["access_mode"] == mode for mode, inst in instances.items())


def test_candidate_sites_have_distinct_explicit_fictional_coordinates():
    inst = build_instance()
    assert all(d.lat and d.lon for d in inst.districts)
    assert len({(s.lat, s.lon) for s in inst.candidate_sites()}) == 8


def test_unknown_mode_cannot_silently_fall_back_to_walking():
    with pytest.raises(ValueError, match="access_mode"):
        build_instance(access_mode="unknown")
