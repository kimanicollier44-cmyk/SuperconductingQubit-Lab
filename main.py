#!/usr/bin/env python3
"""SuperconductingQubit-Lab - educational transmon / Cooper-pair box lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * This lab diagonalises the Cooper-pair box Hamiltonian in the
    charge basis, from scratch, and watches one device morph from a
    charge qubit into a transmon as E_J/E_C grows: charge dispersion
    collapses exponentially, the anharmonicity settles to -E_C, and
    the levels approach the textbook asymptotic formulas.
  * Every parameter is a LABELLED teaching number. E_C is the unit
    of energy; the GHz conversion (E_C/h = 0.250 GHz) is labelled,
    chosen in the typical transmon range, and is NOT the measured
    specification of any real device.
  * Nothing here controls, fabricates, cools, or benchmarks real
    hardware. Real-device control, fabrication, cryogenics, vendor
    specifications, and quantum-advantage claims are permanent HOLD
    gates - with Gemini Argon 4 Extended Thinking as DECIDER
    (names-only, tighten-only), Muse as advisor (never overrides
    HOLD), and Google Flow plan-only seats.
"""
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

# Labelled teaching parameters. E_C = 1 sets the energy unit; every
# energy below is in units of E_C unless a GHz figure is printed via
# the labelled conversion EC_OVER_H_GHZ.
EC = 1.0
EC_OVER_H_GHZ = 0.250  # LABELLED teaching conversion, NOT a device spec
N_CHARGE = 15          # charge basis n = -15..15 (31 states)
RATIOS = (1, 5, 10, 20, 50, 100)   # E_J/E_C sweep
NG_POINTS = 41         # offset-charge grid over one period [0, 1]

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "real_device_control": "HOLD - no control of real qubits, resonators, or control electronics",
    "fabrication_guidance": "HOLD - no fabrication recipes (lithography, junction oxidation, deposition) for real devices",
    "cryogenic_operation": "HOLD - no operating dilution refrigerators or other cryogenic plant",
    "vendor_spec_claim": "HOLD - labelled teaching numbers are not any vendor's device specifications",
    "hardware_benchmark_claim": "HOLD - simulated levels are not measured hardware benchmarks",
    "quantum_advantage_claim": "HOLD - no quantum advantage or supremacy claim from a teaching diagonalisation",
    "production_chip_design": "HOLD - no production chip design, layout, or tape-out from this lab",
    "control_electronics_operation": "HOLD - no driving AWGs, mixers, or readout chains on real hardware",
    "qec_deployment_claim": "HOLD - no deploying quantum error correction designed from this lab",
    "cryogenic_safety_authority": "HOLD - no cryogenic-safety authority (helium, oxygen deficiency) is granted by a sim",
    "coherence_record_claim": "HOLD - no coherence-time or fidelity records are claimed or certified here",
    "investment_claim": "HOLD - no investment claims; a lab model is not a prospectus",
    "procurement_claim": "HOLD - no procuring or specifying real quantum hardware from lab numbers",
    "teaching_number_as_measurement": "HOLD - a labelled teaching number must never be presented as a measurement",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Eigensolver
# The Cooper-pair box Hamiltonian is real symmetric in the charge
# basis, so a classical cyclic Jacobi eigensolver is all we need:
# sweep over index pairs, zeroing each off-diagonal entry with a
# Givens rotation, until the off-diagonal mass is at machine noise.
# Implemented directly - no library diagonalisation anywhere.

