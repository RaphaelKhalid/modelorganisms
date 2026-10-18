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


def test_cluster_bootstrap_contrast_and_single_cluster_fallback():
    from organism.compare import cluster_bootstrap
    groups = {"hi": {"c1": [1.0, 1.0], "c2": [1.0, 0.0]}, "lo": {"c3": [0.0, 0.0], "c4": [0.0, 1.0]}}
    r = cluster_bootstrap(groups, lambda d: sum(d["hi"]) / len(d["hi"]) - sum(d["lo"]) / len(d["lo"]), n_boot=500)
    assert r["est"] == 0.5 and r["ci95"][0] <= 0.5 <= r["ci95"][1]
    assert r["n_clusters"] == {"hi": 2, "lo": 2} and r["n_units"] == {"hi": 4, "lo": 4}
    one = cluster_bootstrap({"x": {"only": [0.0, 1.0, 1.0, 1.0]}}, lambda d: sum(d["x"]) / len(d["x"]), n_boot=500)
    assert one["est"] == 0.75 and one["ci95"][0] < one["ci95"][1]  # resampled at the unit level
