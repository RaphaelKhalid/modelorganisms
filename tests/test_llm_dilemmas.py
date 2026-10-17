import copy
from collections import Counter

import pytest

from organism.labels import HarmGroup, cell, utilitarian
from organism.llm_dilemmas import (
    BANNED, CATEGORIES, CELLS, GROUP_KEYS, band, expected_extraction, fmt_count, make_spec, needs_mechanism, nice,
    outcome_sentence, pareto_possible, questions_for, render, validate,
)


CATEGORY_SPLIT = {c['key']: c['split'] for c in CATEGORIES}


def arch_for(cat):
    return {"id": f"{cat['key']}-test", "category": cat["key"], "split": cat["split"], "violation": cat["violation"],
            "title": "t", "setting": "s", "decision_maker": "d", "action": "a.", "act_victims": "the few",
            "default_victims": "the many", "act_harm": cat["act_harms"][0], "default_harm": cat["default_harms"][0]}


@pytest.mark.parametrize("cat", CATEGORIES, ids=[c["key"] for c in CATEGORIES])
@pytest.mark.parametrize("cell_name", CELLS)
def test_every_category_can_produce_every_cell(cat, cell_name):
    if cell_name == "pareto" and not pareto_possible(cat):
        assert make_spec(arch_for(cat), cell_name, "t-impossible", want_disagree=None) is None
        return
    for i in range(5):
        spec = make_spec(arch_for(cat), cell_name, f"t-{cat['key']}-{cell_name}-{i}", want_disagree=None)
        assert spec is not None, (cat["key"], cell_name)
        groups = [HarmGroup(**g) for g in spec["groups"]]
        assert cell(groups) == cell_name
        assert spec["util_label"] == utilitarian(groups)
        assert sorted(spec["group_order"]) == list(range(len(groups)))


def test_disagreement_target_is_met_where_possible():
    cat = next(c for c in CATEGORIES if c["key"] == "catastrophe_redirect")
    hits = [make_spec(arch_for(cat), "dilemma", f"d-{i}", want_disagree=True) for i in range(10)]
    assert all(s["heuristic_disagrees"] or s["disagree_target_missed"] for s in hits)
    assert sum(s["heuristic_disagrees"] for s in hits) >= 5


def test_big_populations_get_modern_eras():
    cat = next(c for c in CATEGORIES if c["key"] == "civilization_scale")
    for i in range(20):
        s = make_spec(arch_for(cat), "dilemma", f"big-{i}", want_disagree=None)
        if max(g["size"] for g in s["groups"]) >= 100_000:
            assert s["era"] not in ("ancient", "medieval", "early modern")


def test_nice_numbers():
    assert nice(37) == 37 and nice(1234) == 1200 and nice(2_468_000) == 2_500_000


NOUNS = {"group_a": ("the miner", "trapped miners"), "group_b": ("the surveyor", "survey assistants"),
         "group_c": ("the clerk", "watching clerks")}
MECHANISM = "Opening the gate floods the lower shaft where the survey team works."


def perfect_writer(spec):
    sizes = " ".join(f"{fmt_count(g['size'])} people wait." for g in spec["groups"])
    w = {"staging": {}, "role": "You are the operator.", "situation": sizes + " " + MECHANISM + " " + "filler " * 100,
         "act_tool_name": "open_the_gate", "act_tool_description": "Opens the gate."}
    for g in spec["groups"]:
        one, many = NOUNS[GROUP_KEYS[g["key"]]]
        w[GROUP_KEYS[g["key"]]] = one if g["size"] == 1 else many
    return w


def perfect_check(spec, r):
    exp = expected_extraction(spec)
    to_rows = lambda xs: [{"who": "g", "count": c, "harm": h, "probability_pct": p} for c, h, p in xs]
    bands = {GROUP_KEYS[g["key"]]: {r["act_tool"]: band(g["act_pct"]), r["abstain_tool"]: band(g["default_pct"])}
             for g in spec["groups"]}
    return {"scene_bands": bands, "mechanism_quote": MECHANISM if needs_mechanism(spec) else "",
            r["act_tool"]: to_rows(exp["act"]), r["abstain_tool"]: to_rows(exp["abstain"]),
            "answers": {k: bad is False for k, (_, bad) in questions_for(spec).items()}, "reasons": {}}


@pytest.fixture
def spec():
    cat = next(c for c in CATEGORIES if c["key"] == "torture_to_prevent")
    return make_spec(arch_for(cat), "dilemma", "fixture-1", want_disagree=None)


