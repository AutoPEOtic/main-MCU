# src/checkpoint.py
# Clean checkpoint manager for instruction-file execution with "CHECKPOINT <name>" markers.
# Persists only "last_done" + timestamps, and keeps an append-only event log.
#
# Usage pattern:
#   cp = CheckpointManager("settings/checkpoint_state.json", "settings/checkpoint_events.log")
#   cp.run(instructions_path="instructions.txt", execute_line=auto.send_instruction)
#
# Instruction-file markers:
#   CHECKPOINT SAFE_ABOVE_CHAMBER_ENTRY
#   ...commands...
#   CHECKPOINT IN_CHAMBER
#   ...commands...
#
# Semantics:
#   - A checkpoint block starts at "CHECKPOINT X" and ends right before the next "CHECKPOINT Y".
#   - Checkpoint X is considered DONE when "CHECKPOINT Y" is reached (i.e., the block completed).
#   - Resume starts from the line after last_done checkpoint marker (if present), else from start.

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional, List, Dict, Any


@dataclass
class CheckpointState:
    last_done: Optional[str] = None
    last_done_at: Optional[str] = None
    run_started_at: Optional[str] = None


class CheckpointManager:
    def __init__(self, state_path: str, events_path: str):
        self.state_path = state_path
        self.events_path = events_path
        self._run_started_monotonic = time.monotonic()
        self._run_started_at_iso = self._now_iso()

    # -----------------
    # Time / logging
    # -----------------
    @staticmethod
    def _now_iso():
        return datetime.now(timezone.utc).isoformat()

    def _elapsed_s(self):
        return round(time.monotonic() - self._run_started_monotonic, 3)

    def _log_event(self, event: str, checkpoint: Optional[str] = None, extra: str = ""):
        """
        Append-only, human-readable log line.
        """
        os.makedirs(os.path.dirname(self.events_path) or ".", exist_ok=True)
        line = (
            f"{self._now_iso()}\telapsed={self._elapsed_s()}s\t"
            f"event={event}\tcheckpoint={(checkpoint or '-')}"
        )
        if extra:
            line += f"\textra={extra}"
        with open(self.events_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

    # -----------------
    # State persistence
    # -----------------
    def load_state(self):
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return CheckpointState(
                last_done=raw.get("last_done"),
                last_done_at=raw.get("last_done_at"),
                run_started_at=raw.get("run_started_at"),
            )
        except FileNotFoundError:
            return CheckpointState(last_done=None, last_done_at=None, run_started_at=None)
        except Exception:
            # If corrupted, don't brick the run. Start fresh.
            return CheckpointState(last_done=None, last_done_at=None, run_started_at=None)

    def save_last_done(self, checkpoint: Optional[str]):
        os.makedirs(os.path.dirname(self.state_path) or ".", exist_ok=True)
        state = {
            "last_done": checkpoint,
            "last_done_at": self._now_iso() if checkpoint else None,
            "run_started_at": self._run_started_at_iso,
        }
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.state_path)

    def clear_state(self):
        """
        Clears state to start from the beginning on next run.
        """
        self.save_last_done(None)
        self._log_event("state_cleared")

    # -----------------
    # Instruction parsing
    # -----------------
    @staticmethod
    def strip_comment(line: str):
        # Your instruction files use ';' for comments. Keep consistent.
        return line.split(";", 1)[0].strip()

    @staticmethod
    def parse_checkpoint_marker(line: str):
        """
        Returns checkpoint name if line is a marker, else None.
        Accepts:
          CHECKPOINT NAME
        """
        core = CheckpointManager.strip_comment(line)
        if not core:
            return None
        parts = core.split()
        if len(parts) >= 2 and parts[0].upper() == "CHECKPOINT":
            return " ".join(parts[1:]).strip()
        return None

    @staticmethod
    def load_instructions(path: str):
        with open(path, "r", encoding="utf-8") as f:
            return f.readlines()

    def find_resume_index(self, lines: List[str], last_done: Optional[str]):
        """
        Resume from the line *after* the marker "CHECKPOINT <last_done>".
        If not found or last_done is None -> resume from 0.
        """
        if not last_done:
            return 0

        for i, raw in enumerate(lines):
            name = self.parse_checkpoint_marker(raw)
            if name == last_done:
                return i + 1

        # If user edited file and removed/renamed checkpoint: safest is restart from top.
        self._log_event("resume_checkpoint_missing", checkpoint=last_done)
        return 0

    # -----------------
    # Executor
    # -----------------
    def run(
        self,
        instructions_path: str,
        execute_line: Callable[[str], None],
        *,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        """
        Executes the instruction file with checkpoint-based resume.

        - execute_line(line) should execute one instruction synchronously.
          It may raise; we will log and re-raise.

        No special handling for RECONNECT is required here, because RECONNECT should be handled
        inside execute_line (your autopeotic.send_instruction), and it should be a hard barrier
        that returns after reconnect.
        """
        lines = self.load_instructions(instructions_path)
        state = self.load_state()

        idx = self.find_resume_index(lines, state.last_done)
        self._log_event("run_start", checkpoint=state.last_done, extra=f"resume_index={idx}")
        print(f"[CHECKPOINT] resume_from={state.last_done} line_index={idx}")

        current_checkpoint: Optional[str] = None
        last_done = state.last_done

        # Note: if we resume mid-block, current_checkpoint is unknown until we hit the next marker.
        while idx < len(lines):
            raw = lines[idx]
            idx += 1

            core = self.strip_comment(raw)
            if not core:
                continue

            # Marker line
            cp = self.parse_checkpoint_marker(core)
            if cp:
                # Entering a new checkpoint means the previous block completed.
                if current_checkpoint is not None:
                    last_done = current_checkpoint
                    self.save_last_done(last_done)
                    self._log_event("checkpoint_done", checkpoint=last_done)
                    print(f"[CHECKPOINT] done {last_done}")

                current_checkpoint = cp
                self._log_event("checkpoint_start", checkpoint=current_checkpoint)
                print(f"[CHECKPOINT] start {current_checkpoint}")
                continue

            # Normal instruction
            try:
                execute_line(core)
            except Exception as e:
                # Log error in context of current checkpoint (if known)
                self._log_event("error", checkpoint=current_checkpoint, extra=str(e))
                if on_error:
                    on_error(e)
                raise

        # End of file: mark the last open checkpoint as done (if any)
        if current_checkpoint is not None and current_checkpoint != last_done:
            last_done = current_checkpoint
            self.save_last_done(last_done)
            self._log_event("checkpoint_done_eof", checkpoint=last_done)
            print(f"[CHECKPOINT] done {last_done} (EOF)")

        self._log_event("run_end", checkpoint=last_done)
        print("[CHECKPOINT] run_end")

    def should_resume(self, allowed_last_done: set[str]):
        st = self.load_state()
        return (st.last_done is not None) and (st.last_done in allowed_last_done)

    def force_restart_if_not_allowed(self, allowed_last_done: set[str]):
        st = self.load_state()
        if st.last_done is None:
            return  # already starting from beginning

        if st.last_done not in allowed_last_done:
            self._log_event(
                "forced_restart",
                checkpoint=st.last_done,
                extra=f"allowed={sorted(allowed_last_done)}"
            )
            self.clear_state()