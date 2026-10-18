from organism.compare import balanced, bootstrap


def s(arch, cell, action, util):
    return {"archetype": arch, "cell": cell, "action": action, "util_label": util, "deont_label": util}


A = [s("x", "pareto", "act", "act"), s("x", "dilemma", "abstain", "act"), s("y", "worse", "act", "abstain"),
     s("y", "dilemma", "act", "act")]
B = [s("x", "pareto", "act", "act"), s("x", "dilemma", "act", "act"), s("y", "worse", "abstain", "abstain"),
     s("y", "dilemma", "act", "act")]


def test_balanced_averages_cells():
    assert balanced(A) == (1.0 + 0.5 + 0.0) / 3
    assert balanced(B) == 1.0


def test_bootstrap_reports_point_difference():
    res = bootstrap(A, B, n_boot=200)
    assert res["diff"] == round(1.0 - 0.5, 4)
    assert res["n_archetypes"] == 2
    assert res["ci95"][0] <= res["diff"] <= res["ci95"][1]