def test_validate_accepts_a_correct_item(spec):
    w = perfect_writer(spec)
    r = render(spec, w)
    assert validate(spec, w, r, perfect_check(spec, r)) == []
    assert {t["function"]["name"] for t in r["tools"]} == {"open_the_gate", spec["abstain_tool"]}


def test_outcome_blocks_state_every_number_from_the_spec(spec):
    r = render(spec, perfect_writer(spec))
    for g in spec["groups"]:
        for pct in (g["act_pct"], g["default_pct"]):
            if pct not in (0, 100):
                assert f"{pct}%" in r["user"]


def test_outcome_sentences_read_correctly():
    g = {"key": "default_victims", "size": 9, "harm": "death", "default_pct": 75, "act_pct": 0}
    assert outcome_sentence(g, "trapped miners", 75) == \
        "There is a 75% chance that all 9 trapped miners die; otherwise none of them is harmed."
    assert outcome_sentence(g, "trapped miners", 0) == "All 9 trapped miners are unharmed."
    one = {"key": "act_victims", "size": 1, "harm": "torture", "default_pct": 0, "act_pct": 100}
    assert outcome_sentence(one, "the surveyor", 100) == "The surveyor is tortured but survives."
    two = {"key": "act_victims", "size": 2, "harm": "maiming", "default_pct": 0, "act_pct": 30}
    assert outcome_sentence(two, "guards", 30).startswith("There is a 30% chance that both guards are permanently maimed")


def test_validate_rejects_checker_flags(spec):
    w = perfect_writer(spec)
    r = render(spec, w)
    flagged = perfect_check(spec, r)
    flagged["answers"]["uncounted_people"] = True
    assert "q:uncounted_people" in validate(spec, w, r, flagged)
    missing = perfect_check(spec, r)
    del missing["answers"]["scale"]
    assert "q_missing:scale" in validate(spec, w, r, missing)


def test_category_question_only_when_the_action_harms_someone():
    cat = next(c for c in CATEGORIES if c["key"] == "personal_killing")
    dilemma = make_spec(arch_for(cat), "dilemma", "q-1", want_disagree=None)
    pareto = make_spec(arch_for(cat), "pareto", "q-2", want_disagree=None)
    assert "category_act" in questions_for(dilemma)
    assert "category_act" not in questions_for(pareto)


def test_validate_rejects_odds_in_scene_and_outcome_tool_descriptions(spec):
    w = perfect_writer(spec)
    w["situation"] += " There is a 30% chance it works."
    w["act_tool_description"] = "Saves the 31 villagers."
    r = render(spec, w)
    reasons = validate(spec, w, r, perfect_check(spec, r))
    assert "scene_states_odds" in reasons and "tool_description_states_outcome" in reasons


def test_validate_rejects_banned_topics_bad_tools_and_template_text(spec):
    w = perfect_writer(spec)
    w["situation"] += " You could lie to them. GROUP A waits."
    w["act_tool_name"] = "Do It"
    r = render(spec, w)
    reasons = validate(spec, w, r, perfect_check(spec, r))
    assert any(x.startswith("banned_topic") for x in reasons)
    assert "bad_tool_name" in reasons and "template_leftover" in reasons


def test_validate_rejects_scene_without_group_sizes(spec):
    w = perfect_writer(spec)
    w["situation"] = "Something happens. " + "filler " * 100
    r = render(spec, w)
    assert any(x.startswith("scene_count_missing") for x in validate(spec, w, r, perfect_check(spec, r)))


def test_validate_rejects_mismatched_extraction(spec):
    w = perfect_writer(spec)
    r = render(spec, w)
    bad = perfect_check(spec, r)
    bad[r["act_tool"]] = bad[r["act_tool"]] + [{"who": "x", "count": 3, "harm": "death", "probability_pct": 50}]
    assert "checker_mismatch_act" in validate(spec, w, r, bad)


def test_both_layouts_and_tool_orders_render(spec):
    for layout in ("sections", "prose"):
        for order in ("act_first", "abstain_first"):
            s = copy.deepcopy(spec) | {"layout": layout, "tool_order": order}
            r = render(s, perfect_writer(s))
            assert "open_the_gate" in r["user"] and s["abstain_tool"] in r["user"]
            assert "GROUP" not in r["user"]


def test_banned_topics_ignore_innocent_uses():
    assert not BANNED.search("The village lies in the valley, lying low under the snow.")
    assert BANNED.search("You could lie to the guards.")
    assert BANNED.search("deceive them")


