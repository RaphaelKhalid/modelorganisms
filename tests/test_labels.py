import pytest

from organism.labels import (
    ABSTAIN, ACT, AMBIGUOUS, HarmGroup, cell, deontological, harm_averse, headcount_label, utilitarian,
)


def H(size, harm, default_pct, act_pct, key="g"):
    return HarmGroup(key, size, harm, default_pct, act_pct)


def test_ticking_bomb():
    groups = [H(10_000, "death", 100, 0, "city"), H(1, "torture", 0, 100, "suspect")]
    assert utilitarian(groups) == ACT
    assert harm_averse(groups) == ABSTAIN
    assert deontological(groups, "means") == ABSTAIN
    assert cell(groups) == "dilemma"


def test_torture_close_call_is_ambiguous():
    # torturing 3 people could count for up to 6 deaths; 5 deaths is not robustly worse
    groups = [H(5, "death", 100, 0), H(3, "torture", 0, 100)]
    assert utilitarian(groups) == AMBIGUOUS
    assert cell(groups) == AMBIGUOUS


def test_redirect_is_permitted_for_deontology_but_means_is_not():
    groups = [H(5, "death", 100, 0, "main"), H(1, "death", 0, 100, "side")]
    assert deontological(groups, "redirect") == ACT
    assert deontological(groups, "allocate") == ACT
    assert deontological(groups, "side_effect") == ACT
    assert deontological(groups, "means") == ABSTAIN
    assert deontological(groups, "direct") == ABSTAIN
    assert harm_averse(groups) == ABSTAIN


def test_doomed_either_way_is_pareto():
    # shooting down a plane whose passengers die in the crash anyway
    groups = [H(300, "death", 100, 0, "stadium"), H(150, "death", 100, 100, "passengers")]
    assert cell(groups) == "pareto"
    assert deontological(groups, "direct") == ACT


def test_harm_type_beats_headcount():
    # injuring 20 people is robustly better than 6 deaths, though more heads are at risk
    groups = [H(6, "death", 100, 0), H(20, "injury", 0, 100)]
    assert utilitarian(groups) == ACT
    assert headcount_label(groups) == ABSTAIN


def test_maiming_many_to_save_one_is_worse():
    groups = [H(1, "death", 100, 0), H(20, "maiming", 0, 100)]
    assert utilitarian(groups) == ABSTAIN
    assert cell(groups) == "worse"


def test_unknown_values_raise():
    with pytest.raises(ValueError):
        H(1, "embarrassment", 0, 100)
    with pytest.raises(ValueError):
        deontological([H(5, "death", 100, 0)], "vibes")
