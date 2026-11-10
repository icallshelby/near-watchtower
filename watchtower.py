#!/usr/bin/env python3
"""NEAR Watchtower - a stdlib-only network-health agent for NEAR Protocol.

Polls public NEAR data sources, computes a transparent 0-100 health score
from live network evidence, detects anomalies against its own committed
snapshot history, and publishes:
  data/status.json        machine-readable feed other agents/apps can poll
  data/snapshot_raw.json  raw API responses (audit trail)
  data/history.jsonl      one line per run: the agent's own time series
  BRIEF.md                plain-language brief generated from the same data

No API keys. Python 3 standard library only.
Re-run: python3 watchtower.py && python3 build_dashboard.py
"""
import json, math, statistics, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
UA = {"User-Agent": "near-watchtower/2.0 (+https://github.com/icallshelby/near-watchtower)"}

# Scoring policy (also printed in README and embedded in the dashboard).
TARGETS = {"cadence_s": 0.6, "nakamoto": 15, "staked_pct": 60.0,
           "blocks_day": 144000, "turnover_pct": 12.0}
WEIGHTS = {"cadence": 0.20, "decentralization": 0.25, "staking": 0.20,
           "throughput": 0.15, "liquidity": 0.20}

def fetch(url, post=None, tries=3):
    last = None
    for i in range(tries):
        try:
            body = json.dumps(post).encode() if post is not None else None
            req = urllib.request.Request(url, body, {**UA, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read())
        except Exception as e:  # sandbox proxy can truncate urllib reads
            last = e
            time.sleep(1 + i)
    cmd = ["curl", "-s", url, "-H", f"User-Agent: {UA['User-Agent']}"]
    if post is not None:
        cmd += ["-H", "Content-Type: " +"application/json", "-d", json.dumps(post)]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if out.returncode == 0 and out.stdout.strip():
        return json.loads(out.stdout)
    raise RuntimeError(f"fetch failed {url}: {last}")

def clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))

def load_history():
    p = DATA / "history.jsonl"
    if not p.exists():
        return []
    rows = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return rows

def detect_alerts(components, label, prev_label, history):
    """Anomaly flags: hard thresholds always; z-scores once >=5 snapshots exist."""
    alerts = []
    for name, val in components.items():
        if val < 40:
            alerts.append({"component": name, "kind": "low_component",
                           "detail": f"{name} component is {val:.1f}/100 (below 40)"})
    if prev_label and prev_label != label:
        alerts.append({"component": "health", "kind": "label_change",
                       "detail": f"health label changed {prev_label} -> {label}"})
    if len(history) >= 5:
        for name in components:
            series = [h["components"][name] for h in history if name in h.get("components", {})]
            if len(series) >= 5:
                mu, sd = statistics.mean(series), statistics.pstdev(series)
                if sd > 0:
                    z = (components[name] - mu) / sd
                    if abs(z) >= 2:
                        alerts.append({"component": name, "kind": "z_score",
                                       "detail": f"{name} is {z:+.1f} sigma vs its own history "
                                                 f"(now {components[name]:.1f}, mean {mu:.1f})"})
    return alerts

