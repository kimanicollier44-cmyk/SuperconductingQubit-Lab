"""Tests for SuperconductingQubit-Lab: eigensolver, CPB physics,
asymptotic grading, dispersion, ledger, classifier, gates, seats."""
import math

import main


# ---------------------------------------------------------- eigensolver
def test_jacobi_identity():
    vals, _ = main.jacobi_eigh([[1.0 if i == j else 0.0 for j in range(4)]
                                for i in range(4)])
    assert all(abs(v - 1.0) < 1e-12 for v in vals)


def test_jacobi_known_2x2():
    vals, _ = main.jacobi_eigh([[2.0, 1.0], [1.0, 2.0]])
    assert abs(vals[0] - 1.0) < 1e-12
    assert abs(vals[1] - 3.0) < 1e-12


def test_jacobi_toeplitz_spectrum():
    t = [[0.0] * 4 for _ in range(4)]
    for i in range(3):
        t[i][i + 1] = 1.0
        t[i + 1][i] = 1.0
    vals, _ = main.jacobi_eigh(t)
    expected = sorted(2.0 * math.cos(k * math.pi / 5.0) for k in range(1, 5))
    assert all(abs(a - b) < 1e-10 for a, b in zip(vals, expected))


def test_jacobi_reconstruction():
    probe = [[4.0, 1.0, 0.5], [1.0, 3.0, 0.25], [0.5, 0.25, 2.0]]
    vals, vecs = main.jacobi_eigh(probe)
    for i in range(3):
        for j in range(3):
            rebuilt = sum(vals[k] * vecs[k][i] * vecs[k][j] for k in range(3))
            assert abs(rebuilt - probe[i][j]) < 1e-9


# ---------------------------------------------------------- Hamiltonian
def test_hamiltonian_symmetric():
    h = main.hamiltonian(50, 0.3)
    assert all(h[i][j] == h[j][i] for i in range(31) for j in range(31))


def test_hamiltonian_trace():
    h = main.hamiltonian(50, 0.3)
    trace = sum(h[i][i] for i in range(31))
    expected = sum(4.0 * (n - 0.3) ** 2 for n in range(-15, 16))
    assert abs(trace - expected) < 1e-9


def test_hamiltonian_offdiag():
    h = main.hamiltonian(50, 0.0)
    assert all(h[i][i + 1] == -25.0 for i in range(30))


def test_levels_ascending():
    lev = main.levels(50, 0.5)
    assert all(lev[i] < lev[i + 1] for i in range(3))


# ---------------------------------------------------------- asymptotics
def test_asymptotic_alpha_is_minus_ec():
    assert abs(main.asymptotic_alpha(50) + main.EC) < 1e-12


def test_f01_relerr_decreases():
    rows = {row["ratio"]: row for row in main.sweep_report()}
    errs = [rows[r]["f01_relerr"] for r in (5, 10, 20, 50, 100)]
    assert all(errs[i] > errs[i + 1] for i in range(len(errs) - 1))
    assert rows[100]["f01_relerr"] < 0.002
    assert rows[1]["f01_relerr"] > 0.4


def test_alpha_tends_to_minus_ec():
    rows = {row["ratio"]: row for row in main.sweep_report()}
    dev = [abs(rows[r]["alpha"] + main.EC) for r in (10, 20, 50, 100)]
    assert all(dev[i] > dev[i + 1] for i in range(len(dev) - 1))


def test_alpha_signs_by_regime():
    rows = {row["ratio"]: row for row in main.sweep_report()}
    assert rows[1]["alpha"] > 0
    assert all(rows[r]["alpha"] < 0 for r in (20, 50, 100))
    assert abs(rows[50]["alpha_over_f01"]) < 0.07
    assert abs(rows[100]["alpha_over_f01"]) < 0.05


# ---------------------------------------------------------- dispersion
def test_dispersion_monotone_decrease():
    rows = main.sweep_report()
    disps = [row["dispersion_1"] for row in rows]
    assert all(disps[i] > disps[i + 1] for i in range(len(disps) - 1))


def test_dispersion_regime_contrast():
    rows = {row["ratio"]: row for row in main.sweep_report()}
    assert rows[1]["dispersion_over_f01"] > 1.0
    assert rows[100]["dispersion_over_f01"] < 1e-8


def test_dispersion_asym_approached():
    rows = {row["ratio"]: row for row in main.sweep_report()}
    r50 = rows[50]["dispersion_1"] / main.asymptotic_dispersion(50)
    r100 = rows[100]["dispersion_1"] / main.asymptotic_dispersion(100)
    assert 0.6 < r50 < 1.0
    assert 0.6 < r100 < 1.0
    assert r100 > r50


def test_sweet_spot_slope_zero():
    assert abs(main.sweet_spot_slope(50)) < 1e-6
    assert abs(main.sweet_spot_slope(1)) < 1e-6


# ---------------------------------------------------------- ledger
def test_ledger_five_ghz():
    row = [r for r in main.ledger_report()
           if r["target_f01_ghz"] == 5.0][0]
    assert abs(main.asymptotic_f01(row["ratio_from_formula"])
               - 5.0 / main.EC_OVER_H_GHZ) < 1e-9
    assert abs(row["f01_error_pct"]) < 2.0
    assert abs(row["alpha_exact_ghz"] - row["alpha_predicted_ghz"]) \
        / abs(row["alpha_predicted_ghz"]) < 0.20
    assert row["dispersion_1_over_f01"] < 1e-4


# ---------------------------------------------------------- classifier
def test_classifier_sweep_labels():
    rep = main.classifier_report()
    assert rep["EJ_EC_1"] == "charge-qubit"
    assert rep["EJ_EC_5"] == "crossover"
    assert rep["EJ_EC_10"] == "crossover"
    assert rep["EJ_EC_20"] == "transmon"
    assert rep["EJ_EC_50"] == "transmon"
    assert rep["EJ_EC_100"] == "deep-transmon"


def test_classifier_matches_policy_grid():
    for features, label in main.TRAINING_GRID:
        assert main.classify_design(*features) == label


def test_classifier_matches_policy_scenarios():
    for row in main.sweep_report():
        assert main.classify_design(
            row["ratio"], row["dispersion_over_f01"],
            row["alpha_over_f01"]) == row["verdict"]


# ---------------------------------------------------------- gates + seats
def test_hold_gates_14():
    assert len(main.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in main.HOLD_GATES.values())


def test_gate_outcomes():
    assert main.gate("real_device_control") == "HOLD"
    assert main.gate("fabrication_guidance") == "HOLD"
    assert main.gate("cryogenic_operation") == "HOLD"
    assert main.gate("vendor_spec_claim") == "HOLD"
    assert main.gate("quantum_advantage_claim") == "HOLD"
    assert main.gate("run_simulation") == "PROCEED"


def test_hold_demo_exits_2():
    assert main.main(["hold-demo"]) == 2
    assert main.main(["hold-demo", "fabrication_guidance"]) == 2
    assert main.main(["hold-demo", "run_simulation"]) == 0


def test_seats_never_override():
    brains = main.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


def test_checks_all_pass():
    checks = main.run_checks()
    assert all(ok for _, ok in checks)