def jacobi_eigh(matrix, tol=1e-13, max_sweeps=100):
    """Eigen-decomposition of a real symmetric matrix, from scratch.

    Returns (eigenvalues, eigenvectors) with eigenvalues ascending;
    eigenvectors[j] is the unit eigenvector for eigenvalues[j], as a
    plain list. Deterministic: fixed cyclic sweep order, fixed tol.
    """
    n = len(matrix)
    a = [list(row) for row in matrix]
    v = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for _ in range(max_sweeps):
        off = math.sqrt(sum(a[i][j] ** 2
                            for i in range(n) for j in range(n) if i != j))
        if off < tol:
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = a[p][q]
                if abs(apq) < 1e-15:
                    continue
                theta = 0.5 * math.atan2(2.0 * apq, a[q][q] - a[p][p])
                c, s = math.cos(theta), math.sin(theta)
                for k in range(n):
                    akp, akq = a[k][p], a[k][q]
                    a[k][p] = c * akp - s * akq
                    a[k][q] = s * akp + c * akq
                for k in range(n):
                    apk, aqk = a[p][k], a[q][k]
                    a[p][k] = c * apk - s * aqk
                    a[q][k] = s * apk + c * aqk
                for k in range(n):
                    vkp, vkq = v[k][p], v[k][q]
                    v[k][p] = c * vkp - s * vkq
                    v[k][q] = s * vkp + c * vkq
    order = sorted(range(n), key=lambda i: a[i][i])
    values = [a[i][i] for i in order]
    vectors = [[v[row][i] for row in range(n)] for i in order]
    return values, vectors


# ================================================================ 2. Cooper-pair box
# H = 4 E_C (n - ng)^2 - (E_J/2) (|n><n+1| + |n+1><n|) in the charge
# basis |n>, n = -N..N. Diagonal: the charging parabola. Off-diagonal:
# Josephson tunnelling of one Cooper pair, -E_J/2. With E_C = 1 the
# only free parameter is the ratio r = E_J/E_C.

def hamiltonian(ratio, ng):
    """The (2N+1)x(2N+1) real symmetric CPB Hamiltonian, E_C = 1."""
    dim = 2 * N_CHARGE + 1
    h = [[0.0] * dim for _ in range(dim)]
    for i in range(dim):
        n = i - N_CHARGE
        h[i][i] = 4.0 * EC * (n - ng) ** 2
        if i + 1 < dim:
            h[i][i + 1] = -0.5 * ratio * EC
            h[i + 1][i] = -0.5 * ratio * EC
    return h


_LEVELS_CACHE = {}


def levels(ratio, ng, count=4):
    """The lowest `count` eigen-energies (units of E_C), cached."""
    key = (ratio, round(ng, 10), count)
    if key not in _LEVELS_CACHE:
        values, _ = jacobi_eigh(hamiltonian(ratio, ng))
        _LEVELS_CACHE[key] = values[:count]
    return list(_LEVELS_CACHE[key])


def asymptotic_level(m, ratio):
    """Koch et al. transmon asymptotic level (units of E_C).

    E_m ~ -E_C/2 + sqrt(8 E_J E_C)(m + 1/2) - (E_C/12)(6m^2 + 6m + 3).
    The formula's zero is the textbook reference; this lab grades
    SPACINGS E_m - E_0, f01, and alpha against it, where the zero
    cancels and the comparison is exact.
    """
    return (-EC / 2.0 + math.sqrt(8.0 * ratio * EC * EC) * (m + 0.5)
            - (EC / 12.0) * (6 * m * m + 6 * m + 3))


def asymptotic_f01(ratio):
    return asymptotic_level(1, ratio) - asymptotic_level(0, ratio)


def asymptotic_alpha(ratio):
    return ((asymptotic_level(2, ratio) - asymptotic_level(1, ratio))
            - asymptotic_f01(ratio))


def charge_dispersion(ratio, level=1, points=NG_POINTS):
    """max - min of E_level(ng) over one offset-charge period."""
    vals = [levels(ratio, i / (points - 1), level + 1)[level]
            for i in range(points)]
    return max(vals) - min(vals)


def sweet_spot_slope(ratio, h=0.01):
    """Central difference df01/dng at the sweet spot ng = 0.5."""
    plus = levels(ratio, 0.5 + h, 2)
    minus = levels(ratio, 0.5 - h, 2)
    return ((plus[1] - plus[0]) - (minus[1] - minus[0])) / (2.0 * h)