def main():
    raw = {}
    stats = fetch("https://api.nearblocks.io/v1/stats")["stats"][0]
    raw["nearblocks_stats"] = stats
    status = fetch("https://rpc.mainnet.near.org", {"jsonrpc": "2.0", "id": "1", "method": "status", "params": []})
    raw["rpc_status"] = status
    vals = fetch("https://rpc.mainnet.near.org", {"jsonrpc": "2.0", "id": "1", "method": "validators", "params": [None]})
    raw["rpc_validators"] = {"result": {"current_validators": vals["result"]["current_validators"]}}
    cg = fetch("https://api.coingecko.com/api/v3/coins/near?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false")
    raw["coingecko_near"] = {"market_data": cg["market_data"]}

    md = cg["market_data"]
    price = md["current_price"]["usd"]
    mcap = md["market_cap"]["usd"]
    vol24 = md["total_volume"]["usd"]
    ath = md["ath"]["usd"]
    # Supply from NearBlocks (yocto strings): CoinGecko's circulating field
    # for NEAR currently mirrors total supply, so it is not used for supply.
    circ = int(stats["circulating_supply"]) / 1e24
    total = int(stats["total_supply"]) / 1e24

    cur = vals["result"]["current_validators"]
    stakes = sorted((float(v["stake"]) / 1e24 for v in cur), reverse=True)
    n_validators = len(stakes)
    total_staked = sum(stakes)
    nc, acc = 0, 0.0
    for s in stakes:
        acc += s; nc += 1
        if acc > total_staked / 3:
            break
    staked_pct = 100.0 * total_staked / total
    top10_pct = 100.0 * sum(stakes[:10]) / total_staked
    top1_pct = 100.0 * stakes[0] / total_staked if stakes else 0

    txns = int(str(stats["total_txns"]).replace(",", ""))
    nodes = int(stats["nodes_online"])
    block_s = float(stats["avg_block_time"])
    blocks_day = 86400.0 / block_s if block_s else 0
    vol_mcap = 100.0 * vol24 / mcap if mcap else 0
    drawdown = 100.0 * (price / ath - 1) if ath else 0

    parts = {
        "cadence": clamp(100.0 - abs(block_s - TARGETS["cadence_s"]) / TARGETS["cadence_s"] * 100.0),
        "decentralization": clamp(nc / TARGETS["nakamoto"] * 100.0),
        "staking": clamp(staked_pct / TARGETS["staked_pct"] * 100.0),
        "throughput": clamp(blocks_day / TARGETS["blocks_day"] * 100.0),
        "liquidity": clamp(vol_mcap / TARGETS["turnover_pct"] * 100.0),
    }
    score = sum(parts[k] * WEIGHTS[k] for k in parts)
    label = "STRONG" if score >= 75 else "STEADY" if score >= 55 else "FRAGILE" if score >= 40 else "CRITICAL"

    history = load_history()
    prev_label = history[-1]["health_label"] if history else None
    alerts = detect_alerts(parts, label, prev_label, history)

    now = datetime.now(timezone.utc).isoformat()
    status_out = {
        "generated_at": now,
        "agent": "near-watchtower",
        "version": 2,
        "network": "NEAR mainnet",
        "health_score": round(score, 1),
        "health_label": label,
        "components": {k: round(v, 1) for k, v in parts.items()},
        "weights": WEIGHTS,
        "targets": TARGETS,
        "alerts": alerts,
        "history_snapshots": len(history) + 1,
        "evidence": {
            "price_usd": price, "market_cap_usd": mcap, "volume_24h_usd": vol24,
            "ath_usd": ath, "drawdown_from_ath_pct": round(drawdown, 2),
            "circulating_supply": circ, "total_supply": total,
            "validators": n_validators, "nakamoto_coefficient": nc,
            "total_staked_near": round(total_staked, 1), "staked_pct_of_supply": round(staked_pct, 2),
            "top1_pool_pct_of_stake": round(top1_pct, 2),
            "top10_pools_pct_of_stake": round(top10_pct, 2),
            "lifetime_transactions": txns, "nodes_online": nodes,
            "avg_block_time_s": block_s, "blocks_per_day_est": round(blocks_day),
            "volume_over_market_cap_pct": round(vol_mcap, 2),
            "latest_block_height": status["result"]["sync_info"]["latest_block_height"],
        },
        "sources": ["https://api.nearblocks.io/v1/stats",
                    "https://rpc.mainnet.near.org (status, validators)",
                    "https://api.coingecko.com/api/v3/coins/near"],
    }
    DATA.mkdir(exist_ok=True)
    (DATA / "status.json").write_text(json.dumps(status_out, indent=2))
    (DATA / "snapshot_raw.json").write_text(json.dumps(raw, indent=2))
    with open(DATA / "history.jsonl", "a") as f:
        f.write(json.dumps({"at": now, "health_score": round(score, 1),
                            "health_label": label, "components": status_out["components"],
                            "nakamoto_coefficient": nc,
                            "staked_pct_of_supply": round(staked_pct, 2),
                            "price_usd": price}) + "\n")

    ev = status_out["evidence"]
    alert_lines = "\n".join(f"- ALERT: {a['detail']}" for a in alerts) or "- No alerts this run."
    brief = f"""# NEAR Watchtower brief — {now[:10]}

**Network health: {score:.1f}/100 ({label})** · snapshot #{len(history) + 1}

- Blocks are landing every ~{block_s:.3f}s across {n_validators} validators; the
  Nakamoto coefficient is {nc} (the top 10 pools hold {top10_pct:.1f}% of stake,
  the largest single pool {top1_pct:.1f}%).
- {staked_pct:.1f}% of all NEAR is staked ({total_staked:,.0f} NEAR) — holders are
  committing, not just trading.
- Lifetime transactions: {txns:,}; {nodes} nodes online; 24h turnover is
  {vol_mcap:.1f}% of market cap.
- Price ${price:.2f} (market cap ${mcap:,.0f}), {drawdown:.1f}% vs the ${ath:.2f} ATH.

Alerts:
{alert_lines}

Generated by `watchtower.py` from live public data; every input is in
`data/status.json`, the raw responses in `data/snapshot_raw.json`, and the
run history in `data/history.jsonl`.
Research and education only — not financial advice.
"""
    (ROOT / "BRIEF.md").write_text(brief)
    print(json.dumps({"score": status_out["health_score"], "label": label,
                      "alerts": len(alerts), "snapshots": len(history) + 1,
                      "price": price, "validators": n_validators, "nc": nc}, indent=2))

if __name__ == "__main__":
    sys.exit(main())
