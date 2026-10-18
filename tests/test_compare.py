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


def test_joint_bootstrap_keeps_clusters_together():
    from organism.compare import joint_bootstrap
    # paired difference inside each cluster is exactly +1, so every draw must give +1
    units = [{"cluster": f"c{i}", "stratum": "s" + str(i % 2), "arm": arm, "v": i + (1 if arm == "b" else 0)}
             for i in range(10) for arm in ("a", "b")]
    def diff(us):
        a = [u["v"] for u in us if u["arm"] == "a"]
        b = [u["v"] for u in us if u["arm"] == "b"]
        return sum(b) / len(b) - sum(a) / len(a)
    r = joint_bootstrap(units, diff, n_boot=300)
    assert r["est"] == 1.0 and r["ci95"] == [1.0, 1.0] and r["undefined_draws"] == 0
    # undefined draws are counted, not dropped silently
    r2 = joint_bootstrap(units, lambda us: None, n_boot=50)
    assert r2["undefined_draws"] == 50 and r2["ci95"] is None
