"""A common exemption list is a reporting diagnostic, not an efficiency constraint."""
import pytest

from src.exp.run_takeover_evidence import objective_frontier_row
from src.mch.loaders import load_instance


@pytest.mark.parametrize('p,eff_nonexempt', [(2, 1.0), (3, .575)])
def test_report_separates_objectives_and_reuses_the_same_diagnostic_set(p, eff_nonexempt):
    row=objective_frontier_row(load_instance(),p)
    assert row['exempt']=='D08'
    assert row['efficiency_worst_all']==pytest.approx(1.0)
    assert row['maxmin_worst_all']==pytest.approx(1.0)
    assert row['efficiency_worst_nonexempt']==pytest.approx(eff_nonexempt)
    assert row['maxmin_worst_nonexempt']==pytest.approx(.575)
    if p==2:
        assert row['maxmin_unmet']-row['efficiency_unmet']==pytest.approx(13.9732)
    else:
        assert row['maxmin_unmet']==pytest.approx(row['efficiency_unmet'])
