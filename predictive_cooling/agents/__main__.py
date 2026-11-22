"""Run one agent case from the command line.

    python -m predictive_cooling.agents --at "2026-04-21 00:30"
    python -m predictive_cooling.agents --at "2026-04-21 00:30" --fault B5 B6
    python -m predictive_cooling.agents --at "2026-04-21 00:30" --mode analyze --agent gemini
    python -m predictive_cooling.agents --at "2026-04-21 00:30" --agent claude
    python -m predictive_cooling.agents --at "2026-04-29 05:30"                  # hardware warnings (no warmer)
    python -m predictive_cooling.agents --at "2026-04-21 00:30" --equipment-fault CRAH-1
"""
import argparse
import json

from . import CaseRequest, run_case, to_json


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--at", default="2026-04-21 00:30")
    parser.add_argument("--question", default=None)
    parser.add_argument("--mode", choices=["recommend", "analyze"], default="recommend")
    parser.add_argument("--agent", choices=["offline", "gemini", "claude"], default="offline")
    parser.add_argument("--fault", nargs="*", default=[], help="racks whose sensors fail, e.g. B5 B6")
    parser.add_argument("--equipment-fault", nargs="*", default=[], help="devices that trip, e.g. CRAH-1 CHWP-1")
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args()
    request = CaseRequest(at=args.at, mode=args.mode, agent_mode=args.agent, sensor_fault=tuple(args.fault),
                          equipment_fault=tuple(args.equipment_fault),
                          **({"question": args.question} if args.question else {}))
    result = run_case(request)
    if args.json:
        print(json.dumps(to_json(result), indent=2))
        return
    for e in result.events:
        print(f"{e.step:>2} {e.actor:<17} {e.action:<24} {e.status:<10} {e.skill_id or '':<3} {e.detail}")
    print()
    for check in result.checks:
        print(("PASS " if check.passed else "FAIL ") + check.name + (f" — {check.detail}" if check.detail else ""))
    print(f"\n[{result.status} · {result.decision}] {result.explanation}")


if __name__ == "__main__":
    main()
