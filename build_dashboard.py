#!/usr/bin/env python3
"""Render index.html — the interactive NEAR Watchtower lab — from
data/status.json, data/history.jsonl and data/agent_log.jsonl.

The page is fully self-contained (no external requests). Visitors can move
the scoring weights and targets and watch the health score recompute live
from the same published evidence — the model is inspectable, not a black box.
Python 3 standard library only. Run after watchtower.py."""
import json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
S = json.loads((DATA / "status.json").read_text())
ev, comp = S["evidence"], S["components"]

def load_jsonl(name):
    p = DATA / name
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out

history = load_jsonl("history.jsonl")
agent_log = load_jsonl("agent_log.jsonl")
last_decision = agent_log[-1] if agent_log else None
score = S["health_score"]

def fmt(n, dec=0):
    return f"{n:,.{dec}f}"

def arc(value):
    frac = value / 100.0
    length = math.pi * 90
    color = "#3fb950" if value >= 75 else "#d29922" if value >= 55 else "#f0883e" if value >= 40 else "#f85149"
    return (f'<path d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="#21262d" stroke-width="14"/>'
            f'<path id="gaugeArc" d="M 20 110 A 90 90 0 0 1 200 110" fill="none" stroke="{color}" stroke-width="14" '
            f'stroke-dasharray="{frac * length:.1f} {length:.1f}"/>')

def label_of(v):
    return "STRONG" if v >= 75 else "STEADY" if v >= 55 else "FRAGILE" if v >= 40 else "CRITICAL"

def color_of(v):
    return "#3fb950" if v >= 75 else "#d29922" if v >= 55 else "#f0883e" if v >= 40 else "#f85149"

bar_rows = ""
for key in ["cadence", "decentralization", "staking", "throughput", "liquidity"]:
    v = comp[key]
    bar_rows += (f'<div class="bar-row"><span class="bar-name">{key.title()}</span>'
                 f'<div class="bar-track"><div class="bar-fill" id="bar-{key}" style="width:{v:.0f}%;background:{color_of(v)}"></div></div>'
                 f'<span class="bar-val" id="val-{key}">{v:.1f}</span></div>')

cards = [
    (f'${ev["price_usd"]:,.2f}', "NEAR price (USD)"),
    (f'${fmt(ev["market_cap_usd"])}', "Market cap"),
    (f'{ev["drawdown_from_ath_pct"]:.1f}%', f'vs all-time high ${ev["ath_usd"]:,.2f}'),
    (f'{ev["validators"]}', "Validators in the live set"),
    (f'{ev["nakamoto_coefficient"]}', "Nakamoto coefficient"),
    (f'{ev["staked_pct_of_supply"]:.2f}%', "Of supply staked"),
    (f'{ev["top1_pool_pct_of_stake"]:.1f}% / {ev["top10_pools_pct_of_stake"]:.1f}%', "Largest pool / top-10 share of stake"),
    (f'{fmt(ev["lifetime_transactions"])}', "Lifetime transactions"),
    (f'{ev["avg_block_time_s"]:.3f}s', "Average block time"),
    (f'{fmt(ev["blocks_per_day_est"])}', "Blocks per day (est.)"),
    (f'{ev["volume_over_market_cap_pct"]:.2f}%', "24h volume / market cap"),
    (f'{fmt(ev["latest_block_height"])}', "Latest block height"),
]
cards_html = "".join(f'<div class="card"><div class="num">{v}</div><div class="lbl">{l}</div></div>' for v, l in cards)

alerts_html = "".join(f'<div class="alert">⚠ {a["detail"]}</div>' for a in S["alerts"]) or \
              '<div class="ok">No alerts this snapshot — every component is within its normal band.</div>'