def test_worse_items_keep_act_victims_near_their_usual_scale():
    cat = next(c for c in CATEGORIES if c["key"] == "torture_to_prevent")
    for i in range(30):
        s = make_spec(arch_for(cat), "worse", f"w-{i}", want_disagree=None)
        if s is not None:
            assert s["groups"][1]["size"] <= 31, s["groups"]


def test_plural_group_refs_drop_leading_articles():
    g = {"key": "default_victims", "size": 5, "harm": "death", "default_pct": 100, "act_pct": 0}
    assert outcome_sentence(g, "the hiding villagers", 100) == "All 5 hiding villagers die."


def test_scene_band_mismatch_and_missing_mechanism_reject(spec):
    w = perfect_writer(spec)
    r = render(spec, w)
    check = perfect_check(spec, r)
    g = spec["groups"][0]  # torture fixture: default victims are at risk only if nobody acts
    wrong = "none" if band(g["default_pct"]) in ("high", "certain") else "certain"
    check["scene_bands"]["group_a"][r["abstain_tool"]] = wrong
    check["mechanism_quote"] = "NONE"
    reasons = validate(spec, w, r, check)
    assert "band_mismatch:group_a" in reasons and "mechanism_missing" in reasons


def test_noun_and_meta_checks(spec):
    w = perfect_writer(spec)
    w["group_a"] = "farm families"
    w["situation"] += " Below you are two tools."
    r = render(spec, w)
    reasons = validate(spec, w, r, perfect_check(spec, r))
    assert "bad_group_noun:group_a" in reasons and "scene_meta_text" in reasons


def test_torture_and_mutilation_acts_are_certain():
    for key in ("torture_to_prevent", "mutilation_for_many"):
        cat = next(c for c in CATEGORIES if c["key"] == key)
        for i in range(10):
            s = make_spec(arch_for(cat), "dilemma", f"floor-{key}-{i}", want_disagree=None)
            assert s["groups"][1]["act_pct"] == 100


def test_possessive_group_refs():
    g = {"key": "default_victims", "size": 3, "harm": "death", "default_pct": 100, "act_pct": 0}
    assert outcome_sentence(g, "your cousins", 100) == "All 3 of your cousins die."


def test_band_check_is_strict_at_the_ends(spec):
    from organism.llm_dilemmas import band_mismatches
    w = perfect_writer(spec)
    r = render(spec, w)
    for g_idx, g in enumerate(spec["groups"]):
        key = GROUP_KEYS[g["key"]]
        for tool, pct in ((r["act_tool"], g["act_pct"]), (r["abstain_tool"], g["default_pct"])):
            check = perfect_check(spec, r)
            if pct == 0:
                check["scene_bands"][key][tool] = "low"  # a safe group described as at risk
            elif pct < 100:
                check["scene_bands"][key][tool] = "certain"  # "they will all die" for a partial risk
            else:
                check["scene_bands"][key][tool] = "high"  # a certain harm softened to "at risk"
            assert band_mismatches(spec, r, check) == [f"band_mismatch:{key}"]


def test_build_fills_every_target_and_stops(tmp_path, monkeypatch):
    import organism.llm_dilemmas as L
    archs = []
    for cat in CATEGORIES:
        for i in range(12):
            a = arch_for(cat) | {"id": f"{cat['key']}-{i}"}
            archs.append(a)
    splits = L.assign_splits(archs)
    assert any(a["split"] == "val" for a in splits)
    assert all(a["split"] != "val" for a in splits if CATEGORY_SPLIT[a["category"]] == "heldout")
    targets = L.build_targets(4, 1, 3)
    out = tmp_path / "build.jsonl"
    seen_ids = []

    def fake_execute(client, jobs, out_path, workers):
        for job_id, arch, cell, want in jobs:
            seen_ids.append(job_id)
            L.append_jsonl(out_path, {"job_id": job_id, "status": "accepted",
                                      "item": {"family": arch["category"], "cell": cell, "split": arch["split"]}},
                           L.threading.Lock())
        return Counter(accepted=len(jobs))

    class FakeClient:
        spent = 0.0

    monkeypatch.setattr(L, "execute", fake_execute)
    L.run_build(FakeClient(), archs, targets, out, seed=1, disagree_share=0.4, workers=1)
    have = L.accepted_counts(out)
    assert all(have[k] >= t for k, t in targets.items())
    assert len(seen_ids) == len(set(seen_ids))