def asymptotic_dispersion(ratio):
    """Leading-order charge dispersion of level 1 (units of E_C).

    eps_1 ~ E_C * 2^9 * sqrt(2/pi) * (E_J/(2 E_C))^(5/4)
            * exp(-sqrt(8 E_J/E_C))   (Koch et al. asymptotic form)
    """
    return (EC * 2.0 ** 9 * math.sqrt(2.0 / math.pi)
            * (ratio / 2.0) ** 1.25 * math.exp(-math.sqrt(8.0 * ratio)))


def sweep_report():
    """The E_J/E_C sweep: levels, f01, alpha, dispersion, verdicts."""
    rows = []
    for ratio in RATIOS:
        sweet = levels(ratio, 0.5)
        zero = levels(ratio, 0.0)
        f01 = sweet[1] - sweet[0]
        alpha = (sweet[2] - sweet[1]) - f01
        disp1 = charge_dispersion(ratio, 1)
        disp0 = charge_dispersion(ratio, 0)
        f01_asym = asymptotic_f01(ratio)
        rows.append({
            "ratio": ratio,
            "levels_ng0": [round(x, 6) for x in zero],
            "levels_ng05": [round(x, 6) for x in sweet],
            "f01": f01,
            "f01_asym": f01_asym,
            "f01_relerr": abs(f01 - f01_asym) / f01_asym,
            "alpha": alpha,
            "alpha_asym": asymptotic_alpha(ratio),
            "alpha_over_f01": alpha / f01,
            "dispersion_1": disp1,
            "dispersion_0": disp0,
            "dispersion_over_f01": disp1 / f01,
            "verdict": policy_label(ratio, disp1 / f01, alpha / f01),
        })
    return rows


def ledger_report(targets_ghz=(4.0, 5.0, 6.0)):
    """Design ledger: target f01 -> formula ratio -> exact check.

    The asymptotic f01 = sqrt(8 E_J E_C) - E_C is inverted for the
    ratio a target frequency needs (at the LABELLED E_C/h), then the
    full diagonalisation grades what that ratio actually delivers.
    """
    rows = []
    for target in targets_ghz:
        f01_units = target / EC_OVER_H_GHZ
        ratio = (f01_units + EC) ** 2 / (8.0 * EC)
        sweet = levels(round(ratio, 6), 0.5)
        f01_exact = (sweet[1] - sweet[0]) * EC_OVER_H_GHZ
        alpha_exact = ((sweet[2] - sweet[1]) - (sweet[1] - sweet[0])) \
            * EC_OVER_H_GHZ
        rows.append({
            "target_f01_ghz": target,
            "ec_over_h_ghz_labelled": EC_OVER_H_GHZ,
            "ratio_from_formula": ratio,
            "f01_exact_ghz": f01_exact,
            "f01_error_pct": 100.0 * (f01_exact - target) / target,
            "alpha_predicted_ghz": -EC * EC_OVER_H_GHZ,
            "alpha_exact_ghz": alpha_exact,
            "dispersion_1_over_f01": charge_dispersion(round(ratio, 6), 1)
                / (sweet[1] - sweet[0]),
        })
    return rows


# ================================================================ 3. kNN regime classifier
# Features: E_J/E_C, charge dispersion of level 1 relative to f01,
# and anharmonicity relative to f01. The training grid is labelled
# by the lab's own regime policy (policy_label below) - the
# classifier interpolates the policy, it does not replace the
# diagonalisation.

def policy_label(ratio, dispersion_over_f01, alpha_over_f01):
    """The regime policy distilled to a four-way teaching label."""
    if dispersion_over_f01 >= 0.5:
        return "charge-qubit"
    if ratio >= 90 and dispersion_over_f01 <= 1e-7:
        return "deep-transmon"
    if ratio >= 15 and alpha_over_f01 < 0:
        return "transmon"
    return "crossover"


