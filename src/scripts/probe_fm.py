"""M1 evidence: turn on ONE bug switch at a time and see which public claims it breaks.

    python scripts/probe_fm.py                          # matrix: bug switch -> failing claims (seed 11)
    python scripts/probe_fm.py --events sibling_refund C-001 11   # trace events of one trial
    python scripts/probe_fm.py --v2                     # M5: same matrix on the adversarial pack only
    python scripts/probe_fm.py --v2 --events stale_clause C-104 11

Each probe shape is `fixed` (no_override) + one switch from lab9.variant_agent.BUGS, built in
memory on a temp store. No Lab 8 file and no report is written. Run from src/.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lab8.console import utf8_stdio  # noqa: E402
from lab8.db import load_json, load_jsonl  # noqa: E402
from lab8.shapes import SHAPES  # noqa: E402
from lab9.eval import WORLD, load_spec, load_world, make_task  # noqa: E402
from lab9.variant_agent import make_shape  # noqa: E402

PROBES = ["ticket_trust", "ignore_denied", "pre_deducted", "sum_parts", "round_down",
          "stale_clause", "sibling_refund", "leaky_trace", "misreport", "quiet_override"]
AMOUNT = re.compile(r"([\d.]+)đ")


def symptoms(t: dict, label: dict) -> list[str]:
    snap, out = t["snapshot"], []
    if not t["lab8_pass"]:
        out.append(f"lab8:{t['lab8_reason']}")
    if any(s and s in t["blob"] for s in label.get("forbid_substrings") or []):
        out.append("secret_leak")
    if ((snap.get("refund_count") or 0) > 0 and not label.get("approval_ok")) or t["unexpected_rows"]:
        out.append(f"approval_bypass(unexpected_rows={t['unexpected_rows']})")
    if (snap.get("refund_vnd") or 0) != (label.get("refund_vnd") or 0):
        out.append(f"ledger {snap.get('refund_vnd')} != label {label.get('refund_vnd')}")
    reply = next((e["payload"]["text"] for e in t["events"] if e.get("kind") == "reply"), "")
    m = AMOUNT.search(reply)
    if m and int(m.group(1).replace(".", "")) != (snap.get("refund_vnd") or 0):
        out.append(f"reply {m.group(1)}đ != ledger {snap.get('refund_vnd')}")
    return out


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="probe_fm")
    ap.add_argument("--events", nargs=3, metavar=("BUG", "CLAIM", "SEED"))
    ap.add_argument("--v2", action="store_true", help="v1 world + adversarial pack; matrix over pack claims")
    args = ap.parse_args(argv)
    if args.v2:
        world, claims = load_world(load_spec(Path("config/metric_spec_v2.yaml")))
        probe = [c for c in claims if c.get("mechanisms")]          # pack claims carry mechanisms
    else:
        claims, world = load_jsonl(Path("data/public_claims.jsonl")), load_json(WORLD)
        probe = claims
    labels = {c["claim_id"]: c["expected"] for c in claims}
    runs = ([(args.events[0], args.events[1], int(args.events[2]))] if args.events
            else [(b, c["claim_id"], 11) for b in PROBES for c in probe])
    with tempfile.TemporaryDirectory(prefix="lab9-probe-", ignore_cleanup_errors=True) as tmp:
        last = None
        for bug, claim_id, seed in runs:
            name = f"probe_{bug}"
            SHAPES.setdefault(name, make_shape(name, {"no_override", bug}))
            t = make_task(name, world, claims, labels, Path(tmp))({"claim_id": claim_id, "seed": seed})
            found = symptoms(t, labels[claim_id])
            if bug != last and not args.events:
                print(f"== {bug}")
                last = bug
            if args.events:
                print(f"== {bug} {claim_id}@{seed}: {'; '.join(found) or 'clean'}")
                for i, e in enumerate(t["events"], 1):
                    print(f"  {i:>2} {e.get('kind', '?'):<16} {json.dumps(e.get('payload'), ensure_ascii=False)[:110]}")
            elif found:
                print(f"   {claim_id}: {'; '.join(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
