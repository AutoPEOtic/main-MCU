from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Dict, List, Optional

from src.core.errors import SupervisorStateError, ValidationError
from src.core.logging_utils import EventLogger
from src.core.models import ProgramDefinition, RunContext, RuntimeSnapshot
from src.devices.device_manager import DeviceManager
from src.engine.checkpoint_store import CheckpointStore
from src.engine.experiment_engine import EngineRunResult, ExperimentEngine
from src.engine.run_plan import as_run_context, build_run_plan
from src.supervisor.state_machine import StateMachine, SupervisorState


class Supervisor:
    """
    Global runtime owner.

    Responsibilities:
      - global lifecycle state
      - startup / shutdown of devices
      - run-plan construction
      - sequential run execution
      - pause / stop / restart intent flags
      - runtime snapshot for UI

    Does NOT own:
      - parsing device protocols
      - per-command transport behavior
      - line-by-line instruction execution
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        engine: ExperimentEngine,
        checkpoint_store: CheckpointStore,
        logger: EventLogger,
    ) -> None:
        self.device_manager = device_manager
        self.engine = engine
        self.checkpoint_store = checkpoint_store
        self.logger = logger

        self.state_machine = StateMachine()
        self._lock = threading.RLock()

        self._program: Optional[ProgramDefinition] = None
        self._runs = []
        self._current_run_index = 0
        self._last_error = ""
        self._last_event = ""

        self._pause_requested = False
        self._stop_requested = False
        self._restart_run_requested = False
        self._restart_program_requested = False

        self._active_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # lifecycle
    # ------------------------------------------------------------------

    def load_program(self, program: ProgramDefinition) -> None:
        with self._lock:
            if self.state_machine.state not in (SupervisorState.IDLE, SupervisorState.ERROR):
                raise SupervisorStateError(
                    f"Cannot load program while state is {self.state_machine.state}"
                )

            runs = build_run_plan(program)
            if not runs:
                raise ValidationError("Program produced zero runs")

            self._program = program
            self._runs = runs
            self._current_run_index = 0
            self._last_error = ""
            self._last_event = f"Program loaded: {program.name}"

            self.logger.info(
                "supervisor",
                "runtime",
                "LOAD_PROGRAM",
                "OK",
                program=program.name,
                total_runs=len(runs),
            )

    def startup(self) -> None:
        with self._lock:
            if self.state_machine.state != SupervisorState.IDLE:
                raise SupervisorStateError(
                    f"Cannot startup while state is {self.state_machine.state}"
                )

            self.state_machine.transition(SupervisorState.STARTING)
            self._last_event = "Starting devices"

        try:
            self.device_manager.startup_all()

            with self._lock:
                self.state_machine.transition(SupervisorState.IDLE)
                self._last_event = "Devices started"

            self.logger.info("supervisor", "runtime", "STARTUP", "OK")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._last_event = "Startup failed"
                self.state_machine.transition(SupervisorState.ERROR)

            self.logger.error("supervisor", "runtime", "STARTUP", detail=str(exc))
            raise

    def shutdown(self) -> None:
        with self._lock:
            self._last_event = "Shutting down devices"

        try:
            self.device_manager.shutdown_all()

            with self._lock:
                if self.state_machine.state != SupervisorState.IDLE:
                    try:
                        self.state_machine.transition(SupervisorState.IDLE)
                    except Exception:
                        pass
                self._last_event = "Devices shut down"

            self.logger.info("supervisor", "runtime", "SHUTDOWN", "OK")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._last_event = "Shutdown failed"
                try:
                    self.state_machine.transition(SupervisorState.ERROR)
                except Exception:
                    pass

            self.logger.error("supervisor", "runtime", "SHUTDOWN", detail=str(exc))
            raise

    # ------------------------------------------------------------------
    # control flags
    # ------------------------------------------------------------------

    def request_pause(self) -> None:
        with self._lock:
            self._pause_requested = True
            self._last_event = "Pause requested"
        self.logger.info("supervisor", "runtime", "PAUSE_REQUEST", "OK")

    def clear_pause(self) -> None:
        with self._lock:
            self._pause_requested = False
            self._last_event = "Pause cleared"
        self.logger.info("supervisor", "runtime", "PAUSE_CLEAR", "OK")

    def request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            self._last_event = "Stop requested"
        self.engine.request_stop()
        self.logger.info("supervisor", "runtime", "STOP_REQUEST", "OK")

    def request_restart_run(self) -> None:
        with self._lock:
            self._restart_run_requested = True
            self._last_event = "Restart current run requested"
        self.engine.request_stop()
        self.logger.info("supervisor", "runtime", "RESTART_RUN_REQUEST", "OK")

    def request_restart_program(self) -> None:
        with self._lock:
            self._restart_program_requested = True
            self._last_event = "Restart program requested"
        self.engine.request_stop()
        self.logger.info("supervisor", "runtime", "RESTART_PROGRAM_REQUEST", "OK")

    def clear_control_flags(self) -> None:
        with self._lock:
            self._pause_requested = False
            self._stop_requested = False
            self._restart_run_requested = False
            self._restart_program_requested = False

    # ------------------------------------------------------------------
    # execution
    # ------------------------------------------------------------------

    def run_blocking(
        self,
        *,
        resume_runs: bool = True,
        clear_run_checkpoint_on_success: bool = False,
    ) -> None:
        with self._lock:
            if self._program is None:
                raise ValidationError("No program loaded")

            if self.state_machine.state != SupervisorState.IDLE:
                raise SupervisorStateError(
                    f"Cannot start run while state is {self.state_machine.state}"
                )

            self.clear_control_flags()
            self.state_machine.transition(SupervisorState.RUNNING)
            self._last_event = "Experiment started"
            program = self._program
            total_runs = len(self._runs)

        self.logger.info(
            "supervisor",
            "runtime",
            "RUN_BLOCKING",
            "START",
            program=program.name,
            total_runs=total_runs,
        )

        try:
            run_idx = self._current_run_index

            while run_idx < total_runs:
                with self._lock:
                    self._current_run_index = run_idx

                self._wait_if_paused()

                with self._lock:
                    if self._stop_requested:
                        self.state_machine.transition(SupervisorState.STOPPING)
                        self._last_event = "Stopping experiment"
                        break

                compiled_run = self._runs[run_idx]
                ctx = as_run_context(program, compiled_run, total_runs=total_runs)

                self.logger.info(
                    "supervisor",
                    "runtime",
                    "RUN_ONE",
                    "START",
                    run_index=ctx.run_index,
                    total_runs=ctx.total_runs,
                    Upos=ctx.Upos,
                    PEO_time=ctx.PEO_time,
                    KOH_target=ctx.KOH_target,
                )

                result = self.engine.execute_run(
                    ctx=ctx,
                    instructions_path=program.instructions_path,
                    resume=resume_runs,
                    clear_checkpoint_on_success=clear_run_checkpoint_on_success,
                )

                if result.ok:
                    self.logger.info(
                        "supervisor",
                        "runtime",
                        "RUN_ONE",
                        "OK",
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                    )

                    with self._lock:
                        self._last_event = f"Run {ctx.run_index}/{ctx.total_runs} finished"
                        if self._restart_program_requested:
                            run_idx = 0
                            self._current_run_index = 0
                            self._restart_program_requested = False
                            self._last_event = "Restarting full program"
                            continue

                        if self._restart_run_requested:
                            self._restart_run_requested = False
                            self._last_event = "Restarting current run"
                            continue

                    run_idx += 1
                    continue

                # result not ok
                with self._lock:
                    self._last_error = result.error_text or "Run failed"
                    self._last_event = f"Run {ctx.run_index}/{ctx.total_runs} failed"

                    if self._stop_requested:
                        self.state_machine.transition(SupervisorState.STOPPING)
                        break

                    if self._restart_program_requested:
                        self._restart_program_requested = False
                        run_idx = 0
                        self._current_run_index = 0
                        self._last_event = "Restarting full program after failure"
                        try:
                            self.state_machine.transition(SupervisorState.RUNNING)
                        except Exception:
                            pass
                        continue

                    if self._restart_run_requested:
                        self._restart_run_requested = False
                        self._last_event = "Restarting current run after failure"
                        try:
                            self.state_machine.transition(SupervisorState.RUNNING)
                        except Exception:
                            pass
                        continue

                    self.state_machine.transition(SupervisorState.ERROR)
                    self.logger.error(
                        "supervisor",
                        "runtime",
                        "RUN_ONE",
                        detail=result.error_text or "Run failed",
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                    )
                    return

            with self._lock:
                if self.state_machine.state == SupervisorState.STOPPING:
                    self.state_machine.transition(SupervisorState.IDLE)
                    self._last_event = "Experiment stopped"
                elif self.state_machine.state == SupervisorState.RUNNING:
                    self.state_machine.transition(SupervisorState.IDLE)
                    self._last_event = "Experiment finished"

            self.logger.info("supervisor", "runtime", "RUN_BLOCKING", "OK")

        except Exception as exc:
            with self._lock:
                self._last_error = str(exc)
                self._last_event = "Supervisor runtime failure"
                try:
                    self.state_machine.transition(SupervisorState.ERROR)
                except Exception:
                    pass

            self.logger.error("supervisor", "runtime", "RUN_BLOCKING", detail=str(exc))
            raise

    def run_async(
        self,
        *,
        resume_runs: bool = True,
        clear_run_checkpoint_on_success: bool = False,
        daemon: bool = True,
    ) -> None:
        with self._lock:
            if self._active_thread is not None and self._active_thread.is_alive():
                raise SupervisorStateError("Supervisor thread is already active")

            thread = threading.Thread(
                target=self.run_blocking,
                kwargs={
                    "resume_runs": resume_runs,
                    "clear_run_checkpoint_on_success": clear_run_checkpoint_on_success,
                },
                daemon=daemon,
            )
            self._active_thread = thread
            thread.start()

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _wait_if_paused(self) -> None:
        while True:
            with self._lock:
                if self._pause_requested and self.state_machine.state == SupervisorState.RUNNING:
                    self.state_machine.transition(SupervisorState.PAUSED)
                    self._last_event = "Paused"

                if self.state_machine.state != SupervisorState.PAUSED:
                    return

                if self._stop_requested:
                    self.state_machine.transition(SupervisorState.STOPPING)
                    self._last_event = "Stopping from pause"
                    return

                if not self._pause_requested:
                    self.state_machine.transition(SupervisorState.RUNNING)
                    self._last_event = "Resumed"
                    return

            threading.Event().wait(0.2)

    # ------------------------------------------------------------------
    # snapshot / inspection
    # ------------------------------------------------------------------

    def runtime_snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            program_name = self._program.name if self._program else None
            total_runs = len(self._runs)

            params: Dict[str, object] = {}
            if self._program is not None and self._runs and 0 <= self._current_run_index < len(self._runs):
                run = self._runs[self._current_run_index]
                params = {
                    "Upos": run.Upos,
                    "PEO_time": run.PEO_time,
                    "KOH_target": run.KOH_target,
                    "total_ml": run.total_ml,
                    "mix_channels": dict(run.mix_channels),
                    "mix_labels": dict(run.mix_labels),
                }

            return RuntimeSnapshot(
                supervisor_state=self.state_machine.state.value,
                program_name=program_name,
                run_index=self._current_run_index + 1 if total_runs else 0,
                total_runs=total_runs,
                process=self._last_event,
                params=params,
                devices=self.device_manager.snapshot_devices(),
                last_event=self._last_event,
                error=self._last_error or None,
            )

    def is_running(self) -> bool:
        with self._lock:
            return self.state_machine.state in (
                SupervisorState.STARTING,
                SupervisorState.RUNNING,
                SupervisorState.PAUSED,
                SupervisorState.STOPPING,
                SupervisorState.RECOVERING,
            )

    def current_state(self) -> str:
        with self._lock:
            return self.state_machine.state.value