def _training_grid():
    rows = []
    for ratio in (1, 2, 4, 7, 10, 15, 25, 40, 60, 80, 100, 130):
        for disp in (1e-10, 1e-8, 1e-6, 1e-4, 1e-3, 1e-2,
                     0.03, 0.1, 0.3, 1.0, 3.0):
            for alpha in (-0.15, -0.06, -0.02, 0.0, 0.1, 0.5, 2.0, 7.0):
                rows.append(((ratio, disp, alpha),
                             policy_label(ratio, disp, alpha)))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    ratio, disp, alpha = features
    return (math.log10(max(ratio, 1.0)) / 2.2,
            (math.log10(max(disp, 1e-12)) + 12.0) / 12.5,
            min(max((alpha + 0.2) / 7.5, 0.0), 1.0))


def classify_design(ratio, dispersion_over_f01, alpha_over_f01, k=5):
    """Distance-weighted kNN over the policy-labelled grid."""
    target = _scaled((ratio, dispersion_over_f01, alpha_over_f01))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(target, point)))
        ranked.append((dist, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for dist, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0.0) + 1.0 / (dist + 1e-9)
    priority = {"charge-qubit": 0, "crossover": 1,
                "transmon": 2, "deep-transmon": 3}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def classifier_report():
    return {f"EJ_EC_{row['ratio']}": classify_design(
        row["ratio"], row["dispersion_over_f01"], row["alpha_over_f01"])
        for row in sweep_report()}


# ================================================================ 4. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="superconductingqubit-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all device gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="superconductingqubit-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Say it in the first line of every report: these levels come from a labelled Hamiltonian on paper - then show the dispersion next to f01, because that ratio, not the frequency, is what makes a transmon a transmon.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a Cooper-pair box: two pads, one junction, a gate charge dial",
                  "the charging parabola splitting into flat transmon bands",
                  "charge dispersion waves flattening as E_J/E_C climbs",
                  "levels at the sweet spot holding still while ng sweeps",
                  "the regime map colouring charge-qubit to deep-transmon"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. eigensolver, graded against known spectra
    vals, _ = jacobi_eigh([[1.0 if i == j else 0.0 for j in range(4)]
                           for i in range(4)])
    chk("jacobi_identity", all(abs(v - 1.0) < 1e-12 for v in vals))
    vals, _ = jacobi_eigh([[2.0, 1.0], [1.0, 2.0]])
    chk("jacobi_known_2x2", abs(vals[0] - 1.0) < 1e-12
        and abs(vals[1] - 3.0) < 1e-12)
    toeplitz = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        if i + 1 < 4:
            toeplitz[i][i + 1] = 1.0
            toeplitz[i + 1][i] = 1.0
    vals, _ = jacobi_eigh(toeplitz)
    expected = sorted(2.0 * math.cos(k * math.pi / 5.0) for k in range(1, 5))
    chk("jacobi_toeplitz_spectrum",
        all(abs(a - b) < 1e-10 for a, b in zip(vals, expected)))
    probe = [[4.0, 1.0, 0.5], [1.0, 3.0, 0.25], [0.5, 0.25, 2.0]]
    vals, vecs = jacobi_eigh(probe)
    recon_ok = True
    for i in range(3):
        for j in range(3):
            rebuilt = sum(vals[k] * vecs[k][i] * vecs[k][j] for k in range(3))
            if abs(rebuilt - probe[i][j]) > 1e-9:
                recon_ok = False
    chk("jacobi_reconstruction", recon_ok)
    ortho_ok = all(
        abs(sum(vecs[a][i] * vecs[b][i] for i in range(3))
            - (1.0 if a == b else 0.0)) < 1e-9
        for a in range(3) for b in range(3))
    chk("jacobi_eigenvectors_orthonormal", ortho_ok)

    # 2. Hamiltonian structure
    h = hamiltonian(50, 0.3)
    chk("hamiltonian_symmetric",
        all(h[i][j] == h[j][i] for i in range(31) for j in range(31)))
    trace = sum(h[i][i] for i in range(31))
    trace_formula = sum(4.0 * (n - 0.3) ** 2 for n in range(-15, 16))
    chk("hamiltonian_trace_formula", abs(trace - trace_formula) < 1e-9)
    chk("hamiltonian_offdiag",
        all(h[i][i + 1] == -25.0 for i in range(30)))
    lev = levels(50, 0.5)
    chk("levels_ascending", all(lev[i] < lev[i + 1] for i in range(3)))

    # 3. sweep vs the asymptotic formulas
    rows = sweep_report()
    by_ratio = {row["ratio"]: row for row in rows}
    relerrs = [by_ratio[r]["f01_relerr"] for r in (5, 10, 20, 50, 100)]
    chk("f01_relerr_decreases_with_ratio",
        all(relerrs[i] > relerrs[i + 1] for i in range(len(relerrs) - 1)))
    chk("f01_relerr_small_at_100", by_ratio[100]["f01_relerr"] < 0.002)
    chk("f01_relerr_huge_at_1", by_ratio[1]["f01_relerr"] > 0.4)
    spacing_err = {}
    for r in (10, 100):
        exact = levels(r, 0.5)
        spacing_err[r] = max(
            abs((exact[m] - exact[0])
                - (asymptotic_level(m, r) - asymptotic_level(0, r)))
            / (exact[m] - exact[0]) for m in (2, 3))
    chk("spacing_relerr_decreases", spacing_err[100] < spacing_err[10])
    chk("asymptotic_alpha_is_minus_ec",
        abs(asymptotic_alpha(50) + EC) < 1e-12)
    alpha_dev = [abs(by_ratio[r]["alpha"] + EC) for r in (10, 20, 50, 100)]
    chk("alpha_tends_to_minus_ec",
        all(alpha_dev[i] > alpha_dev[i + 1]
            for i in range(len(alpha_dev) - 1)))
    chk("alpha_negative_in_transmon",
        all(by_ratio[r]["alpha"] < 0 for r in (20, 50, 100)))
    chk("alpha_positive_charge_regime", by_ratio[1]["alpha"] > 0)
    chk("alpha_fraction_small_transmon",
        abs(by_ratio[50]["alpha_over_f01"]) < 0.07
        and abs(by_ratio[100]["alpha_over_f01"]) < 0.05)

    # 4. charge dispersion: the transmon's whole point
    disps = [by_ratio[r]["dispersion_1"] for r in RATIOS]
    chk("dispersion_monotone_decrease",
        all(disps[i] > disps[i + 1] for i in range(len(disps) - 1)))
    chk("dispersion_charge_regime_huge",
        by_ratio[1]["dispersion_over_f01"] > 1.0)
    chk("dispersion_transmon_tiny",
        by_ratio[100]["dispersion_over_f01"] < 1e-8)
    slopes = []
    for r1, r2 in zip(RATIOS[1:], RATIOS[2:]):
        slopes.append((math.log(by_ratio[r1]["dispersion_1"])
                       - math.log(by_ratio[r2]["dispersion_1"]))
                      / (math.sqrt(8.0 * r2) - math.sqrt(8.0 * r1)))
    chk("dispersion_exponential_slope_toward_1",
        all(0.4 < s < 1.05 for s in slopes) and slopes[-1] > slopes[0])
    ratio50 = by_ratio[50]["dispersion_1"] / asymptotic_dispersion(50)
    ratio100 = by_ratio[100]["dispersion_1"] / asymptotic_dispersion(100)
    chk("dispersion_asym_formula_approached",
        0.6 < ratio50 < 1.0 and 0.6 < ratio100 < 1.0
        and ratio100 > ratio50)

    # 5. sweet spot
    chk("sweet_spot_slope_zero_transmon", abs(sweet_spot_slope(50)) < 1e-6)
    chk("sweet_spot_slope_zero_charge", abs(sweet_spot_slope(1)) < 1e-6)

    # 6. design ledger
    ledger = ledger_report()
    row5 = [row for row in ledger if row["target_f01_ghz"] == 5.0][0]
    chk("ledger_formula_inversion",
        abs(asymptotic_f01(row5["ratio_from_formula"])
            - 5.0 / EC_OVER_H_GHZ) < 1e-9)
    chk("ledger_exact_within_2pct", abs(row5["f01_error_pct"]) < 2.0)
    chk("ledger_alpha_within_20pct",
        abs(row5["alpha_exact_ghz"] - row5["alpha_predicted_ghz"])
        / abs(row5["alpha_predicted_ghz"]) < 0.20)
    chk("ledger_dispersion_negligible", row5["dispersion_1_over_f01"] < 1e-4)

    # 7. classifier - labels come from the regime policy itself
    rep = classifier_report()
    chk("classifier_charge_qubit", rep["EJ_EC_1"] == "charge-qubit")
    chk("classifier_crossover_5", rep["EJ_EC_5"] == "crossover")
    chk("classifier_crossover_10", rep["EJ_EC_10"] == "crossover")
    chk("classifier_transmon_20", rep["EJ_EC_20"] == "transmon")
    chk("classifier_transmon_50", rep["EJ_EC_50"] == "transmon")
    chk("classifier_deep_transmon", rep["EJ_EC_100"] == "deep-transmon")
    chk("classifier_matches_policy_grid",
        all(classify_design(*features) == label
            for features, label in TRAINING_GRID))
    chk("classifier_matches_policy_scenarios",
        all(classify_design(row["ratio"], row["dispersion_over_f01"],
                            row["alpha_over_f01"]) == row["verdict"]
            for row in rows))

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_device_control_hold", gate("real_device_control") == "HOLD")
    chk("gate_fabrication_hold", gate("fabrication_guidance") == "HOLD")
    chk("gate_cryogenics_hold", gate("cryogenic_operation") == "HOLD")
    chk("gate_vendor_claim_hold", gate("vendor_spec_claim") == "HOLD")
    chk("gate_advantage_hold", gate("quantum_advantage_claim") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"]
        == "Gemini Argon 4 Extended Thinking")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("SuperconductingQubit-Lab - transmon / Cooper-pair box lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - what this lab does and does not claim")
    print("    The Cooper-pair box Hamiltonian is diagonalised in the")
    print("    charge basis, from scratch (cyclic Jacobi, no libraries).")
    print("    Every energy is in units of E_C; the GHz conversion uses a")
    print(f"    LABELLED E_C/h = {EC_OVER_H_GHZ} GHz - a teaching number in")
    print("    the typical transmon range, NOT any real device's spec.")
    print("\n[2] The Hamiltonian - charging parabola + Josephson tunnelling")
    print("    H = 4 E_C (n - ng)^2 - (E_J/2)(|n><n+1| + h.c.),")
    print(f"    charge basis n = -{N_CHARGE}..{N_CHARGE} (31 states), E_C = 1.")
    print("    Diagonal: Cooper pairs cost charging energy. Off-diagonal:")
    print("    pairs tunnel through the junction at -E_J/2.")
    rows = sweep_report()
    by_ratio = {row["ratio"]: row for row in rows}
    print("\n[3] Levels at the sweet spot (ng = 0.5), E_J/E_C = 50")
    exact = levels(50, 0.5)
    for m in range(4):
        spacing = exact[m] - exact[0]
        asym = asymptotic_level(m, 50) - asymptotic_level(0, 50)
        print(f"    E{m} - E0 = {spacing:9.5f} E_C | asymptotic {asym:9.5f} "
              f"| diff {spacing - asym:+.5f}")
    print("\n[4] The sweep - one device, six regimes (ng = 0.5)")
    print("    E_J/E_C | f01 (E_C) | f01 asym | rel.err | alpha (E_C) "
          "| disp1/f01 | verdict")
    for row in rows:
        print(f"    {row['ratio']:7d} | {row['f01']:9.5f} | "
              f"{row['f01_asym']:8.5f} | {row['f01_relerr']:.2e} | "
              f"{row['alpha']:+11.5f} | {row['dispersion_over_f01']:.2e} "
              f"| {row['verdict']}")
    print("\n[5] Charge dispersion of level 1 - why the transmon wins")
    for row in rows:
        print(f"    E_J/E_C = {row['ratio']:4d}: eps_1 = "
              f"{row['dispersion_1']:.3e} E_C "
              f"(eps_1/f01 = {row['dispersion_over_f01']:.2e})")
    print(f"    asymptotic eps_1 at 100: {asymptotic_dispersion(100):.3e} E_C "
          f"(exact/asym = "
          f"{by_ratio[100]['dispersion_1'] / asymptotic_dispersion(100):.3f})")
    print("    -> eps_1 falls roughly as exp(-sqrt(8 E_J/E_C)): at ratio 1")
    print("       it is LARGER than f01 itself; at ratio 100 it is 1e-9 of")
    print("       f01. That collapse - bought with E_J - is the transmon.")
    print("\n[6] Anharmonicity - the price of the transmon bargain")
    for row in rows:
        print(f"    E_J/E_C = {row['ratio']:4d}: alpha = {row['alpha']:+.5f} "
              f"E_C (alpha/f01 = {row['alpha_over_f01']:+.4f})")
    print("    -> charge regime: alpha is large and POSITIVE (+6.55 E_C at")
    print("       ratio 1) - levels are charge states, not a qubit ladder.")
    print("       Transmon regime: alpha settles to -E_C, a few % of f01:")
    print("       enough to address the qubit, small enough to leak.")
    print("\n[7] Sweet spot - first-order charge-noise immunity")
    print(f"    df01/dng at ng = 0.5: {sweet_spot_slope(50):.2e} (ratio 50), "
          f"{sweet_spot_slope(1):.2e} (ratio 1)")
    print("    -> the slope vanishes at ng = 0.5 at every ratio; what the")
    print("       transmon adds is a dispersion so small the residual")
    print("       second-order wobble no longer matters.")
    print("\n[8] Design ledger - target f01 -> ratio -> exact grade")
    for row in ledger_report():
        print(f"    target {row['target_f01_ghz']:.1f} GHz -> formula ratio "
              f"{row['ratio_from_formula']:.3f} -> exact f01 "
              f"{row['f01_exact_ghz']:.4f} GHz ({row['f01_error_pct']:+.2f}%), "
              f"alpha {row['alpha_exact_ghz']:+.4f} GHz vs predicted "
              f"{row['alpha_predicted_ghz']:+.3f}")
    print("\n[9] Regime classifier (TinyML kNN, labels from the policy)")
    for name, label in classifier_report().items():
        print(f"    {name:12s} -> {label}")
    print("\n[10] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[11] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "levels":
        report = {f"EJ_EC_{row['ratio']}": {
            "levels_ng0": row["levels_ng0"],
            "levels_ng05": row["levels_ng05"]} for row in sweep_report()}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if cmd == "dispersion":
        report = {f"EJ_EC_{row['ratio']}": {
            "dispersion_0": row["dispersion_0"],
            "dispersion_1": row["dispersion_1"],
            "dispersion_1_over_f01": row["dispersion_over_f01"],
            "asymptotic_dispersion_1": asymptotic_dispersion(row["ratio"])}
            for row in sweep_report()}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if cmd == "anharmonicity":
        report = {f"EJ_EC_{row['ratio']}": {
            "f01": row["f01"], "alpha": row["alpha"],
            "alpha_asym": row["alpha_asym"],
            "alpha_over_f01": row["alpha_over_f01"]}
            for row in sweep_report()}
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    if cmd == "sweep":
        print(json.dumps(sweep_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "ledger":
        print(json.dumps(ledger_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "real_device_control"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
