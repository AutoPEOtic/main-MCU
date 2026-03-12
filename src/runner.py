# src/runner.py
from __future__ import annotations

import os
import time
import traceback
from typing import Dict, Any, List, Tuple, Optional

from src.autopeotic import autopeotic
from src.ipc import IPCPaths, read_json, atomic_write_json, default_status, default_control
from settings.programs import programs_by_name, Program
from src.checkpoint import CheckpointManager

CHECKPOINT_STATE = "settings/checkpoint_state.json"
CHECKPOINT_LOG = "settings/checkpoint_events.log"

class RestartCurrentRunRequested(Exception):
    pass

class StopRequested(Exception):
    pass

class ProgramRestartRequested(Exception):
    pass

class Runner:
    def __init__(self, ipc: IPCPaths):
        self.ipc = ipc
        self.ap = autopeotic()
        self.restart_current_run_requested = False
        self.failed_run_idx = None
        self.state = "IDLE"  # IDLE/RUNNING/PAUSED/ERROR
        self.resume_run_idx: Optional[int] = None
        self.program: Optional[Program] = None

        self.stop_requested = False
        self.pause_requested = False
        self.restart_requested = False
        self.restart_program_name: Optional[str] = None

        self.current_i = 0
        self.total_n = 0

        self.last_seen_command_id = 0
        self.last_event = ""

        if not os.path.exists(self.ipc.control_path):
            atomic_write_json(self.ipc.control_path, default_control())
        if not os.path.exists(self.ipc.status_path):
            atomic_write_json(self.ipc.status_path, default_status())

        self.publish_status(process="not running")

        # --- IMPORTANT: do not replay old UI commands after runner restart ---
        ctrl = self.read_control()
        self.last_seen_command_id = int(ctrl.get("command_id", 0))
        # Optional safety: if the last command is START/RESTART, clear it so it won't be reused by other tools
        atomic_write_json(self.ipc.control_path, {
            "command": "NONE",
            "program": None,
            "issued_at": time.time(),
            "command_id": self.last_seen_command_id,
        })

    # ---------- checkpoint reset ----------
    def reset_checkpoints(self) -> None:
        for p in [CHECKPOINT_STATE, CHECKPOINT_LOG]:
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
        # simplest reset: recreate autopeotic (rebuilds CheckpointManager)
        self.ap = autopeotic()

    # ---------- mixing math (2-channel) ----------
    def compute_two_channel_recipe(self, prog: Program, target: float):
        c1 = prog.water_conc
        c2 = prog.koh_stock_conc
        if abs(c2 - c1) < 1e-9:
            raise ValueError("Invalid program: water_conc equals koh_stock_conc")

        r_koh = (target - c1) / (c2 - c1)
        r_koh = max(0.0, min(1.0, r_koh))
        r_water = 1.0 - r_koh

        channels = {prog.water_channel: round(r_water, 6), prog.koh_stock_channel: round(r_koh, 6)}
        labels = {"H2O": round(r_water, 6), "KOH_stock": round(r_koh, 6)}
        return channels, labels

    # ---------- IPC ----------
    def read_control(self) -> Dict[str, Any]:
        return read_json(self.ipc.control_path, default_control())

    def publish_status(self, process: Optional[str] = None, error: Optional[str] = None) -> None:
        st = read_json(self.ipc.status_path, default_status())
        st["state"] = self.state
        st["program"] = self.program.name if self.program else None
        st["process"] = process if process is not None else st.get("process", "not running")
        st["iteration"] = {"i": self.current_i, "n": self.total_n}
        st["params"]["Upos"] = getattr(self.ap, "Upos", None)
        st["params"]["PEO_time"] = getattr(self.ap, "PEO_time", None)
        st["params"]["KOH_target"] = getattr(self.ap, "KOH_concentration", None)
        st["last_event"] = self.last_event
        st["error"] = error
        st["updated_at"] = time.time()
        st["seen_command_id"] = self.last_seen_command_id
        atomic_write_json(self.ipc.status_path, st)

    # ---------- Command handling ----------
    def handle_command(self, ctrl: Dict[str, Any]):
        cmd_id = int(ctrl.get("command_id", 0))
        if cmd_id <= self.last_seen_command_id:
            return

        cmd = str(ctrl.get("command", "NONE")).upper().strip()
        prog_name = ctrl.get("program", None)

        self.last_seen_command_id = cmd_id
        self.last_event = f"CMD {cmd} (id={cmd_id})"
        self.publish_status()

        # STOP always allowed and immediate
        if cmd == "STOP":
            self.stop_requested = True
            self.pause_requested = False
            self.restart_requested = False
            self.restart_program_name = None
            self.restart_current_run_requested = False
            self.last_event = "STOP accepted"
            self.publish_status(process="stopping")
            return

        if cmd == "PAUSE":
            if self.state == "RUNNING":
                self.pause_requested = True
                self.state = "PAUSED"
                if self.current_i > 0:
                    self.failed_run_idx = self.current_i
                    self.resume_run_idx = self.current_i
                self.last_event = f"PAUSE accepted (run {self.current_i})"
            else:
                self.last_event = f"PAUSE rejected (state={self.state})"
            self.publish_status()
            return

        if cmd == "CONTINUE":
            if self.state == "PAUSED":
                self.pause_requested = False
                self.resume_run_idx = self.failed_run_idx or self.current_i or 1
                self.state = "RUNNING"
                self.last_event = "CONTINUE accepted"
            else:
                self.last_event = f"CONTINUE rejected (state={self.state})"
            self.publish_status()
            return

        if cmd in ("START", "RESTART"):
            if prog_name is None:
                self.last_event = f"{cmd} rejected (no program)"
                self.publish_status()
                return

            progs = programs_by_name()
            if prog_name not in progs:
                self.last_event = f"{cmd} rejected (unknown program: {prog_name})"
                self.publish_status(error=self.last_event)
                return

            if cmd == "START":
                if self.state != "IDLE":
                    self.last_event = f"START rejected (state={self.state})"
                    self.publish_status()
                    return
                self.stop_requested = False
                self.pause_requested = False
                self.restart_requested = False
                self.restart_program_name = None
                self.state = "RUNNING"
                self.program = progs[prog_name]
                self.last_event = f"START accepted (program={prog_name})"
                self.publish_status(process="starting")
                return

            # RESTART: can be issued during RUNNING/PAUSED/IDLE.
            # We mark restart_requested and interrupt current execution.
            self.restart_requested = True
            self.restart_program_name = prog_name
            self.stop_requested = True  # force abort of current cp.run as soon as possible
            self.pause_requested = False
            self.last_event = f"RESTART accepted (program={prog_name})"
            self.publish_status(process="restarting")
            return
            
        if cmd == "RESTART_CURRENT_RUN":
            run_i = self.resume_run_idx or self.failed_run_idx or self.current_i
            if run_i and run_i > 0:
                self._delete_run_checkpoints(run_i)
                self.restart_current_run_requested = True

                # KEEP pause active until the live cp.run is explicitly aborted
                self.pause_requested = True
                self.stop_requested = False
                self.resume_run_idx = run_i
                self.state = "PAUSED"

                self.last_event = f"RESTART_CURRENT_RUN accepted (run {run_i})"
                self.publish_status(process="restarting current run", error=None)
            else:
                self.last_event = "RESTART_CURRENT_RUN rejected (no current run)"
                self.publish_status()
            return

        if cmd not in ("NONE", ""):
            self.last_event = f"Unknown command: {cmd}"
            self.publish_status(error=self.last_event)

    # ---------- run list ----------
    def build_runs(self, prog: Program) -> List[Dict[str, Any]]:
        runs: List[Dict[str, Any]] = []
        for t in prog.PEO_time_values:
            for u in prog.Upos_values:
                for koh in prog.KOH_targets:
                    runs.append({"PEO_time": t, "Upos": u, "KOH": koh})
        return runs

    # ---------- Instruction wrapper ----------
    def _poll_commands(self) -> None:
        ctrl = self.read_control()
        self.handle_command(ctrl)

    def execute_line(self, line: str, run_ctx: Dict[str, Any]) -> None:
        # IMPORTANT: poll commands before each instruction line
        self._poll_commands()


        # STOP / RESTART interrupt as soon as we can
        if self.stop_requested:
            raise RuntimeError("STOP requested")

        # PAUSE gate: block here until CONTINUE/STOP/RESTART
        while self.pause_requested:
            self.state = "PAUSED"
            self.publish_status(process="paused")
            time.sleep(0.2)
            self._poll_commands()

            if self.stop_requested:
                raise RuntimeError("STOP requested")

            if self.restart_current_run_requested:
                raise RestartCurrentRunRequested(f"Restart current run requested (run {self.current_i})")

        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            return

        u = stripped.upper()

        # UI process labeling
        if u.startswith("SOLUTION"):
            self.publish_status(process="mixing")
        elif u.startswith(("G0", "G1", "HOME", "$H", "$X", "G90", "G91", "F")):
            self.publish_status(process="moving")
        elif u.startswith("CUT"):
            self.publish_status(process="cutting wire")
        elif u.startswith("FLUSH"):
            self.publish_status(process="flushing")
        elif u.startswith("SPECTRUM GET"):
            self.publish_status(process="measuring spectrum")
        elif u.startswith(("PEO ON", "SEND PEO VALUES")):
            self.publish_status(process="doing PEO")
        elif u.startswith("RECONNECT"):
            self.publish_status(process="reconnecting")
        elif u.startswith("SOLENOID"):
            self.publish_status(process="actuating solenoid")
        elif u.startswith("DEOXIDIZE"):
            self.publish_status(process="deoxidizing")

        # Rewrite SOLUTION dynamically
        if u.startswith("SOLUTION"):
            prog: Program = run_ctx["program"]
            total_ml: float = run_ctx["total_ml"]
            channels = run_ctx["mix_channels"]
            parts = ["SOLUTION", str(total_ml)]
            for ch in sorted(channels.keys()):
                parts += [ch, str(channels[ch])]
            rewritten = " ".join(parts)
            self.ap.send_instruction(rewritten)
            return

        # Pass-through
        self.ap.send_instruction(stripped)

    # ---------- main loop ----------
    def loop(self) -> None:
        while True:
            try:
                self._poll_commands()

                # STOP from PAUSED/IDLE should be handled here
                if self.stop_requested and self.state != "RUNNING":
                    self._do_stop()
                    time.sleep(0.2)
                    continue

                # Whole-program restart
                if self.restart_requested:
                    self._do_restart()
                    continue

                # Restart the currently paused/failed run
                if self.restart_current_run_requested and self.state == "PAUSED" and self.program is not None:
                    run_i = self.resume_run_idx or self.failed_run_idx or self.current_i
                    if run_i and run_i > 0:
                        self.restart_current_run_requested = False
                        self.pause_requested = False
                        self.failed_run_idx = None
                        self.state = "RUNNING"
                        self.resume_run_idx = run_i
                        self.last_event = f"Restarting current run {run_i}"
                        self.publish_status(process="restarting current run", error=None)
                        continue
                    else:
                        self.restart_current_run_requested = False
                        self.last_event = "RESTART_CURRENT_RUN rejected (no run to restart)"
                        self.publish_status()
                        time.sleep(0.2)
                        continue

                if self.state != "RUNNING" or self.program is None:
                    time.sleep(0.2)
                    continue
                prog = self.program
                runs = self.build_runs(prog)
                self.total_n = len(runs)

                if not runs:
                    self.last_event = "Program has no runs"
                    self.state = "IDLE"
                    self.program = None
                    self.publish_status(process="not running", error=self.last_event)
                    time.sleep(0.2)
                    continue

                start_idx = self.resume_run_idx or 1
                if start_idx < 1:
                    start_idx = 1
                if start_idx > len(runs):
                    start_idx = len(runs)

                self.current_i = start_idx - 1
                self.resume_run_idx = None
                self.publish_status(process="running")

                for idx in range(start_idx, len(runs) + 1):
                    r = runs[idx - 1]
                    self._poll_commands()

                    if self.stop_requested and self.state != "RUNNING":
                        self._do_stop()
                        time.sleep(0.2)
                        continue

                    if self.restart_requested and self.state != "RUNNING":
                        self._do_restart()
                        continue

                    if self.restart_requested:
                        raise RuntimeError("RESTART requested")

                    if self.stop_requested:
                        raise RuntimeError("STOP requested")

                    self.current_i = idx
                    self.ap.PEO_time = r["PEO_time"]
                    self.ap.Upos = r["Upos"]
                    self.ap.KOH_concentration = r["KOH"]

                    ch_ratios, labels = self.compute_two_channel_recipe(prog, r["KOH"])

                    # publish fluid preview for this run
                    st = read_json(self.ipc.status_path, default_status())
                    st["fluid"]["total_ml"] = prog.total_ml
                    st["fluid"]["channels"] = ch_ratios
                    st["fluid"]["ratios"] = labels
                    st["iteration"] = {"i": self.current_i, "n": self.total_n}
                    st["state"] = self.state
                    st["program"] = prog.name
                    st["process"] = "running"
                    st["updated_at"] = time.time()
                    st["seen_command_id"] = self.last_seen_command_id
                    atomic_write_json(self.ipc.status_path, st)

                    run_ctx = {"program": prog, "total_ml": prog.total_ml, "mix_channels": ch_ratios}
                    self.last_event = f"Run {idx}/{self.total_n} started"
                    self.publish_status()

                    self._set_run_checkpoints(idx)
            
                    self.ap.cp.force_restart_if_not_allowed({"RECONNECT"})
                    self.ap.cp.run(prog.instructions_path, execute_line=lambda ln: self.execute_line(ln, run_ctx))

                    self.last_event = f"Run {idx}/{self.total_n} finished"
                    self.publish_status(process="run complete")
                    self.ap.line = 1

                # finished normally
                self.last_event = "Program finished"
                self.state = "IDLE"
                self.program = None
                self.stop_requested = False
                self.pause_requested = False
                self.publish_status(process="not running")
                self.failed_run_idx = None
                self.resume_run_idx = None
                self.restart_current_run_requested = False

            except Exception as e:
                msg = f"{type(e).__name__}: {e}"

                if isinstance(e, RestartCurrentRunRequested):
                    run_i = self.resume_run_idx or self.failed_run_idx or self.current_i

                    self.restart_current_run_requested = False
                    self.pause_requested = False
                    self.stop_requested = False
                    self.failed_run_idx = None

                    if run_i and run_i > 0:
                        self.last_event = f"Reconnecting before restarting current run {run_i}"
                        self.publish_status(process="reconnecting", error=None)

                        self.ap.connect()   # yes, full reconnect for now

                        self.state = "RUNNING"
                        self.resume_run_idx = run_i
                        self.last_event = f"Restarting current run {run_i}"
                        self.publish_status(process="restarting current run", error=None)
                        continue

                # 1) STOP should not be treated as "failed run"
                if "STOP requested" in msg:
                    self._do_stop()
                    continue

                # 2) Program RESTART should not be treated as "failed run"
                if "RESTART requested" in msg or self.restart_requested:
                    self.publish_status(process="restarting", error=None)
                    self._do_restart()
                    continue

                # If we are in the middle of a run, pause and allow manual restart-current-run
                if self.state in ("RUNNING", "PAUSED") and self.program is not None and self.current_i > 0:
                    self.failed_run_idx = self.current_i
                    self.resume_run_idx = self.current_i
                    self.state = "PAUSED"
                    self.pause_requested = True
                    self.stop_requested = False  # stop only aborted the current cp.run
                    msg = f"{type(e).__name__}: {e}"
                    self.last_event = f"Run {self.current_i}/{self.total_n} failed (paused)"
                    self.publish_status(process="paused", error=msg)
                    continue

                # ERROR path
                print(traceback.format_exc())
                self.last_event = "ERROR in runner"
                self.state = "ERROR"
                self.publish_status(process="error", error=msg)

                # fall back to IDLE but keep error visible
                self.state = "IDLE"
                self.program = None
                self.stop_requested = False
                self.pause_requested = False
                self.publish_status(process="not running", error=msg)
                time.sleep(0.5)

    def _do_stop(self) -> None:
        self.last_event = "Stopped by command"
        self.state = "IDLE"
        self.program = None
        self.stop_requested = False
        self.pause_requested = False
        self.restart_requested = False
        self.restart_program_name = None
        self.restart_current_run_requested = False
        self.failed_run_idx = None
        self.resume_run_idx = None
        self.current_i = 0
        self.total_n = 0
        self.publish_status(process="not running", error=None)
    
    def _do_restart(self) -> None:
        # Clear running state
        name = self.restart_program_name
        self.restart_requested = False
        self.restart_program_name = None
        self.stop_requested = False
        self.pause_requested = False

        self.restart_current_run_requested = False
        self.failed_run_idx = None
        self.resume_run_idx = 1
        self.current_i = 0
        self.total_n = 0

        if not name:
            self.last_event = "RESTART failed: no program name"
            self.state = "IDLE"
            self.program = None
            self.publish_status(process="not running", error=self.last_event)
            return

        progs = programs_by_name()
        if name not in progs:
            self.last_event = f"RESTART failed: unknown program {name}"
            self.state = "IDLE"
            self.program = None
            self.publish_status(process="not running", error=self.last_event)
            return

        self.last_event = f"Restarting program: {name}"
        self.state = "RUNNING"
        self.program = progs[name]
        self.publish_status(process="restarting")
        self.reset_checkpoints()

    def _set_run_checkpoints(self, run_idx: int) -> None:
        os.makedirs("settings/checkpoints", exist_ok=True)
        state_path = f"settings/checkpoints/run_{run_idx:03d}_state.json"
        log_path = f"settings/checkpoints/run_{run_idx:03d}_events.log"
        self.ap.cp = CheckpointManager(state_path, log_path)

    def _delete_run_checkpoints(self, run_idx: int) -> None:
        state_path = f"settings/checkpoints/run_{run_idx:03d}_state.json"
        log_path = f"settings/checkpoints/run_{run_idx:03d}_events.log"
        for p in (state_path, log_path):
            try:
                os.remove(p)
            except FileNotFoundError:
                pass
    

if __name__ == "__main__":
    Runner(IPCPaths()).loop()