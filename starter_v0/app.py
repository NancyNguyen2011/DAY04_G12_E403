"""Streamlit UI for the Day04 research agent.

Reuses `run_model_tool_loop` from chat.py so the UI, the CLI and the eval all drive
the same agent loop over the same artifacts.

The four things a demo has to show:
  1. the request and the final response        -> always visible
  2. per-tool trace: name, args, round, status, result/error
                                               -> "Tool trace" expander
  3. transcript / run / artifact_version       -> header strip + "Metadata" expander
  4. one scenario across several versions      -> "So sánh version" section
"""
from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from chat import ROOT, run_model_tool_loop, safe_slug, trim_history, write_transcript
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version

ARTIFACTS = ROOT / "artifacts"
HISTORY = ARTIFACTS / "history"

# Each label points at the prompt + tool declarations that version actually ran with,
# so a demo can replay one scenario across versions and show the routing change.
#
# Every entry is byte-identical to the artifact its run JSON was produced with —
# verified by sha256 against prompt_hash/tools_hash in runs/*.json. Two versions
# share a file whenever that round changed the other artifact, which is what makes
# the one-variable-at-a-time discipline visible here.
ARTIFACT_SETS: dict[str, tuple[Path, Path]] = {
    "v0 — baseline (base .65)": (HISTORY / "system_prompt.v0.md", HISTORY / "tools.v0.yaml"),
    "v1 — prompt: boundary (base .85)": (HISTORY / "system_prompt.v1.md", HISTORY / "tools.v0.yaml"),
    "v2 — tools: arg convention (base .90)": (HISTORY / "system_prompt.v1.md", HISTORY / "tools.v2.yaml"),
    "v3 — prompt: clarify limits (base .95)": (HISTORY / "system_prompt.v3.md", HISTORY / "tools.v2.yaml"),
    "v4 — prompt: multi-tool (base .95)": (HISTORY / "system_prompt.v4.md", HISTORY / "tools.v2.yaml"),
    "v5 — tools: +4 team tools (base .95)": (HISTORY / "system_prompt.v4.md", HISTORY / "tools.v5.yaml"),
    "v7 — prompt: derive args (group .80)": (HISTORY / "system_prompt.v7.md", HISTORY / "tools.v5.yaml"),
    "v8 — prompt: scope first (group .90)": (HISTORY / "system_prompt.v8.md", HISTORY / "tools.v5.yaml"),
    "current": (ARTIFACTS / "system_prompt.md", ARTIFACTS / "tools.yaml"),
}

