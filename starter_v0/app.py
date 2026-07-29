"""Streamlit UI cho Research Agent.

Nguyên tắc: UI KHÔNG có agent loop riêng. Toàn bộ vòng lặp model <-> tool
được import từ `chat.py` (`run_model_tool_loop`), nên CLI và UI luôn chạy
đúng cùng một hành vi, cùng prompt và cùng tool declarations.

Chạy:  streamlit run app.py
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

# --- Single source of truth cho agent loop: chat.py -------------------------
from chat import (
    ARTIFACTS_DIR,
    ROOT,
    json_text,
    now_iso,
    run_model_tool_loop,
    safe_slug,
    trim_history,
    write_transcript,
)
from providers import make_provider
from tools import load_tool_declarations, to_openai_tools
from versioning import artifact_version_dict, build_artifact_version


VERSIONS_DIR = ARTIFACTS_DIR / "versions"
TRANSCRIPTS_DIR = ROOT / "transcripts"
COMPARISONS_DIR = ROOT / "comparisons"
RUNS_DIR = ROOT / "runs"
DATA_DIR = ROOT / "data"

PROVIDER_ENV_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
}

STATUS_BADGE = {
    "answered": "✅",
    "waiting_for_user": "⏸️",
    "max_tool_rounds": "⚠️",
    "provider_error": "❌",
}


# ---------------------------------------------------------------------------
# Artifact versions
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ArtifactSet:
    """Một bộ artifact (system_prompt + tools) tương ứng một version."""

    label: str
    system_prompt_path: Path
    tools_path: Path
    is_live: bool

    @property
    def display(self) -> str:
        return f"{self.label} · live" if self.is_live else f"{self.label} · snapshot"


def discover_artifact_sets(live_label: str) -> list[ArtifactSet]:
    """Bộ artifact đang sửa (live) + mọi snapshot trong artifacts/versions/."""
    sets = [
        ArtifactSet(
            label=live_label,
            system_prompt_path=ARTIFACTS_DIR / "system_prompt.md",
            tools_path=ARTIFACTS_DIR / "tools.yaml",
            is_live=True,
        )
    ]
    if VERSIONS_DIR.exists():
        for folder in sorted(VERSIONS_DIR.iterdir()):
            prompt_path = folder / "system_prompt.md"
            tools_path = folder / "tools.yaml"
            if folder.is_dir() and prompt_path.exists() and tools_path.exists():
                sets.append(
                    ArtifactSet(
                        label=folder.name,
                        system_prompt_path=prompt_path,
                        tools_path=tools_path,
                        is_live=False,
                    )
                )
    return sets


def load_artifact_set(artifact_set: ArtifactSet) -> dict[str, Any]:
    system_prompt = artifact_set.system_prompt_path.read_text(encoding="utf-8")
    declarations = load_tool_declarations(artifact_set.tools_path)
    return {
        "set": artifact_set,
        "system_prompt": system_prompt,
        "declarations": declarations,
        "openai_tools": to_openai_tools(declarations),
        "artifact_version": build_artifact_version(
            artifact_set.label,
            artifact_set.system_prompt_path,
            artifact_set.tools_path,
        ),
    }


def snapshot_live_artifacts(label: str, *, overwrite: bool) -> tuple[bool, str]:
    """Chụp artifacts/ hiện tại thành artifacts/versions/<label>/ để so sánh sau này."""
    slug = safe_slug(label)
    dest = VERSIONS_DIR / slug
    prompt_dest = dest / "system_prompt.md"
    tools_dest = dest / "tools.yaml"
    if (prompt_dest.exists() or tools_dest.exists()) and not overwrite:
        return False, f"Snapshot `{slug}` đã tồn tại. Tick 'ghi đè' nếu thật sự muốn thay."
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ARTIFACTS_DIR / "system_prompt.md", prompt_dest)
    shutil.copy2(ARTIFACTS_DIR / "tools.yaml", tools_dest)
    return True, f"Đã lưu snapshot `{slug}` vào {dest.relative_to(ROOT)}"


# ---------------------------------------------------------------------------
# Trace helpers
# ---------------------------------------------------------------------------

def compact(value: Any, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


def event_status(event: dict[str, Any]) -> tuple[str, str]:
    """(status, badge) cho một tool event."""
    result = event.get("result")
    if not isinstance(result, dict):
        return "ok", "✅"
    if result.get("error"):
        return f"error:{result['error']}", "❌"
    if result.get("awaiting_user"):
        return "awaiting_user", "⏸️"
    status = result.get("status")
    if status:
        return str(status), "⚠️" if status == "needs_confirmation" else "✅"
    return "ok", "✅"


def result_summary(event: dict[str, Any]) -> str:
    result = event.get("result")
    if not isinstance(result, dict):
        return type(result).__name__
    if result.get("error"):
        return str(result.get("message") or result.get("error"))
    if result.get("awaiting_user"):
        return str(result.get("question") or "")
    items = result.get("items")
    if isinstance(items, list):
        first = items[0].get("title") if items and isinstance(items[0], dict) else ""
        return f"{len(items)} item(s)" + (f" · {first}" if first else "")
    if result.get("message"):
        return str(result["message"])
    return compact({k: v for k, v in result.items() if k != "tool"}, 120)


def called_tools(record: dict[str, Any]) -> list[str]:
    return [event.get("tool", "?") for event in record.get("tool_events", [])]


def error_count(record: dict[str, Any]) -> int:
    return sum(1 for event in record.get("tool_events", []) if event_status(event)[1] == "❌")


def render_request(messages: list[dict[str, str]], declarations: list[dict[str, Any]]) -> None:
    st.caption(
        f"{len(messages)} message(s) · {len(declarations)} tool declaration(s) được gửi cho model"
    )
    left, right = st.columns(2)
    with left:
        st.markdown("**messages**")
        st.code(json_text(messages, max_chars=12000), language="json")
    with right:
        st.markdown("**tools được khai báo**")
        st.code(
            json_text([item["name"] for item in declarations]),
            language="json",
        )


def render_rounds(rounds: list[dict[str, Any]], *, key_prefix: str) -> None:
    if not rounds:
        st.info("Không có round nào (request lỗi trước khi gọi model).")
        return

    for round_record in rounds:
        calls = round_record.get("tool_calls") or []
        events = round_record.get("tool_results") or []
        names = ", ".join(call.get("name", "?") for call in calls) if calls else "không gọi tool → trả lời thẳng"
        badges = "".join(event_status(event)[1] for event in events)
        header = f"Round {round_record.get('round')} — {names} {badges}"

        with st.expander(header, expanded=True):
            if round_record.get("assistant_text"):
                st.markdown("**assistant_text**")
                st.markdown(round_record["assistant_text"])

            if not events:
                continue

            st.markdown("**Tool events**")
            st.dataframe(
                [
                    {
                        "#": index + 1,
                        "tool": event.get("tool", "?"),
                        "status": event_status(event)[0],
                        "args": compact(event.get("args", {})),
                        "result/error": result_summary(event),
                    }
                    for index, event in enumerate(events)
                ],
                hide_index=True,
            )

            for index, event in enumerate(events):
                status, badge = event_status(event)
                st.markdown(f"{badge} **`{event.get('tool', '?')}`** · status `{status}`")
                args_col, result_col = st.columns(2)
                with args_col:
                    st.caption("args")
                    st.code(json_text(event.get("args", {})), language="json")
                with result_col:
                    st.caption("result / error")
                    st.code(json_text(event.get("result"), max_chars=8000), language="json")
                if index < len(events) - 1:
                    st.divider()


def render_turn(turn: dict[str, Any], *, key_prefix: str) -> None:
    status = turn.get("status", "unknown")
    badge = STATUS_BADGE.get(status, "•")

    with st.chat_message("user"):
        st.markdown(turn.get("user", ""))

    with st.chat_message("assistant"):
        head = st.columns([1, 1, 1, 2])
        head[0].metric("status", f"{badge} {status}")
        head[1].metric("rounds", len(turn.get("rounds") or []))
        head[2].metric("tool calls", len(turn.get("tool_events") or []))
        head[3].metric("tool errors", error_count(turn))

        if turn.get("error"):
            st.error(turn["error"])

        st.markdown("**Final response**")
        st.markdown(turn.get("assistant_text") or "_(trống)_")

        if turn.get("request_messages") is not None:
            with st.expander("Request gửi cho model", expanded=False):
                render_request(turn["request_messages"], turn.get("request_tools") or [])

        st.markdown("**Trace từng round**")
        render_rounds(turn.get("rounds") or [], key_prefix=key_prefix)


def artifact_header(artifact: dict[str, Any], *, extra: dict[str, str] | None = None) -> None:
    version = artifact["artifact_version"]
    cols = st.columns(4)
    cols[0].metric("version", version.version)
    cols[1].metric("prompt_hash", version.prompt_hash[:12])
    cols[2].metric("tools_hash", version.tools_hash[:12])
    cols[3].metric("tools", len(artifact["declarations"]))
    st.code(f"artifact_version = {version.artifact_version}", language="text")
    if extra:
        st.caption(" · ".join(f"{key}: {value}" for key, value in extra.items()))


# ---------------------------------------------------------------------------
# Chạy agent (mọi nơi trong UI đều đi qua hàm này -> chat.run_model_tool_loop)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def get_provider(name: str):
    return make_provider(name)


def run_once(
    *,
    provider_name: str,
    model: str | None,
    artifact: dict[str, Any],
    history: list[dict[str, str]],
    user_text: str,
    history_window: int,
    max_tool_rounds: int,
) -> dict[str, Any]:
    """Một lượt agent. Loop thật nằm ở chat.run_model_tool_loop."""
    messages = [
        {"role": "system", "content": artifact["system_prompt"]},
        *trim_history(history, history_window),
        {"role": "user", "content": user_text},
    ]
    record: dict[str, Any] = {
        "started_at": now_iso(),
        "user": user_text,
        "status": "started",
        "assistant_text": None,
        "rounds": [],
        "tool_events": [],
        "request_messages": messages,
        "request_tools": artifact["declarations"],
    }

    started = time.perf_counter()
    try:
        result = run_model_tool_loop(
            provider=get_provider(provider_name),
            messages=messages,
            tools=artifact["openai_tools"],
            model=model,
            max_tool_rounds=max_tool_rounds,
        )
        record.update(result)
    except Exception as exc:
        record.update(
            {
                "status": "provider_error",
                "assistant_text": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
    record["elapsed_seconds"] = round(time.perf_counter() - started, 2)
    record["ended_at"] = now_iso()
    return record


def new_transcript(
    *,
    artifact: dict[str, Any],
    provider_name: str,
    model: str | None,
    history_window: int,
    max_tool_rounds: int,
    kind: str,
) -> tuple[dict[str, Any], Path]:
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    artifact_set: ArtifactSet = artifact["set"]
    transcript_id = "_".join(
        [safe_slug(artifact_set.label), safe_slug(provider_name), safe_slug(kind), timestamp]
    )
    transcript = {
        "transcript_id": transcript_id,
        **artifact_version_dict(artifact["artifact_version"]),
        "provider": provider_name,
        "model": model,
        "system_prompt": str(artifact_set.system_prompt_path),
        "tools": str(artifact_set.tools_path),
        "history_window": history_window,
        "max_tool_rounds": max_tool_rounds,
        "source": "app.py (streamlit)",
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "turns": [],
    }
    return transcript, TRANSCRIPTS_DIR / f"{transcript_id}.transcript.json"


# ---------------------------------------------------------------------------
# Scenario library
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def load_scenarios() -> list[dict[str, Any]]:
    """Scenario lấy từ các eval dataset để demo cùng một case qua nhiều version."""
    scenarios: list[dict[str, Any]] = []
    for path in sorted(DATA_DIR.glob("eval_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for case in data.get("cases", []):
            turns = case.get("turns")
            if turns:
                history = [
                    {"role": turn.get("role", "user"), "content": turn.get("content", "")}
                    for turn in turns[:-1]
                ]
                user_text = turns[-1].get("content", "")
            else:
                history = []
                user_text = case.get("input") or case.get("query") or ""
            if not user_text:
                continue
            scenarios.append(
                {
                    "id": case.get("id", "case"),
                    "dataset": path.stem,
                    "history": history,
                    "user_text": user_text,
                    "expect": case.get("expect", {}),
                    "metadata": case.get("metadata", {}),
                }
            )
    return scenarios


def expected_tools(expect: dict[str, Any]) -> list[str]:
    if expect.get("no_tool"):
        return []
    return [call.get("name", "") for call in expect.get("tool_calls", [])]


def routing_match(expect: dict[str, Any], record: dict[str, Any]) -> str:
    """Chỉ báo nhanh cho demo. Điểm chính thức vẫn là run_eval.py."""
    if not expect:
        return "—"
    actual = called_tools(record)
    expected = expected_tools(expect)
    if expect.get("no_tool"):
        return "✅ khớp" if not actual else "❌ lệch"
    return "✅ khớp" if sorted(actual) == sorted(expected) else "❌ lệch"


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

st.set_page_config(page_title="Research Agent — UI", page_icon="🔎", layout="wide")

for key, default in [
    ("chat_transcript", None),
    ("chat_transcript_path", None),
    ("chat_history", []),
    ("chat_signature", None),
    ("compare_result", None),
    ("snapshot_message", None),
]:
    st.session_state.setdefault(key, default)

with st.sidebar:
    st.header("Cấu hình")

    provider_name = st.selectbox("Provider", ["openrouter", "openai", "anthropic", "gemini"])
    env_key = PROVIDER_ENV_KEYS[provider_name]
    if os.getenv(env_key):
        st.success(f"{env_key}: đã set")
    else:
        st.error(f"{env_key}: chưa set trong .env")

    model_input = st.text_input("Model (bỏ trống = default của provider)", value="")
    model = model_input.strip() or None
    history_window = st.slider("history_window", 0, 10, 5)
    max_tool_rounds = st.slider("max_tool_rounds", 1, 8, 4)

    st.divider()
    st.subheader("Artifact version")
    live_label = st.text_input("Nhãn cho artifacts đang sửa", value="wip").strip() or "wip"
    artifact_sets = discover_artifact_sets(live_label)
    set_by_display = {item.display: item for item in artifact_sets}
    active_display = st.selectbox("Version dùng cho tab Chat", list(set_by_display))
    active_set = set_by_display[active_display]

    st.caption(
        f"{len(artifact_sets) - 1} snapshot trong `artifacts/versions/`. "
        "Snapshot là cách giữ lại prompt/tools của v0, v1, v2… để so sánh."
    )

    with st.form("snapshot_form", clear_on_submit=False):
        snapshot_label = st.text_input("Chụp artifacts hiện tại thành version", value="v0")
        overwrite = st.checkbox("ghi đè nếu đã tồn tại", value=False)
        if st.form_submit_button("Lưu snapshot"):
            ok, message = snapshot_live_artifacts(snapshot_label, overwrite=overwrite)
            st.session_state["snapshot_message"] = (ok, message)
            st.rerun()

    if st.session_state["snapshot_message"]:
        ok, message = st.session_state["snapshot_message"]
        (st.success if ok else st.warning)(message)


try:
    active_artifact = load_artifact_set(active_set)
except Exception as exc:
    st.error(f"Không đọc được artifact `{active_set.label}`: {type(exc).__name__}: {exc}")
    st.stop()


st.title("🔎 Research Agent")
st.caption(
    "Group 11"
)

chat_tab, compare_tab, browse_tab = st.tabs(
    ["💬 Chat & Trace", "🆚 So sánh version", "📁 Transcript / Run"]
)


# ---------------------------------------------------------------------------
# Tab 1 — Chat & Trace
# ---------------------------------------------------------------------------

with chat_tab:
    artifact_header(
        active_artifact,
        extra={
            "provider": provider_name,
            "model": model or "default",
            "system_prompt": str(active_set.system_prompt_path.relative_to(ROOT)),
            "tools": str(active_set.tools_path.relative_to(ROOT)),
        },
    )

    signature = (
        active_artifact["artifact_version"].artifact_version,
        provider_name,
        model,
        history_window,
        max_tool_rounds,
    )
    if st.session_state["chat_signature"] != signature or st.session_state["chat_transcript"] is None:
        transcript, transcript_path = new_transcript(
            artifact=active_artifact,
            provider_name=provider_name,
            model=model,
            history_window=history_window,
            max_tool_rounds=max_tool_rounds,
            kind="chat",
        )
        st.session_state["chat_transcript"] = transcript
        st.session_state["chat_transcript_path"] = transcript_path
        st.session_state["chat_history"] = []
        st.session_state["chat_signature"] = signature

    transcript = st.session_state["chat_transcript"]
    transcript_path: Path = st.session_state["chat_transcript_path"]

    info_col, button_col = st.columns([4, 1])
    info_col.code(f"transcript = {transcript_path.relative_to(ROOT)}", language="text")
    if button_col.button("Hội thoại mới"):
        st.session_state["chat_signature"] = None
        st.rerun()

    with st.expander("System prompt đang dùng", expanded=False):
        st.code(active_artifact["system_prompt"], language="markdown")

    for index, turn in enumerate(transcript["turns"]):
        render_turn(turn, key_prefix=f"chat{index}")

    user_text = st.chat_input("Nhập request…")
    if user_text:
        with st.spinner("Agent đang chạy…"):
            record = run_once(
                provider_name=provider_name,
                model=model,
                artifact=active_artifact,
                history=st.session_state["chat_history"],
                user_text=user_text,
                history_window=history_window,
                max_tool_rounds=max_tool_rounds,
            )
        record["turn_index"] = len(transcript["turns"]) + 1
        transcript["turns"].append(record)

        if record["status"] != "provider_error":
            st.session_state["chat_history"].append({"role": "user", "content": user_text})
            st.session_state["chat_history"].append(
                {"role": "assistant", "content": record.get("assistant_text") or ""}
            )

        write_transcript(transcript_path, transcript)
        st.rerun()


# ---------------------------------------------------------------------------
# Tab 2 — So sánh version
# ---------------------------------------------------------------------------

with compare_tab:
    st.subheader("Một scenario, nhiều version")
    st.caption(
        "Chạy đúng cùng một request qua nhiều bộ artifact để thấy version nào cải thiện. "
        "Kết quả lưu thành transcript riêng cho từng version + một file so sánh."
    )

    scenarios = load_scenarios()
    scenario_options = ["✍️ Tự nhập"] + [
        f"{item['id']} · {item['dataset']}" for item in scenarios
    ]
    picked = st.selectbox("Scenario", scenario_options)

    if picked == "✍️ Tự nhập":
        scenario = {
            "id": "custom",
            "dataset": "manual",
            "history": [],
            "expect": {},
            "metadata": {},
        }
        scenario["user_text"] = st.text_area(
            "Request", value="Tóm tắt 5 tweet mới nhất của Sam Altman", height=90
        )
        scenario_id = st.text_input("Tên scenario (dùng đặt tên file)", value="demo_scenario")
        scenario["id"] = scenario_id or "custom"
    else:
        scenario = scenarios[scenario_options.index(picked) - 1]
        st.text_area("Request", value=scenario["user_text"], height=90, disabled=True)
        if scenario["history"]:
            st.caption("Lượt trước đó đưa vào context:")
            st.code(json_text(scenario["history"]), language="json")
        if scenario["expect"]:
            st.caption(f"Expectation của eval case: `{compact(scenario['expect'], 300)}`")

    selected_displays = st.multiselect(
        "Các version cần chạy",
        list(set_by_display),
        default=[active_display],
    )

    run_compare = st.button(
        "▶️ Chạy scenario qua các version",
        type="primary",
        disabled=not selected_displays or not scenario.get("user_text"),
    )

    if run_compare:
        rows: list[dict[str, Any]] = []
        progress = st.progress(0.0, text="Bắt đầu…")
        for position, display in enumerate(selected_displays, start=1):
            artifact_set = set_by_display[display]
            progress.progress(
                (position - 1) / len(selected_displays), text=f"Đang chạy {artifact_set.label}…"
            )
            try:
                artifact = load_artifact_set(artifact_set)
            except Exception as exc:
                rows.append(
                    {
                        "label": artifact_set.label,
                        "error": f"Không đọc được artifact: {type(exc).__name__}: {exc}",
                    }
                )
                continue

            record = run_once(
                provider_name=provider_name,
                model=model,
                artifact=artifact,
                history=scenario["history"],
                user_text=scenario["user_text"],
                history_window=history_window,
                max_tool_rounds=max_tool_rounds,
            )
            record["turn_index"] = 1

            transcript, path = new_transcript(
                artifact=artifact,
                provider_name=provider_name,
                model=model,
                history_window=history_window,
                max_tool_rounds=max_tool_rounds,
                kind=f"compare-{safe_slug(scenario['id'])}",
            )
            transcript["scenario_id"] = scenario["id"]
            transcript["turns"].append(record)
            write_transcript(path, transcript)

            rows.append(
                {
                    "label": artifact_set.label,
                    "display": display,
                    **artifact_version_dict(artifact["artifact_version"]),
                    "record": record,
                    "transcript": str(path.relative_to(ROOT)),
                    "system_prompt": str(artifact_set.system_prompt_path),
                    "tools": str(artifact_set.tools_path),
                    "routing": routing_match(scenario["expect"], record),
                }
            )

        progress.progress(1.0, text="Xong")

        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        compare_id = f"compare_{safe_slug(scenario['id'])}_{safe_slug(provider_name)}_{timestamp}"
        compare_path = COMPARISONS_DIR / f"{compare_id}.compare.json"
        compare_path.parent.mkdir(parents=True, exist_ok=True)
        compare_path.write_text(
            json.dumps(
                {
                    "compare_id": compare_id,
                    "scenario": {k: v for k, v in scenario.items()},
                    "provider": provider_name,
                    "model": model,
                    "history_window": history_window,
                    "max_tool_rounds": max_tool_rounds,
                    "generated_at": now_iso(),
                    "versions": rows,
                },
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

        st.session_state["compare_result"] = {
            "scenario": scenario,
            "rows": rows,
            "path": compare_path,
        }
        st.rerun()

    result = st.session_state["compare_result"]
    if result:
        rows = result["rows"]
        st.divider()
        st.markdown(f"**Scenario:** {result['scenario']['user_text']}")
        st.code(f"comparison = {result['path'].relative_to(ROOT)}", language="text")

        summary = []
        for row in rows:
            if "record" not in row:
                summary.append({"version": row["label"], "status": row.get("error", "error")})
                continue
            record = row["record"]
            summary.append(
                {
                    "version": row["label"],
                    "artifact_version": row["artifact_version"],
                    "status": f"{STATUS_BADGE.get(record['status'], '•')} {record['status']}",
                    "rounds": len(record.get("rounds") or []),
                    "tool_calls": " → ".join(called_tools(record)) or "—",
                    "tool_errors": error_count(record),
                    "khớp expectation": row["routing"],
                    "giây": record.get("elapsed_seconds"),
                }
            )
        st.dataframe(summary, hide_index=True)
        if result["scenario"].get("expect"):
            st.caption(
                "Cột 'khớp expectation' chỉ là chỉ báo nhanh cho demo. "
                "Metric chính thức vẫn lấy từ `run_eval.py`."
            )

        detail_tabs = st.tabs([row["label"] for row in rows])
        for tab, row in zip(detail_tabs, rows):
            with tab:
                if "record" not in row:
                    st.error(row.get("error", "unknown error"))
                    continue
                record = row["record"]
                st.code(f"artifact_version = {row['artifact_version']}", language="text")
                st.caption(f"transcript: {row['transcript']}")
                render_turn(record, key_prefix=f"cmp-{safe_slug(row['label'])}")

        readable = [row for row in rows if "record" in row]
        if len(readable) >= 2:
            with st.expander("Khác biệt artifact giữa các version", expanded=False):
                for previous, current in zip(readable, readable[1:]):
                    st.markdown(f"**{previous['label']} → {current['label']}**")
                    for name, key in [("system_prompt.md", "system_prompt"), ("tools.yaml", "tools")]:
                        diff = list(
                            difflib.unified_diff(
                                Path(previous[key]).read_text(encoding="utf-8").splitlines(),
                                Path(current[key]).read_text(encoding="utf-8").splitlines(),
                                fromfile=f"{previous['label']}/{name}",
                                tofile=f"{current['label']}/{name}",
                                lineterm="",
                            )
                        )
                        st.caption(name)
                        st.code("\n".join(diff) or "(không đổi)", language="diff")


# ---------------------------------------------------------------------------
# Tab 3 — Transcript / Run browser
# ---------------------------------------------------------------------------

with browse_tab:
    st.subheader("Mở lại evidence đã lưu")

    source = st.radio(
        "Nguồn",
        ["transcripts (chat/compare)", "comparisons (so sánh version)", "runs (eval)"],
        horizontal=True,
    )
    folder = {
        "transcripts (chat/compare)": TRANSCRIPTS_DIR,
        "comparisons (so sánh version)": COMPARISONS_DIR,
        "runs (eval)": RUNS_DIR,
    }[source]

    files = sorted(folder.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True) if folder.exists() else []
    if not files:
        st.info(f"Chưa có file nào trong `{folder.name}/`.")
    else:
        chosen = st.selectbox("File", files, format_func=lambda item: item.name)
        payload = json.loads(chosen.read_text(encoding="utf-8"))

        meta_cols = st.columns(4)
        meta_cols[0].metric("version", str(payload.get("version", "—")))
        meta_cols[1].metric("provider", str(payload.get("provider", "—")))
        meta_cols[2].metric("model", str(payload.get("model") or "default"))
        meta_cols[3].metric("generated", str(payload.get("generated_at") or payload.get("created_at") or "—"))
        if payload.get("artifact_version"):
            st.code(f"artifact_version = {payload['artifact_version']}", language="text")

        st.download_button(
            "Tải file JSON",
            data=chosen.read_bytes(),
            file_name=chosen.name,
            mime="application/json",
        )

        if "turns" in payload:
            for index, turn in enumerate(payload["turns"]):
                render_turn(turn, key_prefix=f"browse{index}")

        elif "versions" in payload:
            st.markdown(f"**Scenario:** {payload.get('scenario', {}).get('user_text', '')}")
            st.dataframe(
                [
                    {
                        "version": row.get("label"),
                        "artifact_version": row.get("artifact_version"),
                        "status": (row.get("record") or {}).get("status", row.get("error", "—")),
                        "tool_calls": " → ".join(called_tools(row.get("record") or {})) or "—",
                        "khớp expectation": row.get("routing", "—"),
                        "transcript": row.get("transcript"),
                    }
                    for row in payload["versions"]
                ],
                hide_index=True,
            )
            version_tabs = st.tabs([row.get("label", "?") for row in payload["versions"]])
            for tab, row in zip(version_tabs, payload["versions"]):
                with tab:
                    if not row.get("record"):
                        st.error(row.get("error", "unknown"))
                        continue
                    render_turn(row["record"], key_prefix=f"browsecmp-{row.get('label')}")

        elif "results" in payload:
            summary = payload.get("summary", {})
            metric_cols = st.columns(4)
            metric_cols[0].metric("case_accuracy", summary.get("case_accuracy", "—"))
            metric_cols[1].metric("routing", summary.get("tool_routing_accuracy", "—"))
            metric_cols[2].metric("argument", summary.get("argument_accuracy", "—"))
            metric_cols[3].metric("multiturn", summary.get("multiturn_accuracy", "—"))
            st.dataframe(
                [
                    {
                        "case": item.get("id"),
                        "passed": item["result"].get("passed"),
                        "expected": compact(item.get("expect", {}), 80),
                        "actual": " → ".join(
                            call.get("name", "") for call in item["result"].get("actual_tool_calls", [])
                        )
                        or "—",
                        "failure_type": item["result"].get("failure_type") or "",
                        "failures": "; ".join(item["result"].get("failures") or []),
                    }
                    for item in payload["results"]
                ],
                hide_index=True,
            )

        with st.expander("Raw JSON", expanded=False):
            st.code(json_text(payload, max_chars=200000), language="json")
