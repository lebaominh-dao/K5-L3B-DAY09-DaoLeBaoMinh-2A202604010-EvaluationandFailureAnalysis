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
from lab9 import evalset, stats
from lab9.eval import SPEC, aggregate, load_spec, per_item
from lab9.graders import GRADERS


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
    for who, rep in (("PR", pr), ("baseline", base)):
        problems += [f"{who}: {p}" for p in _report_problems(rep, spec)]
    problems += _pair_problems(pr, base)
    problems += _slice_tag_problems(pr, base, spec)
    if base_spec is not None:
        problems += ratchet_problems(spec, base_spec, same_eval_set=(
            pr["manifest"].get("eval_set_sha") == base["manifest"].get("eval_set_sha")))
    return problems


def _graded_ids(rep: dict, spec: dict) -> list[str]:
    """Spec metrics scored per row (code graders). Aggregate-only ids (pass_hat_5, cost) are not."""
    return [m["id"] for m in spec["metrics"] if m["id"] in GRADERS
            or any(m["id"] in r for r in rep.get("rows") or [])]


def _report_problems(rep: dict, spec: dict) -> list[str]:
    """Problems visible in one report on its own: broken numbers, broken graders, wrong row count,
    and headline metrics that do not follow from the rows."""
    out: list[str] = []
    for k, v in (rep.get("metrics") or {}).items():
        if isinstance(v, float) and not math.isfinite(v):
            out.append(f"metric {k} is {v} (a crashed grader must fail the run, not drop out of it)")
    if rep.get("evaluator_failures"):
        out.append(f"{len(rep['evaluator_failures'])} evaluator failure(s), first: {rep['evaluator_failures'][0]}")
    rows, man = rep.get("rows") or [], rep.get("manifest") or {}
    want = int(man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        out.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    if spec.get("seeds") and sorted(man.get("seeds") or []) != sorted(spec["seeds"]):
        out.append(f"seeds {man.get('seeds')} differ from the spec's {spec['seeds']}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        out.append(f"duplicated (item, seed) rows: {dups[:5]}")
    graded = _graded_ids(rep, spec)
    bad = [f"{r.get('item_id')}@{r.get('seed')}:{m}={r.get(m)!r}" for r in rows for m in graded
           if not isinstance(r.get(m), bool)]
    if bad:
        out.append(f"{len(bad)} graded value(s) missing or not a bool (crashed grader?), first: {bad[0]}")
    elif rows:
        # Headline numbers must be what the rows say: a hand-edited metric is not a measurement.
        k_values = sorted({int(k.rsplit("_", 1)[1]) for k in rep.get("metrics") or {}
                           if k.startswith(("pass_at_", "pass_hat_")) and k.rsplit("_", 1)[1].isdigit()})
        try:
            again = aggregate([{**r, "cost": r.get("cost", 0.0)} for r in rows], graded, k_values=k_values)
        except (ValueError, KeyError, TypeError) as e:
            out.append(f"metrics cannot be recomputed from rows: {e}")
            again = {}
        for k, v in (rep.get("metrics") or {}).items():
            w = again.get(k)
            if k == "cost_per_success" and not any("cost" in r for r in rows):
                continue
            if isinstance(v, (int, float)) and isinstance(w, (int, float)) and math.isfinite(v) and abs(v - w) > 1e-4:
                out.append(f"metric {k}={v} but the rows give {w}")
            elif (v is None) != (w is None) and k in again:
                out.append(f"metric {k}={v} but the rows give {w}")
    return out


def _pair_problems(pr: dict, base: dict) -> list[str]:
    """Paired comparison is only valid on the same (item, seed) set: no dropped, added or swapped trials."""
    a = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows") or []}
    b = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    out = []
    if a != b:
        out.append(f"(item, seed) set differs from the baseline: {len(b - a)} missing, {len(a - b)} extra"
                   f" (e.g. missing {sorted(b - a, key=str)[:3]})")
    pm, bm = pr.get("manifest") or {}, base.get("manifest") or {}
    if pm.get("items") != bm.get("items") or sorted(pm.get("seeds") or []) != sorted(bm.get("seeds") or []):
        out.append(f"manifest {pm.get('items')} items / seeds {pm.get('seeds')} differs from the baseline's "
                   f"{bm.get('items')} items / seeds {bm.get('seeds')}")
    return out


def _slice_tag_problems(pr: dict, base: dict, spec: dict) -> list[str]:
    """Slice membership comes from the label, so it is fixed per item. Compare the PR's tags with the
    baseline's and, when the eval-set file is there, with the item file itself (a tampered baseline
    must not vouch for a tampered PR)."""
    truth: dict[str, list[str]] = {}
    path = Path(spec.get("eval_set") or "")
    if spec.get("eval_set") and path.is_file():
        truth = {it["item_id"]: sorted(it.get("slices") or []) for it in evalset.load_jsonl(path)}
    out = []
    for who, rep in (("PR", pr), ("baseline", base)):
        seen: dict[str, list[str]] = {}
        for r in rep.get("rows") or []:
            tags = sorted(r.get("slices") or [])
            iid = r.get("item_id")
            if iid in seen and seen[iid] != tags:
                out.append(f"{who}: {iid} carries different slice tags on different seeds")
            seen.setdefault(iid, tags)
            if truth and iid in truth and truth[iid] != tags:
                out.append(f"{who}: {iid}@{r.get('seed')} slices {tags} but the eval set says {truth[iid]}")
                break
    base_tags = {r.get("item_id"): sorted(r.get("slices") or []) for r in base.get("rows") or []}
    moved = sorted({r.get("item_id") for r in pr.get("rows") or []
                    if r.get("item_id") in base_tags and sorted(r.get("slices") or []) != base_tags[r.get("item_id")]},
                   key=str)
    if moved:
        out.append(f"slice tags of {moved[:5]} differ from the baseline's (relabelled out of a slice?)")
    return out


def _looser(old: dict, new: dict | None, where: str) -> list[str]:
    """One metric or slice entry: may only get stricter."""
    if new is None:
        return [f"{where} was removed"]
    out = []
    if old.get("blocking") and not new.get("blocking"):
        out.append(f"{where} is no longer blocking")
    oth, nth = old.get("threshold", old), new.get("threshold", new)
    for key, worse in (("max", lambda o, n: n > o), ("min", lambda o, n: n < o),
                       ("max_increase", lambda o, n: n > o)):
        if key in oth:
            if key not in nth or nth[key] is None:
                out.append(f"{where} dropped {key} {oth[key]}")
            elif worse(oth[key], nth[key]):
                out.append(f"{where} {key} loosened {oth[key]} -> {nth[key]}")
    if oth.get("no_significant_drop") and not nth.get("no_significant_drop"):
        out.append(f"{where} dropped no_significant_drop")
    return out


def ratchet_problems(spec: dict, base_spec: dict, *, same_eval_set: bool = True) -> list[str]:
    """Same eval set => thresholds may only get stricter. Bumping eval_set_version on the same eval
    set (same sha) does not reset the ratchet: it is a relabel, not a new eval set."""
    out: list[str] = []
    sv, bv = spec.get("eval_set_version"), base_spec.get("eval_set_version")
    if sv != bv:
        if not same_eval_set:
            return out          # genuinely new eval set: thresholds start again, new baseline needed
        out.append(f"RATCHET eval_set_version {bv} -> {sv} without a new eval set")
    new_m = {m["id"]: m for m in spec.get("metrics") or []}
    for m in base_spec.get("metrics") or []:
        out += [f"RATCHET {p}" for p in _looser(m, new_m.get(m["id"]), f"metric {m['id']}")]
    new_s = {(s["name"], s["metric"]): s for s in spec.get("slices") or []}
    for s in base_spec.get("slices") or []:
        out += [f"RATCHET {p}" for p in _looser(s, new_s.get((s["name"], s["metric"])),
                                                f"slice {s['name']}/{s['metric']}")]
    if sorted(spec.get("seeds") or []) != sorted(base_spec.get("seeds") or []):
        out.append(f"RATCHET seeds changed {base_spec.get('seeds')} -> {spec.get('seeds')}")
    if (spec.get("bootstrap") or {}).get("confidence", 0.95) > (base_spec.get("bootstrap") or {}).get("confidence", 0.95):
        out.append("RATCHET bootstrap confidence raised (wider CI = fewer regressions blocked)")
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for sl in spec.get("slices") or []:
        name, mid = sl["name"], sl["metric"]
        sid = f"slice:{name}/{mid}"
        a, b = per_item(pr, mid, slice_name=name), per_item(base, mid, slice_name=name)
        verdict, note, val = "ok", "", None
        if not a:
            # An empty slice is not "nothing to check": the items were dropped or relabelled away.
            verdict, note = "missing", "no PR rows in this slice"
        else:
            val = round(sum(a.values()) / len(a), 4)
            if "min" in sl and val < sl["min"]:
                verdict = "fail"
            if "max" in sl and val > sl["max"]:
                verdict = "fail"
            if sl.get("no_significant_drop"):
                keys = sorted(set(a) & set(b))
                if keys:
                    d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                                       n_resamples=bs.get("n_resamples", 1000),
                                                       rng=bs.get("rng", 2027))
                    note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                    if hi < 0:
                        verdict = "fail"
                else:
                    verdict, note = "missing", "no baseline items to pair with"
        if verdict != "ok" and sl.get("blocking"):
            blocked.append(sid)
        th = {k: sl[k] for k in ("min", "max", "no_significant_drop") if k in sl}
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if sl.get("blocking") else "warn")
        lines.append(f"  {sid:<44} {val!s:<8} {json.dumps(th):<44} {note:<28} {label}  (n={len(a)} item)")
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
