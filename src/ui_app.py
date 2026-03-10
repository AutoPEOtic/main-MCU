# ui_app.py

from __future__ import annotations
import os
import re
import sys

# Ensure project root is importable when running: streamlit run src/ui_app.py
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import time
import streamlit as st

from src.ipc import IPCPaths, read_json, atomic_write_json, default_control, default_status
from settings.programs import list_programs, programs_by_name

ipc = IPCPaths()

st.set_page_config(page_title="AutoPEOtic Control Panel", layout="wide")

status = read_json(ipc.status_path, default_status())
state = status.get("state", "IDLE")
process = status.get("process", "not running")
program_running = status.get("program", None)

iteration = status.get("iteration", {"i": 0, "n": 0})
params = status.get("params", {})
fluid = status.get("fluid", {})
last_event = status.get("last_event", "")
error = status.get("error", None)

# --- run log storage (per UI session) ---
if "run_log" not in st.session_state:
    st.session_state["run_log"] = []   # list[dict]

if "program_start_ts" not in st.session_state:
    st.session_state["program_start_ts"] = None

# Start timer when program enters RUNNING
if state == "RUNNING" and st.session_state["program_start_ts"] is None:
    st.session_state["program_start_ts"] = time.time()

# Reset timer + log when program goes IDLE (finished or stopped)
if state == "IDLE" and st.session_state["program_start_ts"] is not None:
    st.session_state["program_start_ts"] = None
    # optional: keep log or clear it:
    # st.session_state["run_log"] = []

# Helper: format elapsed program time
def _elapsed_str() -> str:
    ts = st.session_state["program_start_ts"]
    if ts is None:
        return "—"
    sec = int(time.time() - ts)
    mm = sec // 60
    ss = sec % 60
    return f"{mm:02d}:{ss:02d}"

# Append a log row when we see "Run i/n finished"
m = re.search(r"Run\s+(\d+)\s*/\s*(\d+)\s+finished", str(last_event))
if m and st.session_state["program_start_ts"] is not None:
    run_i = int(m.group(1))

    # avoid duplicates on UI reruns
    if not any(row.get("run") == run_i for row in st.session_state["run_log"]):
        st.session_state["run_log"].append({
            "run": run_i,
            "Upos": params.get("Upos"),
            "KOH_target": params.get("KOH_target"),
            "done_at": _elapsed_str(),   # program working time at completion
        })

# --- Header ---
c1, c2, c3 = st.columns([2, 4, 4])
with c1:
    st.markdown("## AutoPEOtic")
with c2:
    st.caption("State")
    if state == "RUNNING":
        st.success("RUNNING")
    elif state == "PAUSED":
        st.warning("PAUSED")
    elif state == "ERROR":
        st.error("ERROR")
    else:
        st.info("IDLE")
with c3:
    st.caption("Process")
    st.write(process)

st.markdown("---")

programs = list_programs()
program_names = [p.name for p in programs]
prog_map = programs_by_name()

left, right = st.columns([1, 1])

with left:
    st.subheader("Program")
    selected = st.selectbox(
        "Choose a program (defined in settings/programs.py)",
        program_names,
        index=0 if program_names else None,
        disabled=(state in ("RUNNING", "PAUSED")),
    )
    st.caption(f"Currently running: {program_running or 'None'}")

with right:
    st.subheader("Iteration (live)")
    st.metric("Run", f"{iteration.get('i', 0)}/{iteration.get('n', 0)}")
    st.caption(f"Last event: {last_event}")
    if error:
        st.error(error)

st.markdown("---")

# --- Command helpers ---
def issue_command(command: str, program: str | None = None) -> None:
    ctrl = read_json(ipc.control_path, default_control())
    next_id = int(ctrl.get("command_id", 0)) + 1
    atomic_write_json(
        ipc.control_path,
        {
            "command": command,
            "program": program,
            "issued_at": time.time(),
            "command_id": next_id,
        },
    )

# Enable rules (your spec)
can_start = (state == "IDLE")
can_pause = (state == "RUNNING")
can_continue = (state == "PAUSED")
can_restart = True
can_stop = True