# history sparkline (score over snapshots)
if len(history) >= 2:
    pts, W, H = [], 640, 90
    xs = [h["health_score"] for h in history]
    lo, hi = min(xs + [40]), max(xs + [90])
    for i, h in enumerate(history):
        x = 8 + i * (W - 16) / (len(history) - 1)
        y = H - 8 - (h["health_score"] - lo) / (hi - lo) * (H - 16)
        pts.append(f"{x:.0f},{y:.0f}")
    history_html = (f'<svg width="100%" viewBox="0 0 {W} {H}" style="background:#161b22;border:1px solid #21262d;border-radius:8px">'
                    f'<polyline points="{" ".join(pts)}" fill="none" stroke="#3fb950" stroke-width="2"/></svg>'
                    f'<div class="sub">{len(history)} committed snapshots — the agent\'s own time series '
                    f'(data/history.jsonl). First: {history[0]["at"][:16]}Z · latest: {history[-1]["at"][:16]}Z.</div>')
else:
    history_html = '<div class="sub">The time series starts with this snapshot; every run appends one line to data/history.jsonl.</div>'

if last_decision:
    reasons = "".join(f"<li>{r}</li>" for r in last_decision["reasons"])
    consumer_html = (f'<div class="card" style="grid-column:1/-1"><div class="num" style="font-size:17px">'
                     f'Demo treasury agent → {last_decision["allocation_growth_pct"]}% growth / '
                     f'{last_decision["allocation_reserve_pct"]}% reserve'
                     f'{" · OPERATOR ALERT" if last_decision["operator_alert"] else ""}</div>'
                     f'<div class="lbl">SIMULATION — no real funds. Decision by agent_consumer.py from this feed '
                     f'(label {last_decision["health_label"]}, {last_decision["health_score"]}/100).</div>'
                     f'<ul style="margin:8px 0 0;padding-left:18px">{reasons}</ul></div>')
else:
    consumer_html = '<div class="sub">Run agent_consumer.py to see a second agent act on this feed.</div>'

feed_json = json.dumps({"evidence": ev, "weights": S["weights"], "targets": S["targets"]})

