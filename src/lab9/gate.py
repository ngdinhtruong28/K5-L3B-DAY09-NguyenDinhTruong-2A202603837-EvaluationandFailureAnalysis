"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def _ratchet_problems(spec: dict, base_spec: dict) -> list[str]:
    """Thresholds on the same eval-set version may only get stricter."""
    problems: list[str] = []
    base_metrics = {m["id"]: m for m in base_spec.get("metrics") or []}
    spec_metrics = {m["id"]: m for m in spec.get("metrics") or []}
    for mid, bm in base_metrics.items():
        sm = spec_metrics.get(mid)
        if sm is None:
            problems.append(f"metric {mid} disappeared from the spec")
            continue
        bth, sth = bm.get("threshold") or {}, sm.get("threshold") or {}
        if "min" in bth and ("min" not in sth or sth["min"] < bth["min"]):
            problems.append(f"metric {mid} min loosened: {bth.get('min')} -> {sth.get('min')}")
        if "max" in bth and ("max" not in sth or sth["max"] > bth["max"]):
            problems.append(f"metric {mid} max loosened: {bth.get('max')} -> {sth.get('max')}")
        if "max_increase" in bth and (
            "max_increase" not in sth or sth["max_increase"] > bth["max_increase"]
        ):
            problems.append(
                f"metric {mid} max_increase loosened: {bth.get('max_increase')} -> {sth.get('max_increase')}"
            )
        if bth.get("no_significant_drop") and not sth.get("no_significant_drop"):
            problems.append(f"metric {mid} dropped no_significant_drop")
        if bm.get("blocking") and not sm.get("blocking"):
            problems.append(f"metric {mid} changed from blocking to non-blocking")

    base_slices = {s["name"]: s for s in base_spec.get("slices") or []}
    spec_slices = {s["name"]: s for s in spec.get("slices") or []}
    for name, bs in base_slices.items():
        ss = spec_slices.get(name)
        if ss is None:
            problems.append(f"slice {name} disappeared from the spec")
            continue
        if bs.get("metric") != ss.get("metric"):
            problems.append(f"slice {name} metric changed: {bs.get('metric')} -> {ss.get('metric')}")
        if "min" in bs and ("min" not in ss or ss["min"] < bs["min"]):
            problems.append(f"slice {name} min loosened: {bs.get('min')} -> {ss.get('min')}")
        if bs.get("no_significant_drop") and not ss.get("no_significant_drop"):
            problems.append(f"slice {name} dropped no_significant_drop")
        if bs.get("blocking") and not ss.get("blocking"):
            problems.append(f"slice {name} changed from blocking to non-blocking")
    return problems


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems: list[str] = []

    for key, value in (pr.get("metrics") or {}).items():
        if isinstance(value, (int, float)) and not isinstance(value, bool) and not math.isfinite(float(value)):
            problems.append(f"metric {key} is {value!r} (NaN/inf)")

    manifest = pr.get("manifest") or {}
    try:
        expected_rows = int(manifest["items"]) * len(manifest["seeds"])
    except (KeyError, TypeError, ValueError):
        expected_rows = None
    rows = pr.get("rows") or []
    if expected_rows is not None and len(rows) != expected_rows:
        problems.append(f"row count {len(rows)} != items x seeds {expected_rows}")

    pr_keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if len(set(pr_keys)) != len(pr_keys):
        problems.append("duplicate (item_id, seed) rows in the PR report")
    if set(pr_keys) != base_keys:
        missing = sorted(base_keys - set(pr_keys))
        extra = sorted(set(pr_keys) - base_keys)
        problems.append(f"(item_id, seed) set differs from baseline: missing={missing[:5]}, extra={extra[:5]}")

    if pr.get("evaluator_failures"):
        problems.append(f"evaluator_failures is non-empty: {pr['evaluator_failures'][:1]}")

    graded = {m["id"] for m in spec.get("metrics") or []}
    for row in rows:
        for mid in sorted(graded & set(row)):
            if row.get(mid) is None:
                problems.append(f"{row.get('item_id')}@{row.get('seed')}: graded metric {mid} is None")

    base_slices = {
        (r.get("item_id"), r.get("seed")): tuple(sorted(r.get("slices") or []))
        for r in base.get("rows") or []
    }
    for row in rows:
        key = (row.get("item_id"), row.get("seed"))
        if key in base_slices and tuple(sorted(row.get("slices") or [])) != base_slices[key]:
            problems.append(f"{key[0]}@{key[1]}: slice tags differ from baseline")

    if base_spec is not None:
        problems += _ratchet_problems(spec, base_spec)
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked: list[str] = []
    lines: list[str] = []
    bootstrap = spec.get("bootstrap") or {}
    for sl in spec.get("slices") or []:
        name, metric = sl["name"], sl["metric"]
        sid = f"slice:{name}/{metric}"
        values = per_item(pr, metric, slice_name=name)
        if not values:
            verdict = "MISSING"
            lines.append(f"  {sid:<32} {'-':<8} {json.dumps(sl):<48} no items in slice")
            if sl.get("blocking"):
                blocked.append(sid)
            continue

        value = sum(values.values()) / len(values)
        threshold = sl.get("min")
        verdict, note = "ok", ""
        if threshold is not None and value < threshold:
            verdict = "fail"
        if sl.get("no_significant_drop"):
            base_values = per_item(base, metric, slice_name=name)
            keys = sorted(set(values) & set(base_values))
            if not keys:
                verdict = "fail"
                note = "no paired items"
            else:
                delta, lo, hi = stats.paired_bootstrap(
                    [values[k] for k in keys],
                    [base_values[k] for k in keys],
                    n_resamples=bootstrap.get("n_resamples", 1000),
                    rng=bootstrap.get("rng", 2027),
                )
                note = f"Δ {delta:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"

        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        label = "ok" if verdict == "ok" else ("BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<32} {value:<8.4f} {json.dumps(sl):<48} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