b1, b2, b3, b4, b5 = st.columns(5)
with b1:
    if st.button("START", disabled=not can_start):
        issue_command("START", program=selected)
with b2:
    if st.button("PAUSE", disabled=not can_pause):
        issue_command("PAUSE")
with b3:
    if st.button("CONTINUE", disabled=not can_continue):
        issue_command("CONTINUE")
with b4:
    if st.button("RESTART", disabled=not can_restart):
        issue_command("RESTART", program=selected)
with b5:
    if st.button("STOP", disabled=not can_stop):
        issue_command("STOP")
can_restart_current = (state == "PAUSED") and int(iteration.get("i", 0)) > 0
with st.columns(6)[5]: 
    if st.button("RESTART CURRENT RUN", disabled=not can_restart_current):
        issue_command("RESTART_CURRENT_RUN")
st.markdown("---")

# --- Live telemetry (during run) ---
t1, t2, t3 = st.columns(3)
with t1:
    st.subheader("Current Parameters (live)")
    st.metric("Upos", params.get("Upos", "—"))
    st.metric("PEO time", params.get("PEO_time", "—"))
    st.metric("KOH target", params.get("KOH_target", "—"))

with t2:
    st.subheader("Fluid (labels, live)")
    ratios = fluid.get("ratios", {}) or {}
    if ratios:
        for k, v in ratios.items():
            st.write(f"- **{k}**: {v}")
    else:
        st.write("—")

with t3:
    st.subheader("Fluid (channels, live)")
    ch = fluid.get("channels", {}) or {}
    total_ml = fluid.get("total_ml", None)
    if total_ml is not None:
        st.write(f"Total: **{total_ml} mL**")
    if ch:
        for k, v in ch.items():
            st.write(f"- **{k}**: {v}")
    else:
        st.write("—")

# --- Program preview BEFORE start ---
if selected and selected in prog_map:
    p = prog_map[selected]

    st.subheader("Program Preview (before START)")
    p1, p2, p3 = st.columns(3)
    with p1:
        st.write("**Upos values**")
        st.write(p.Upos_values)
    with p2:
        st.write("**PEO time values**")
        st.write(p.PEO_time_values)
    with p3:
        st.write("**KOH targets**")
        st.write(p.KOH_targets)

    total_runs = len(p.Upos_values) * len(p.PEO_time_values) * len(p.KOH_targets)
    st.write(f"**Total runs:** {total_runs}")
    st.write(f"**Total volume per run:** {p.total_ml} mL")
    st.write(f"**Mixing model:** {p.water_channel} (H2O) + {p.koh_stock_channel} (KOH stock)")

    # First 10 runs preview
    preview = []
    for t in p.PEO_time_values:
        for u in p.Upos_values:
            for koh in p.KOH_targets:
                preview.append((t, u, koh, 1.0 - koh, koh))
                if len(preview) >= 10:
                    break
            if len(preview) >= 10:
                break
        if len(preview) >= 10:
            break

    st.write("**First 10 planned runs (preview)**")
    st.table(
        [
            {
                "PEO_time": t,
                "Upos": u,
                "KOH_target": koh,
                "H2O_frac": h2o,
                "KOH_stock_frac": k,
            }
            for (t, u, koh, h2o, k) in preview
        ]
    )

    st.write("**Mixing ratios per KOH target (preview)**")
    st.table(
        [
            {
                "KOH_target": koh,
                "H2O": round(1.0 - koh, 6),
                "KOH_stock": round(koh, 6),
                p.water_channel: round(1.0 - koh, 6),
                p.koh_stock_channel: round(koh, 6),
            }
            for koh in p.KOH_targets
        ]
    )

st.markdown("---")

st.markdown("---")
st.subheader("Run log")

if st.session_state["run_log"]:
    # optional: show newest first
    st.table(sorted(st.session_state["run_log"], key=lambda r: r["run"], reverse=True))
else:
    st.write("No completed runs yet.")

# Auto-refresh
time.sleep(0.5)
st.rerun()