html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NEAR Watchtower — an interactive network-health agent</title>
<style>
body{{background:#0d1117;color:#e6edf3;font-family:-apple-system,'Segoe UI',Roboto,sans-serif;margin:0;padding:32px 20px}}
.wrap{{max-width:1024px;margin:0 auto}} h1{{font-size:30px;margin:0 0 6px}} h2{{font-size:20px;margin:32px 0 10px;border-bottom:1px solid #21262d;padding-bottom:6px}}
.sub{{color:#8b949e;font-size:14px;line-height:1.55}} code{{background:#161b22;padding:1px 5px;border-radius:4px;font-size:12.5px}}
.hero{{display:flex;gap:28px;flex-wrap:wrap;align-items:flex-start;margin-top:18px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px;margin-top:14px}}
.card{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px}} .num{{font-size:21px;font-weight:700}} .lbl{{color:#8b949e;font-size:12.5px;margin-top:3px}}
.bar-row{{display:flex;align-items:center;gap:10px;margin:7px 0}} .bar-name{{width:140px;font-size:13.5px}}
.bar-track{{flex:1;background:#21262d;border-radius:5px;height:14px}} .bar-fill{{height:14px;border-radius:5px;transition:width .2s}}
.bar-val{{width:44px;font-weight:700;font-size:13.5px}}
.ctl{{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px 22px;margin-top:10px}}
.ctl label{{font-size:13px;color:#8b949e;display:flex;justify-content:space-between}}
input[type=range]{{width:100%}} button{{background:#21262d;color:#e6edf3;border:1px solid #30363d;border-radius:6px;padding:7px 12px;cursor:pointer;font-size:13px}}
button:hover{{background:#30363d}} .alert{{background:#2d1a08;border:1px solid #9e6a03;border-radius:8px;padding:10px 14px;margin:6px 0}}
.ok{{background:#0f2417;border:1px solid #238636;border-radius:8px;padding:10px 14px}}
li{{margin:5px 0;line-height:1.5}} .foot{{color:#8b949e;font-size:12.5px;margin-top:34px;line-height:1.6}}
pre{{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;overflow-x:auto;font-size:12.5px}}
</style></head><body><div class="wrap">
<h1>NEAR Watchtower</h1>
<div class="sub">A network-health agent for NEAR Protocol — and an open lab around it. The agent polls live
public data, scores the network from evidence, watches its own history for anomalies, and publishes a feed
(<code>data/status.json</code>) that other agents act on (one does, below). On this page you can also
<b>re-weight the model yourself</b> and watch the score change: the methodology is inspectable, not a black box.<br>
Snapshot: {S["generated_at"]} · snapshot #{S["history_snapshots"]}</div>

<div class="hero">
<div><svg width="220" height="130" viewBox="0 0 220 130">{arc(score)}
<text x="110" y="95" text-anchor="middle" font-size="34" fill="#e6edf3" font-weight="700" id="scoreNum">{score}</text>
<text x="110" y="118" text-anchor="middle" font-size="13" font-weight="700" id="scoreLbl" fill="{color_of(score)}">{S["health_label"]}</text></svg>
<div class="sub" style="text-align:center">live-recomputed as you move the controls</div></div>
<div style="flex:1;min-width:280px"><h2 style="margin-top:0;border:none">Health components</h2>{bar_rows}</div>
</div>

<h2>Alerts from this snapshot</h2>
{alerts_html}

<h2>Score history</h2>
{history_html}

<h2>The lab — re-weight the model</h2>
<div class="sub">Weights are policy. The defaults are the published ones (decentralization counts most, at 25%).
Drag them, or try a preset, and the gauge, bars and score above recompute instantly from the same evidence.
Reset restores the author's published model.</div>
<div class="ctl" id="weightCtls"></div>
<div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap">
<button onclick="preset('author')">Author's model</button>
<button onclick="preset('decentralization')">Decentralization maximalist</button>
<button onclick="preset('markets')">Markets only</button>
<button onclick="preset('equal')">Equal weights</button>
</div>
<div class="sub" style="margin-top:8px" id="labNote"></div>

<h2>Another agent, acting on this feed</h2>
<div class="cards">{consumer_html}</div>

<h2>The evidence</h2>
<div class="cards">{cards_html}</div>

<h2>How another agent uses this</h2>
<pre>GET data/status.json
{{
  "health_score": {score}, "health_label": "{S["health_label"]}",
  "components": {{ "cadence": ..., "decentralization": ..., "staking": ..., "throughput": ..., "liquidity": ... }},
  "alerts": [ {{ "component": "...", "kind": "z_score | low_component | label_change", "detail": "..." }} ],
  "evidence": {{ "nakamoto_coefficient": {ev["nakamoto_coefficient"]}, "staked_pct_of_supply": {ev["staked_pct_of_supply"]}, ... }},
  "generated_at": "{S["generated_at"]}"
}}</pre>

<h2>Method &amp; sources</h2>
<ul>
<li>NearBlocks API — supply, price, market cap, volume, lifetime transactions, nodes online, block time.</li>
<li>NEAR mainnet RPC — chain status and the live validator set; stake shares and the Nakamoto coefficient are summed directly.</li>
<li>CoinGecko — market data cross-check (price, market cap, ATH).</li>
<li>Alerts: any component under 40 flags immediately; label changes flag; with ≥5 snapshots of history,
components also flag at |z| ≥ 2 against their own history.</li>
<li>Full methodology, weights rationale and limitations: the repository README. Raw responses: <code>data/snapshot_raw.json</code>.</li>
</ul>

<div class="foot">Re-run the whole system yourself: <code>python3 watchtower.py &amp;&amp; python3 agent_consumer.py &amp;&amp; python3 build_dashboard.py</code> — Python 3 standard library only, no API keys.<br>
Built by team zarroww for the NEAR Hackathon (Agent Economy track). Sibling project: <i>NEAR by the Numbers</i>, a re-runnable investment-thesis model. Research and education only — not financial advice.</div>
</div>
<script>
const FEED = {feed_json};
const EV = FEED.evidence;
const KEYS = ["cadence","decentralization","staking","throughput","liquidity"];
let W = {{...FEED.weights}};
const T = FEED.targets;
function components(){{
  const cadence = Math.max(0, Math.min(100, 100 - Math.abs(EV.avg_block_time_s - T.cadence_s)/T.cadence_s*100));
  const decentr = Math.max(0, Math.min(100, EV.nakamoto_coefficient / T.nakamoto * 100));
  const staking = Math.max(0, Math.min(100, EV.staked_pct_of_supply / T.staked_pct * 100));
  const through = Math.max(0, Math.min(100, EV.blocks_per_day_est / T.blocks_day * 100));
  const liquid  = Math.max(0, Math.min(100, EV.volume_over_market_cap_pct / T.turnover_pct * 100));
  return {{cadence, decentralization: decentr, staking, throughput: through, liquidity: liquid}};
}}
function color(v){{ return v>=75 ? "#3fb950" : v>=55 ? "#d29922" : v>=40 ? "#f0883e" : "#f85149"; }}
function label(v){{ return v>=75 ? "STRONG" : v>=55 ? "STEADY" : v>=40 ? "FRAGILE" : "CRITICAL"; }}
function render(){{
  const C = components();
  const tot = KEYS.reduce((a,k)=>a+W[k],0) || 1;
  let s = 0; KEYS.forEach(k=>{{ s += C[k]*W[k]/tot;
    document.getElementById("bar-"+k).style.width = C[k].toFixed(0)+"%";
    document.getElementById("bar-"+k).style.background = color(C[k]);
    document.getElementById("val-"+k).textContent = C[k].toFixed(1);
    document.getElementById("wv-"+k).textContent = Math.round(W[k]/tot*100)+"%";
  }});
  const L = Math.PI*90;
  const arcEl = document.getElementById("gaugeArc");
  arcEl.setAttribute("stroke-dasharray", (s/100*L).toFixed(1)+" "+L.toFixed(1));
  arcEl.setAttribute("stroke", color(s));
  document.getElementById("scoreNum").textContent = s.toFixed(1);
  const lbl = document.getElementById("scoreLbl");
  lbl.textContent = label(s); lbl.setAttribute("fill", color(s));
  document.getElementById("labNote").textContent =
    "With these weights the score is " + s.toFixed(1) + " (" + label(s) + "). The evidence never changes — only the judgement applied to it.";
}}
const ctl = document.getElementById("weightCtls");
KEYS.forEach(k=>{{
  const d = document.createElement("div");
  d.innerHTML = '<label><span>'+k+'</span><span id="wv-'+k+'"></span></label>'+
    '<input type="range" min="0" max="50" value="'+Math.round(W[k]*100)+'" id="w-'+k+'">';
  ctl.appendChild(d);
  d.querySelector("input").addEventListener("input", e=>{{ W[k] = e.target.value/100; render(); }});
}});
function preset(name){{
  if(name==="author") W = {{...FEED.weights}};
  if(name==="decentralization") W = {{cadence:.05, decentralization:.70, staking:.10, throughput:.05, liquidity:.10}};
  if(name==="markets") W = {{cadence:.05, decentralization:.05, staking:.10, throughput:.05, liquidity:.75}};
  if(name==="equal") W = {{cadence:.2, decentralization:.2, staking:.2, throughput:.2, liquidity:.2}};
  KEYS.forEach(k=>{{ document.getElementById("w-"+k).value = Math.round(W[k]*100); }});
  render();
}}
render();
</script>
</body></html>"""
(ROOT / "index.html").write_text(html)
print("index.html written,", len(html), "bytes; score", score, S["health_label"],
      "| history points:", len(history), "| consumer log entries:", len(agent_log))