"""Streamlit UI for the Day04 research agent.

Reuses `run_model_tool_loop` from chat.py so the UI, the CLI and the eval all drive
the same agent loop over the same artifacts.

The four things a demo has to show:
  1. the request and the final response        -> always visible
  2. per-tool trace: name, args, round, status, result/error
                                               -> "Tool trace" expander
  3. transcript / run / artifact_version       -> hero artifact card + Metadata expander
  4. one scenario across several versions      -> coral "So sánh version" band
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

# (prompt, tools, pinned model | None). Every file is byte-identical to the artifact
# its run JSON was produced with — verified by sha256 against prompt_hash/tools_hash
# in runs/*.json. Two versions share a file whenever that round changed the other
# artifact, which is what makes the one-variable-at-a-time discipline visible here.
#
# v6 is the odd one out: it changed no artifact at all. It reruns v5's exact prompt
# and tools against a different model, so it pins the model instead. That is what
# turns it into a controlled experiment — and why it needs a model slot here rather
# than an artifact slot.
NEMOTRON = "nvidia/llama-3.3-nemotron-super-49b-v1.5"

ARTIFACT_SETS: dict[str, tuple[Path, Path, str | None]] = {
    "v0 — baseline (base .65)": (HISTORY / "system_prompt.v0.md", HISTORY / "tools.v0.yaml", None),
    "v1 — prompt: boundary (base .85)": (HISTORY / "system_prompt.v1.md", HISTORY / "tools.v0.yaml", None),
    "v2 — tools: arg convention (base .90)": (HISTORY / "system_prompt.v1.md", HISTORY / "tools.v2.yaml", None),
    "v3 — prompt: clarify limits (base .95)": (HISTORY / "system_prompt.v3.md", HISTORY / "tools.v2.yaml", None),
    "v4 — prompt: multi-tool (base .95)": (HISTORY / "system_prompt.v4.md", HISTORY / "tools.v2.yaml", None),
    "v5 — tools: +4 team tools (base .95)": (HISTORY / "system_prompt.v4.md", HISTORY / "tools.v5.yaml", None),
    "v6 — model swap: nemotron (base .85)": (HISTORY / "system_prompt.v4.md", HISTORY / "tools.v5.yaml", NEMOTRON),
    "v7 — prompt: derive args (group .80)": (HISTORY / "system_prompt.v7.md", HISTORY / "tools.v5.yaml", None),
    "v8 — prompt: scope first (group .90)": (HISTORY / "system_prompt.v8.md", HISTORY / "tools.v5.yaml", None),
    "current": (ARTIFACTS / "system_prompt.md", ARTIFACTS / "tools.yaml", None),
}

# Anthropic's radial spike mark: four tapered blades, widest away from the centre.
SPIKE = (
    '<svg viewBox="0 0 24 24" width="26" height="26" aria-hidden="true" class="spike">'
    '<g fill="currentColor">'
    '<path d="M12 1.6 13.7 10.4 12 12.4 10.3 10.4Z"/>'
    '<path d="M22.4 12 13.6 13.7 11.6 12 13.6 10.3Z"/>'
    '<path d="M12 22.4 10.3 13.6 12 11.6 13.7 13.6Z"/>'
    '<path d="M1.6 12 10.4 10.3 12.4 12 10.4 13.7Z"/>'
    "</g></svg>"
)

st.set_page_config(page_title="Research Agent", page_icon="✳", layout="wide")

st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400;500&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400&display=swap');

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
  --surface-soft:#f5f0e8; --surface-cream-strong:#e8e0d2;
  --surface-dark:#181715; --surface-dark-soft:#1f1e1b; --surface-dark-elevated:#252320;
  --primary:#cc785c; --primary-active:#a9583e;
  --on-dark:#faf9f5; --on-dark-soft:#cfcac1; --on-dark-label:#a8a49b;
  --success:#7fd191; --error:#e08a8a; --teal:#7fcfc0;
  --serif:'Cormorant Garamond','Tiempos Headline',Garamond,'Times New Roman',serif;
  --sans:Inter,-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --mono:'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace;
  /* spacing scale: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 96 */
  --sp-lg:24px; --sp-xl:32px; --sp-xxl:48px; --sp-section:96px;
}

html, body, [class*="css"] { font-family:var(--sans); }
.block-container { padding-top:2.2rem !important; max-width:1200px; }

/* ---------- hero ---------- */
.hero { padding:8px 0 var(--sp-xl); }
.brand { display:flex; align-items:center; gap:12px; margin-bottom:14px; color:var(--ink); }
.brand .spike { flex:none; }
.brand-word { font-family:var(--sans); font-size:12px; font-weight:500; letter-spacing:1.5px;
              text-transform:uppercase; color:var(--ink); opacity:.72; }
.hero h1 { font-family:var(--serif); font-weight:400; font-size:56px; line-height:1.05;
           letter-spacing:-1.5px; color:var(--ink); margin:0 0 14px; }
.hero p { font-size:16px; line-height:1.55; color:var(--ink); opacity:.7; margin:0; max-width:52ch; }

/* Artifact card — cream feature card, 32px padding per the spacing scale. */
.artifact-card { background:var(--surface-card); border-radius:12px; padding:var(--sp-xl); }
.artifact-card .eyebrow { font-size:12px; font-weight:500; letter-spacing:1.5px; text-transform:uppercase;
                          color:var(--ink); opacity:.72; margin-bottom:10px; }
.artifact-card .big { font-family:var(--mono); font-size:15px; color:var(--ink);
                      word-break:break-all; line-height:1.5; margin-bottom:18px; }
.kv { display:grid; grid-template-columns:auto 1fr; gap:7px 16px; font-size:13px; }
.kv dt { font-size:11px; letter-spacing:1.2px; text-transform:uppercase; color:var(--ink);
         opacity:.72; white-space:nowrap; padding-top:2px; }
.kv dd { margin:0; font-family:var(--mono); font-size:12.5px; color:var(--ink); word-break:break-all; }

/* ---------- conversation ---------- */
.rule { height:1px; background:var(--hairline); border:0; margin:var(--sp-xxl) 0 var(--sp-lg); }

.turn-user { background:var(--surface-card); border-radius:12px; padding:var(--sp-xl);
             color:var(--ink); font-size:17px; line-height:1.5; margin:var(--sp-lg) 0 14px; }
.turn-user .lbl, .answer .lbl { font-size:12px; font-weight:500; letter-spacing:1.5px;
                                text-transform:uppercase; display:block; margin-bottom:10px; }
.turn-user .lbl { color:var(--ink); opacity:.72; }

.answer { background:var(--canvas); border:1px solid var(--hairline); border-radius:12px;
          padding:var(--sp-xl); color:var(--ink); font-size:16px; line-height:1.6; margin:0 0 10px; }
.answer .lbl { color:var(--primary-active); }
.answer table { border-collapse:collapse; margin:12px 0; font-size:14px; }
.answer th, .answer td { border:1px solid var(--hairline); padding:7px 11px; text-align:left; }

/* ---------- tool trace: the design system's dark code-window card ---------- */
.trace { background:var(--surface-dark); border-radius:12px; padding:var(--sp-lg); margin:2px 0 8px; }
.trace-head { display:flex; align-items:center; gap:10px; margin-bottom:16px; }
.trace-round { font-family:var(--mono); font-size:12px; color:var(--on-dark-soft); }
.tool { background:var(--surface-dark-soft); border-radius:8px; padding:16px 18px; margin-bottom:10px; }
.tool:last-child { margin-bottom:0; }
.tool-name { font-family:var(--mono); font-size:14px; color:var(--on-dark);
             display:flex; align-items:center; gap:10px; }
/* Streamlit rewrites <pre> into div[data-testid="stMarkdownPre"] carrying its own
   emotion class themed for the light canvas. Both selectors are needed or the JSON
   renders in near-black on the dark card. */
.tool pre,
.tool [data-testid="stMarkdownPre"],
.tool [data-testid="stMarkdownPre"] code {
            font-family:var(--mono) !important; font-size:12.5px !important; line-height:1.65;
            color:var(--on-dark-soft) !important;
            background:var(--surface-dark-elevated) !important; border-radius:6px;
            margin:8px 0 0; overflow-x:auto; white-space:pre; }
.tool [data-testid="stMarkdownPre"] { padding:12px 14px !important; }
.tool [data-testid="stMarkdownPre"] code { padding:0 !important; }
.tool .k { font-size:11px; letter-spacing:1.2px; text-transform:uppercase;
           color:var(--on-dark-label); margin-top:14px; }

.pill { display:inline-block; font-size:12px; font-weight:500; letter-spacing:1.5px;
        text-transform:uppercase; border-radius:9999px; padding:3px 12px; }
.pill-ok { background:rgba(127,209,145,.18); color:var(--success); }
.pill-err { background:rgba(224,138,138,.18); color:var(--error); }
.pill-wait { background:rgba(127,207,192,.18); color:var(--teal); }
/* White on #cc785c is only 3.3:1 — below AA for a 12px label. The design system's
   press-state coral is the same family and clears the bar at 5.6:1. */
.pill-coral { background:var(--primary-active); color:#fff; }

.meta { font-family:var(--mono); font-size:12px; color:var(--ink); opacity:.72; }

/* ---------- coral callout: the page's one voltage moment ----------
   The design system paints this card in --primary, but white on #cc785c is 3.3:1 —
   fine for the 36px serif head (large-text AA is 3:1), too low for the 15px body
   copy. Dropping to the press-state coral keeps it unmistakably coral, stays inside
   the palette, and puts both head and body at 5.06:1. */
.callout { background:var(--primary-active); border-radius:12px; padding:var(--sp-xxl);
           margin:var(--sp-section) 0 var(--sp-lg); }
.callout h2 { font-family:var(--serif); font-weight:400; font-size:36px; line-height:1.15;
              letter-spacing:-.5px; color:#fff; margin:0 0 12px; }
.callout p { color:#fff; font-size:15px; line-height:1.55; margin:0; max-width:62ch; }

.section-h { font-family:var(--serif); font-weight:400; font-size:28px; letter-spacing:-.3px;
             color:var(--ink); margin:var(--sp-xl) 0 4px; }

/* ---------- expanders: cream feature cards ---------- */
[data-testid="stExpander"] { border:1px solid var(--hairline) !important; border-radius:12px !important;
                             background:var(--canvas) !important; margin-bottom:10px; }
[data-testid="stExpander"] summary { font-family:var(--sans) !important; font-size:14px !important;
                                     font-weight:500 !important; color:var(--ink) !important;
                                     padding:14px 18px !important; }
[data-testid="stExpander"] summary p { font-size:14px !important; font-weight:500 !important; }

/* ---------- empty state ---------- */
.empty { border:1px dashed var(--hairline); border-radius:12px; padding:var(--sp-xxl) var(--sp-xl);
         text-align:center; }
.empty h3 { font-family:var(--serif); font-weight:400; font-size:26px; letter-spacing:-.3px;
            color:var(--ink); margin:0 0 8px; }
.empty p { color:var(--ink); opacity:.62; font-size:14px; margin:0 0 18px; }
.chips { display:flex; flex-wrap:wrap; gap:8px; justify-content:center; }
.chip { background:var(--surface-card); border-radius:9999px; padding:7px 16px;
        font-size:13px; color:var(--ink); }

/* ---------- footer: dark band, never inverts ---------- */
.footer { background:var(--surface-dark); border-radius:12px; padding:var(--sp-xl);
          margin-top:var(--sp-section); display:flex; flex-wrap:wrap; gap:28px 56px; }
.footer .col b { display:block; font-size:11px; letter-spacing:1.5px; text-transform:uppercase;
                 color:var(--on-dark-label); margin-bottom:7px; font-weight:500; }
.footer .col span { font-family:var(--mono); font-size:12.5px; color:var(--on-dark); }
.footer .mark { color:var(--on-dark); display:flex; align-items:center; gap:10px;
                font-size:12px; letter-spacing:1.5px; text-transform:uppercase; }

/* ---------- sidebar + controls ---------- */
[data-testid="stSidebar"] h2 { font-family:var(--serif); font-weight:400; font-size:26px;
                               letter-spacing:-.3px; color:var(--ink); }
.stButton>button { background:var(--primary); color:#fff; border:none; border-radius:8px;
                   font-weight:500; font-size:14px; height:40px; }
.stButton>button:hover { background:var(--primary); color:#fff; }
.stButton>button:active { background:var(--primary-active); }
table { font-size:14px; }
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
                f'<div class="tool-name">{html.escape(str(event.get("tool")))}{status_pill(result)}</div>'
                '<div class="k">arguments</div>'
                f'<pre>{esc(event.get("args", {}))}</pre>'
                '<div class="k">result</div>'
                f'<pre>{esc(result)[:2500]}</pre>'
                "</div>"
            )
        blocks.append("</div>")
    return "".join(blocks)


def call_summary(rounds: list[dict[str, Any]]) -> str:
    names = [call["name"] for record in rounds for call in record.get("tool_calls", [])]
    return " → ".join(names) if names else "không gọi tool"


def render_turn(turn: dict[str, Any]) -> None:
    st.markdown(
        f'<div class="turn-user"><span class="lbl">Request</span>{html.escape(turn["user"])}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="answer"><span class="lbl">Response</span>{html.escape(turn["assistant_text"])}</div>',
        unsafe_allow_html=True,
    )
    rounds = turn.get("rounds", [])
    calls = sum(len(r.get("tool_calls", [])) for r in rounds)
    with st.expander(f"Tool trace · {calls} call · {len(rounds)} round · {call_summary(rounds)}"):
        st.markdown(
            trace_html(rounds) or '<div class="meta">Lượt này không gọi tool nào.</div>',
            unsafe_allow_html=True,
        )
    with st.expander(f"Metadata · {turn.get('artifact_version', '')}"):
        st.markdown(
            '<dl class="kv">'
            f'<dt>artifact</dt><dd>{html.escape(str(turn.get("artifact_version", "")))}</dd>'
            f'<dt>prompt hash</dt><dd>{html.escape(str(turn.get("prompt_hash", "")))}</dd>'
            f'<dt>tools hash</dt><dd>{html.escape(str(turn.get("tools_hash", "")))}</dd>'
            f'<dt>prompt file</dt><dd>{html.escape(str(turn.get("prompt_file", "")))}</dd>'
            f'<dt>tools file</dt><dd>{html.escape(str(turn.get("tools_file", "")))}</dd>'
            f'<dt>provider</dt><dd>{html.escape(str(turn.get("provider", "")))} · '
            f'{html.escape(str(turn.get("model") or "default"))}</dd>'
            f'<dt>status</dt><dd>{html.escape(str(turn.get("status", "")))}</dd>'
            f'<dt>transcript</dt><dd>{html.escape(str(turn.get("transcript", "")))}</dd>'
            "</dl>",
            unsafe_allow_html=True,
        )


def load_artifacts(label: str, fallback_model: str | None = None):
    prompt_path, tools_path, pinned_model = ARTIFACT_SETS[label]
    if not (prompt_path.exists() and tools_path.exists()):
        return None
    declarations = load_tool_declarations(tools_path)
    return {
        "prompt_path": prompt_path,
        "tools_path": tools_path,
        "system_prompt": prompt_path.read_text(encoding="utf-8"),
        "declarations": declarations,
        "openai_tools": to_openai_tools(declarations),
        # A version that pins a model always wins over the sidebar box — otherwise
        # picking v6 would silently run it on the wrong model and the experiment
        # would mean nothing.
        "model": pinned_model or fallback_model or None,
        "model_pinned": pinned_model is not None,
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

active = load_artifacts(artifact_label, model_override or None)
if active is None:
    st.error(f"Thiếu artifact cho {artifact_label}")
    st.stop()
if active["model_pinned"]:
    st.sidebar.info(f"Version này ghim model `{active['model']}`, bỏ qua ô Model ở trên.")

artifact_version = build_artifact_version(version_label or "ui", active["prompt_path"], active["tools_path"])

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
        "model": active["model"],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "turns": [],
        "comparisons": [],
    }

# ---------------------------------------------------------------- hero band
hero, card = st.columns([1.15, 1], gap="large")
with hero:
    st.markdown(
        f'<div class="hero">'
        f'<div class="brand">{SPIKE}<span class="brand-word">AI20k · Day 04</span></div>'
        f"<h1>Research Agent</h1>"
        f"<p>Tìm tin theo chủ đề hoặc theo tài khoản, đọc một URL, tìm repo open-source "
        f"và tra khái niệm — rồi tổng hợp lại. Mỗi lượt mở được tool trace đầy đủ và "
        f"metadata của đúng artifact version đang chạy.</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
with card:
    st.markdown(
        '<div class="artifact-card">'
        '<div class="eyebrow">Artifact đang chạy</div>'
        f'<div class="big">{html.escape(artifact_version.artifact_version)}</div>'
        '<dl class="kv">'
        f'<dt>prompt</dt><dd>{html.escape(active["prompt_path"].name)}</dd>'
        f'<dt>tools</dt><dd>{html.escape(active["tools_path"].name)} · {len(active["declarations"])} tool</dd>'
        f'<dt>provider</dt><dd>{html.escape(provider_name)}</dd>'
        f'<dt>model</dt><dd>{html.escape(active["model"] or "default")}'
        f'{" · ghim theo version" if active["model_pinned"] else ""}</dd>'
        f'<dt>transcript</dt><dd>{html.escape(st.session_state.transcript_path.name)}</dd>'
        "</dl></div>",
        unsafe_allow_html=True,
    )

st.markdown('<hr class="rule">', unsafe_allow_html=True)

# ---------------------------------------------------------------- conversation
if not st.session_state.turns:
    st.markdown(
        '<div class="empty">'
        "<h3>Thử một câu để bắt đầu</h3>"
        "<p>Agent sẽ chọn tool, chạy thật, rồi hiện toàn bộ trace bên dưới câu trả lời.</p>"
        '<div class="chips">'
        '<span class="chip">Tin AI hôm nay có gì nổi bật?</span>'
        '<span class="chip">Có thư viện open-source nào để crawl web không?</span>'
        '<span class="chip">Retrieval augmented generation là gì?</span>'
        '<span class="chip">Tóm tắt 5 tweet mới nhất giúp mình</span>'
        "</div></div>",
        unsafe_allow_html=True,
    )

for turn in st.session_state.turns:
    render_turn(turn)


def run_once(bundle: dict[str, Any], messages: list[dict[str, str]]) -> dict[str, Any]:
    return run_model_tool_loop(
        provider=make_provider(provider_name),
        messages=messages,
        tools=bundle["openai_tools"],
        model=bundle["model"],
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
            "model": active["model"],
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

# ---------------------------------------------------------------- coral callout
st.markdown(
    '<div class="callout">'
    "<h2>So sánh version</h2>"
    "<p>Chạy cùng một scenario qua nhiều artifact version để thấy routing đổi ở đâu. "
    "Mỗi version dùng đúng prompt và tool declarations của chính nó, nên khác biệt trên "
    "bảng là khác biệt thật chứ không phải do câu hỏi khác nhau. Chọn v5 cùng v6 để so "
    "hai model trên cùng một artifact — đó là cách R13 được chứng minh là giới hạn của "
    "model chứ không phải lỗi prompt.</p>"
    "</div>",
    unsafe_allow_html=True,
)

scenario = st.text_input(
    "Scenario",
    value="Đăng bản tin AI hôm nay lên Telegram giúp mình",
    help="Câu này được gửi tới từng version đã chọn, không mang theo lịch sử hội thoại.",
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
        bundle = load_artifacts(label, model_override or None)
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
                "model": bundle["model"] or "default",
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
        f'<div class="section-h">Kết quả</div>'
        f'<div class="meta">"{html.escape(comparison["scenario"])}" · {comparison["ran_at"]}</div>',
        unsafe_allow_html=True,
    )
    st.table([
        {
            "Version": row["version"],
            "Model": row.get("model", ""),
            "Tool được gọi": row.get("tools", row.get("error", "")),
            "Status": row.get("status", ""),
            "artifact_version": row.get("artifact_version", ""),
        }
        for row in comparison["rows"]
    ])
    for row in comparison["rows"]:
        if "rounds" not in row:
            continue
        with st.expander(f'{row["version"]} · trace + response'):
            st.markdown(
                f'<div class="answer"><span class="lbl">Response</span>'
                f'{html.escape(row["assistant_text"])}</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                trace_html(row["rounds"]) or '<div class="meta">Không gọi tool nào.</div>',
                unsafe_allow_html=True,
            )

# ---------------------------------------------------------------- footer
st.markdown(
    '<div class="footer">'
    f'<div class="mark">{SPIKE}<span>Research Agent</span></div>'
    f'<div class="col"><b>artifact</b><span>{html.escape(artifact_version.artifact_version)}</span></div>'
    f'<div class="col"><b>tool declarations</b><span>{len(active["declarations"])}</span></div>'
    f'<div class="col"><b>lượt trong phiên</b><span>{len(st.session_state.turns)}</span></div>'
    f'<div class="col"><b>transcript</b><span>{html.escape(st.session_state.transcript_path.name)}</span></div>'
    "</div>",
    unsafe_allow_html=True,
)