st.set_page_config(page_title="Research Agent", page_icon="✳", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap');

/* Surfaces follow Streamlit's active theme (config.toml pins the brand palette),
   so nothing depends on the viewer's light/dark toggle. Brand hexes are the
   fallback. The dark surfaces below are fixed by design — the tool trace is the
   design system's code-window-card and stays dark in both modes, so its text is
   set against that dark, never against the page. */
:root {
  --canvas: var(--background-color, #faf9f5);
  --surface-card: var(--secondary-background-color, #efe9de);
  --ink: var(--text-color, #141413);
  --hairline: var(--border-color, #e6dfd8);
  --surface-dark:#181715; --surface-dark-soft:#1f1e1b; --surface-dark-elevated:#252320;
  --primary:#cc785c; --primary-active:#a9583e;
  --on-dark:#faf9f5; --on-dark-soft:#cfcac1; --on-dark-label:#a8a49b;
  --success:#7fd191; --error:#e08a8a; --teal:#7fcfc0;
  --serif:'Cormorant Garamond','Tiempos Headline',Garamond,'Times New Roman',serif;
  --sans:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
}

html, body, [class*="css"] { font-family:var(--sans); }

.brand { display:flex; align-items:baseline; gap:12px; margin-bottom:4px; }
.brand-mark { color:var(--ink); font-size:22px; line-height:1; }
.brand h1 { font-family:var(--serif); font-weight:500; font-size:44px; line-height:1.1;
            letter-spacing:-1px; color:var(--ink); margin:0; }
.brand-sub { color:var(--ink); opacity:.66; font-size:14px; margin:0 0 20px 2px; }

.turn-user { background:var(--surface-card); border-radius:12px; padding:16px 20px;
             color:var(--ink); font-size:16px; line-height:1.55; margin:24px 0 12px; }
.turn-user .lbl { font-size:12px; font-weight:500; letter-spacing:1.5px; text-transform:uppercase;
                  color:var(--ink); opacity:.62; display:block; margin-bottom:6px; }

.answer { background:var(--canvas); border:1px solid var(--hairline); border-radius:12px;
          padding:20px 24px; color:var(--ink); font-size:16px; line-height:1.55; margin:0 0 8px; }
.answer .lbl { font-size:12px; font-weight:500; letter-spacing:1.5px; text-transform:uppercase;
               color:var(--primary-active); display:block; margin-bottom:8px; }

.trace { background:var(--surface-dark); border-radius:12px; padding:18px 20px; margin:4px 0 10px; }
.trace-head { display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.trace-round { font-family:var(--mono); font-size:12px; color:var(--on-dark-soft); }
.tool { background:var(--surface-dark-soft); border-radius:8px; padding:14px 16px; margin-bottom:10px; }
.tool:last-child { margin-bottom:0; }
.tool-name { font-family:var(--mono); font-size:14px; color:var(--on-dark); }
/* Streamlit rewrites <pre> into div[data-testid="stMarkdownPre"] carrying its own
   emotion class themed for the light canvas. Both selectors are needed or the JSON
   renders in near-black on the dark card. */
.tool pre,
.tool [data-testid="stMarkdownPre"],
.tool [data-testid="stMarkdownPre"] code {
            font-family:var(--mono) !important; font-size:12.5px !important; line-height:1.6;
            color:var(--on-dark-soft) !important;
            background:var(--surface-dark-elevated) !important; border-radius:6px;
            margin:8px 0 0; overflow-x:auto; white-space:pre; }
.tool [data-testid="stMarkdownPre"] { padding:10px 12px !important; }
.tool [data-testid="stMarkdownPre"] code { padding:0 !important; }
.tool .k { font-size:11px; letter-spacing:1.2px; text-transform:uppercase; color:var(--on-dark-label); }

.pill { display:inline-block; font-size:12px; font-weight:500; letter-spacing:1.5px;
        text-transform:uppercase; border-radius:9999px; padding:3px 12px; }
.pill-ok { background:rgba(127,209,145,.18); color:var(--success); }
.pill-err { background:rgba(224,138,138,.18); color:var(--error); }
.pill-wait { background:rgba(127,207,192,.18); color:var(--teal); }
/* White on #cc785c is only 3.3:1 — below AA for a 12px label. The design system's
   press-state coral is the same family and clears the bar at 5.6:1. */
.pill-coral { background:var(--primary-active); color:#fff; }

.meta { font-family:var(--mono); font-size:12px; color:var(--ink); opacity:.6; margin-top:6px; }
.metagrid { display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:10px 20px; }
.metagrid div { font-family:var(--mono); font-size:12.5px; color:var(--ink); }
.metagrid b { font-weight:500; opacity:.55; display:block; font-size:11px;
              letter-spacing:1.2px; text-transform:uppercase; }

.section-h { font-family:var(--serif); font-weight:500; font-size:28px; letter-spacing:-.3px;
             color:var(--ink); margin:28px 0 2px; }
.section-sub { color:var(--ink); opacity:.66; font-size:14px; margin:0 0 14px; }

/* Expander: cream card with hairline, matching feature-card in the design system. */
[data-testid="stExpander"] { border:1px solid var(--hairline) !important; border-radius:12px !important;
                             background:var(--canvas) !important; margin-bottom:10px; }
[data-testid="stExpander"] summary { font-family:var(--sans) !important; font-size:14px !important;
                                     font-weight:500 !important; color:var(--ink) !important; }
[data-testid="stExpander"] summary p { font-size:14px !important; font-weight:500 !important; }

[data-testid="stSidebar"] h2 { font-family:var(--serif); font-weight:500; font-size:22px;
                               letter-spacing:-.3px; color:var(--ink); }
.stButton>button { background:var(--primary); color:#fff; border:none; border-radius:8px;
                   font-weight:500; font-size:14px; height:40px; }
.stButton>button:hover { background:var(--primary); color:#fff; }
.stButton>button:active { background:var(--primary-active); }
hr { border-color:var(--hairline); }
</style>
""",
    unsafe_allow_html=True,
)


def esc(value: Any) -> str:
    return html.escape(json.dumps(value, ensure_ascii=False, indent=2, default=str))


def status_pill(result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return '<span class="pill pill-ok">ok</span>'
    if result.get("error"):
        return f'<span class="pill pill-err">{html.escape(str(result["error"]))}</span>'
    if result.get("awaiting_user"):
        return '<span class="pill pill-wait">awaiting user</span>'
    if result.get("status"):
        return f'<span class="pill pill-wait">{html.escape(str(result["status"]))}</span>'
    return '<span class="pill pill-ok">ok</span>'


def trace_html(rounds: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for record in rounds:
        if not record.get("tool_calls"):
            continue
        blocks += [
            '<div class="trace">',
            f'<div class="trace-head"><span class="pill pill-coral">round {record["round"]}</span>'
            f'<span class="trace-round">{len(record["tool_calls"])} tool call(s)</span></div>',
        ]
        for event in record.get("tool_results", []):
            result = event.get("result", {})
            blocks.append(
                '<div class="tool">'
                f'<div class="tool-name">{html.escape(str(event.get("tool")))} {status_pill(result)}</div>'
                '<div class="k" style="margin-top:10px">arguments</div>'
                f'<pre>{esc(event.get("args", {}))}</pre>'
                '<div class="k" style="margin-top:10px">result</div>'
                f'<pre>{esc(result)[:2500]}</pre>'
                '</div>'
            )
        blocks.append("</div>")
    return "".join(blocks)


def call_summary(rounds: list[dict[str, Any]]) -> str:
    names = [call["name"] for record in rounds for call in record.get("tool_calls", [])]
    return ", ".join(names) if names else "không gọi tool"


def render_turn(turn: dict[str, Any], key: str) -> None:
    st.markdown(
        f'<div class="turn-user"><span class="lbl">Request</span>{html.escape(turn["user"])}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="answer"><span class="lbl">Response</span>{html.escape(turn["assistant_text"])}</div>',
        unsafe_allow_html=True,
    )
    rounds = turn.get("rounds", [])
    call_count = sum(len(r.get("tool_calls", [])) for r in rounds)
    with st.expander(f"Tool trace — {call_count} tool call · {len(rounds)} round · {call_summary(rounds)}"):
        if call_count:
            st.markdown(trace_html(rounds), unsafe_allow_html=True)
        else:
            st.markdown('<div class="meta">Lượt này không gọi tool nào.</div>', unsafe_allow_html=True)
    with st.expander(f"Metadata — {turn.get('artifact_version', '')}"):
        st.markdown(
            '<div class="metagrid">'
            f'<div><b>artifact_version</b>{html.escape(str(turn.get("artifact_version", "")))}</div>'
            f'<div><b>prompt_hash</b>{html.escape(str(turn.get("prompt_hash", "")))}</div>'
            f'<div><b>tools_hash</b>{html.escape(str(turn.get("tools_hash", "")))}</div>'
            f'<div><b>prompt file</b>{html.escape(str(turn.get("prompt_file", "")))}</div>'
            f'<div><b>tools file</b>{html.escape(str(turn.get("tools_file", "")))}</div>'
            f'<div><b>provider / model</b>{html.escape(str(turn.get("provider", "")))} · '
            f'{html.escape(str(turn.get("model") or "default"))}</div>'
            f'<div><b>status</b>{html.escape(str(turn.get("status", "")))}</div>'
            f'<div><b>transcript</b>{html.escape(str(turn.get("transcript", "")))}</div>'
            '</div>',
            unsafe_allow_html=True,
        )


def load_artifacts(label: str):
    prompt_path, tools_path = ARTIFACT_SETS[label]
    missing = [p.name for p in (prompt_path, tools_path) if not p.exists()]
    if missing:
        return None
    declarations = load_tool_declarations(tools_path)
    return {
        "prompt_path": prompt_path,
        "tools_path": tools_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8"),
        "declarations": declarations,
        "openai_tools": to_openai_tools(declarations),
    }


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.markdown("## Cấu hình")
    provider_name = st.selectbox("Provider", ["nvidia", "openrouter", "openai", "anthropic", "gemini"])
    model_override = st.text_input("Model (bỏ trống = mặc định)", value="")
    artifact_label = st.selectbox("Artifact version", list(ARTIFACT_SETS), index=len(ARTIFACT_SETS) - 1)
    version_label = st.text_input("Nhãn version ghi vào transcript", value=artifact_label.split(" ")[0])
    max_rounds = st.slider("Max tool rounds", 1, 6, 4)
    history_window = st.slider("History window (số cặp lượt)", 0, 10, 5)
    if st.button("Xoá hội thoại"):
        for key in ("turns", "history", "transcript", "transcript_path", "comparison"):
            st.session_state.pop(key, None)
        st.rerun()

active = load_artifacts(artifact_label)
if active is None:
    st.error(f"Thiếu artifact cho {artifact_label}")
    st.stop()

artifact_version = build_artifact_version(version_label or "ui", active["prompt_path"], active["tools_path"])

# ---------------------------------------------------------------- header
st.markdown(
    '<div class="brand"><span class="brand-mark">✳</span><h1>Research Agent</h1></div>'
    '<p class="brand-sub">Tìm tin theo chủ đề hoặc theo tài khoản, đọc URL, tìm repo và tra khái niệm '
    '— mỗi lượt mở được tool trace và metadata đầy đủ.</p>',
    unsafe_allow_html=True,
)

st.session_state.setdefault("turns", [])
st.session_state.setdefault("history", [])
st.session_state.setdefault("comparison", None)

if "transcript_path" not in st.session_state:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    transcript_id = "_".join([safe_slug(version_label or "ui"), "ui", safe_slug(provider_name), stamp])
    st.session_state.transcript_path = ROOT / "transcripts" / f"{transcript_id}.transcript.json"
    st.session_state.transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact_version),
        "surface": "streamlit_ui",
        "provider": provider_name,
        "model": model_override or None,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "turns": [],
        "comparisons": [],
    }

st.markdown(
    f'<div class="meta">artifact_version <b>{artifact_version.artifact_version}</b> · '
    f'{active["prompt_path"].name} + {active["tools_path"].name} · '
    f'{len(active["declarations"])} tool · {provider_name} / {model_override or "default"} · '
    f'transcript {st.session_state.transcript_path.name}</div>',
    unsafe_allow_html=True,
)

for index, turn in enumerate(st.session_state.turns):
    render_turn(turn, key=f"turn{index}")


def run_once(bundle: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    return run_model_tool_loop(
        provider=make_provider(provider_name),
        messages=messages,
        tools=bundle["openai_tools"],
        model=model_override or None,
        max_tool_rounds=max_rounds,
    )


user_text = st.chat_input("Ví dụ: Tin AI hôm nay có gì nổi bật?")
if user_text:
    messages = [
        {"role": "system", "content": active["system_prompt"]},
        *trim_history(st.session_state.history, history_window),
        {"role": "user", "content": user_text},
    ]
    try:
        with st.spinner("Agent đang chọn tool..."):
            result = run_once(active, messages)
        turn = {
            "user": user_text,
            **result,
            **artifact_version_dict(artifact_version),
            "prompt_file": active["prompt_path"].name,
            "tools_file": active["tools_path"].name,
            "provider": provider_name,
            "model": model_override or None,
            "transcript": st.session_state.transcript_path.name,
        }
        st.session_state.turns.append(turn)
        st.session_state.history += [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": result["assistant_text"]},
        ]
        st.session_state.transcript["turns"].append({"turn_index": len(st.session_state.turns), **turn})
        write_transcript(st.session_state.transcript_path, st.session_state.transcript)
        st.rerun()
    except Exception as exc:
        st.error(f"{type(exc).__name__}: {exc}")

# ---------------------------------------------------------------- version comparison
st.markdown('<div class="section-h">So sánh version</div>', unsafe_allow_html=True)
st.markdown(
    '<p class="section-sub">Chạy cùng một scenario qua nhiều artifact version để thấy routing đổi ở đâu. '
    'Mỗi version dùng đúng prompt + tool declarations của version đó.</p>',
    unsafe_allow_html=True,
)

scenario = st.text_input(
    "Scenario",
    value="Đăng bản tin AI hôm nay lên Telegram giúp mình",
    help="Câu này sẽ được gửi tới từng version đã chọn, không mang theo lịch sử hội thoại.",
)
compare_labels = st.multiselect(
    "Version cần so sánh",
    list(ARTIFACT_SETS),
    default=["v0 — baseline (base .65)", "current"],
)

if st.button("Chạy so sánh") and scenario and compare_labels:
    rows: list[dict[str, Any]] = []
    progress = st.progress(0.0)
    for position, label in enumerate(compare_labels, start=1):
        bundle = load_artifacts(label)
        if bundle is None:
            rows.append({"version": label, "error": "thiếu artifact"})
            continue
        version = build_artifact_version(label.split(" ")[0], bundle["prompt_path"], bundle["tools_path"])
        try:
            outcome = run_once(bundle, [
                {"role": "system", "content": bundle["system_prompt"]},
                {"role": "user", "content": scenario},
            ])
            rows.append({
                "version": label,
                "artifact_version": version.artifact_version,
                "tools": call_summary(outcome["rounds"]),
                "status": outcome["status"],
                "assistant_text": outcome["assistant_text"],
                "rounds": outcome["rounds"],
            })
        except Exception as exc:
            rows.append({"version": label, "error": f"{type(exc).__name__}: {exc}"})
        progress.progress(position / len(compare_labels))
    progress.empty()
    st.session_state.comparison = {"scenario": scenario, "rows": rows,
                                   "ran_at": datetime.now().isoformat(timespec="seconds")}
    st.session_state.transcript["comparisons"].append({
        "scenario": scenario,
        "ran_at": st.session_state.comparison["ran_at"],
        "rows": [{k: v for k, v in row.items() if k != "rounds"} for row in rows],
    })
    write_transcript(st.session_state.transcript_path, st.session_state.transcript)

if st.session_state.comparison:
    comparison = st.session_state.comparison
    st.markdown(
        f'<div class="meta">scenario: "{html.escape(comparison["scenario"])}" · {comparison["ran_at"]}</div>',
        unsafe_allow_html=True,
    )
    st.table([
        {
            "Version": row["version"],
            "Tool được gọi": row.get("tools", row.get("error", "")),
            "Status": row.get("status", ""),
            "artifact_version": row.get("artifact_version", ""),
        }
        for row in comparison["rows"]
    ])
    for row in comparison["rows"]:
        if "rounds" not in row:
            continue
        with st.expander(f'{row["version"]} — trace + response'):
            st.markdown(
                f'<div class="answer"><span class="lbl">Response</span>'
                f'{html.escape(row["assistant_text"])}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(trace_html(row["rounds"]) or
                        '<div class="meta">Không gọi tool nào.</div>', unsafe_allow_html=True)
