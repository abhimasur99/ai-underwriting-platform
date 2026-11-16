"""CLI: run sample deals end to end and print the event log.

    python scripts/run_deal.py data/deals/bronx_mf
    python scripts/run_deal.py data/deals/* --fresh --quiet      (what `make demo` does)
    python scripts/run_deal.py data/deals/bronx_mf --force-mismatch persist   (retry, escalate)
    python scripts/run_deal.py data/deals/bronx_mf --live        (calls Claude; needs a key)
"""
import argparse
import sys
from pathlib import Path

from bridge.agents.chief import Chief
from bridge.agents.runner import CachedRunner
from bridge.agents.underwriter import FaultPlan
from bridge.core.parsers import parse_deal_dir
from bridge.settings import ROOT, get_settings
from bridge.store.db import Store


def _runner(live: bool, settings):
    if not live:
        return CachedRunner()
    if not settings.api_key:
        raise SystemExit("--live needs ANTHROPIC_API_KEY (copy .env.example to .env).")
    from bridge.agents.claude_runner import ClaudeRunner
    return ClaudeRunner.from_settings(settings)


def _print_events(chief: Chief, deal_id: str, quiet: bool) -> None:
    for e in chief.store.events(deal_id):
        if quiet and e.type == "tool.called":
            continue
        print(f"  {e.event_id:04d} {e.actor:<11} {e.type:<22} {e.summary}")


def _summary(chief: Chief, deal_id: str) -> None:
    state = chief.state(deal_id)
    print(f"\n== {deal_id}: state {state}")
    if state not in ("NEEDS_REVIEW",):
        return
    deal, result, check = chief.latest(deal_id)
    from bridge.store import projections
    st = projections.status(chief.store, deal_id)
    print(f"   {deal.name}")
    print(f"   call: {result.call.upper()}   checker: {check.status}   retries: "
          f"{st.retry_count}   escalated: {st.escalation}")
    for r in result.reasons:
        print(f"   - {r.code}")
    if not result.reasons:
        print("   - (no rule triggered)")
    print(f"   memo:     {result.artifacts['memo_pdf']}")
    print(f"   workbook: {result.artifacts['workbook']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("deals", nargs="+", type=Path, help="sample deal folder(s)")
    ap.add_argument("--live", action="store_true", help="call Claude instead of cached fixtures")
    ap.add_argument("--force-mismatch", nargs="?", const="once", choices=["once", "persist"],
                    help="nudge one underwriter metric so the checker fails (demo of retries)")
    ap.add_argument("--db", type=Path, help="SQLite file (default: data/runtime/bridge.db)")
    ap.add_argument("--fresh", action="store_true", help="delete the database first")
    ap.add_argument("--quiet", action="store_true", help="hide individual tool calls")
    args = ap.parse_args(argv)

    settings = get_settings()
    db = (args.db or settings.database_path)
    db = db if db.is_absolute() else ROOT / db
    if args.fresh and db.exists():
        db.unlink()
    runtime = db.parent
    faults = None
    if args.force_mismatch:
        faults = FaultPlan("ltc", 0.0078, frozenset({1} if args.force_mismatch == "once"
                                                    else {1, 2, 3}))
    chief = Chief(Store(db), _runner(args.live, settings), runtime / "outputs",
                  runtime / "uploads", faults=faults)
    code = 0
    for folder in args.deals:
        try:
            deal_id = parse_deal_dir(folder).deal_id
        except Exception:  # noqa: BLE001  (an incomplete folder is reported by the chief below)
            deal_id = chief.store.next_deal_id()
        if chief.store.deal_exists(deal_id):
            deal_id = chief.store.next_deal_id()
        chief.create_deal(deal_id)
        print(f"\n>> {folder.name} as {deal_id} ({'live' if args.live else 'cached'} mode)")
        checklist = chief.ingest_directory(deal_id, folder)
        if not checklist["ready"]:
            missing = checklist["missing"] + checklist["facts_missing"]
            print(f"   not ready: still missing {', '.join(missing)}")
            code = 1
            continue
        state = chief.process(deal_id)
        _print_events(chief, deal_id, args.quiet)
        _summary(chief, deal_id)
        if state not in ("NEEDS_REVIEW",):
            code = 1
    return code


if __name__ == "__main__":
    sys.exit(main())
