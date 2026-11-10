#!/usr/bin/env python3
"""Demo consumer agent for the NEAR Watchtower feed.

Shows how a second, independent agent uses data/status.json: it reads the
health feed, applies a published risk policy, and logs the decision it
would take for a SIMULATED treasury allocation. No real funds, no keys,
no transactions — the point is the agent-to-agent contract: one agent
publishes evidence, another acts on it without trusting the first agent's
word, because every input is in the feed's audit trail.

Policy (also in README):
  STRONG   -> risk budget 70% growth / 30% reserve
  STEADY   -> 50 / 50
  FRAGILE  -> 20 / 80 and raise an operator alert
  CRITICAL -> 0 / 100 and raise an operator alert
Any active watchtower alert caps the growth share at 20% regardless of label.

Run: python3 agent_consumer.py   (after watchtower.py)
Writes: data/agent_log.jsonl (one decision record per run), prints a summary.
Python 3 standard library only.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

POLICY = {"STRONG": 70, "STEADY": 50, "FRAGILE": 20, "CRITICAL": 0}

def main():
    feed = json.loads((DATA / "status.json").read_text())
    label = feed["health_label"]
    growth = POLICY[label]
    reasons = [f"health {feed['health_score']}/100 -> {label}, base growth share {growth}%"]
    alerts = feed.get("alerts", [])
    if alerts:
        if growth > 20:
            reasons.append(f"{len(alerts)} active watchtower alert(s) -> growth capped at 20%")
            growth = 20
        for a in alerts:
            reasons.append(f"alert: {a['detail']}")
    weakest = min(feed["components"], key=feed["components"].get)
    reasons.append(f"weakest component: {weakest} ({feed['components'][weakest]}/100)")
    decision = {
        "at": datetime.now(timezone.utc).isoformat(),
        "consumer": "demo-treasury-agent (SIMULATION - no real funds)",
        "feed_generated_at": feed["generated_at"],
        "health_label": label,
        "health_score": feed["health_score"],
        "allocation_growth_pct": growth,
        "allocation_reserve_pct": 100 - growth,
        "operator_alert": label in ("FRAGILE", "CRITICAL") or bool(alerts),
        "reasons": reasons,
    }
    with open(DATA / "agent_log.jsonl", "a") as f:
        f.write(json.dumps(decision) + "\n")
    print(f"[{decision['consumer']}]")
    print(f"Feed: {label} {feed['health_score']}/100 (generated {feed['generated_at']})")
    print(f"Decision (simulated): {growth}% growth / {100 - growth}% reserve"
          f"{'  ** OPERATOR ALERT **' if decision['operator_alert'] else ''}")
    for r in reasons:
        print(f"  - {r}")

if __name__ == "__main__":
    main()
