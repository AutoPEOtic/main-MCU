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
from src.core.recovery_policy import FailureClass, RecoveryAction, RecoveryDecision
from src.core.models import DeviceName


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
        self._run_retry_counts: Dict[int, int] = {}

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
            self._run_retry_counts = {}
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
            self._last_error = ""
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
                    self._clear_run_retry(ctx.run_index)

                    self.logger.info(
                        "supervisor",
                        "runtime",
                        "RUN_ONE",
                        "OK",
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                    )

                    with self._lock:
                        self._last_error = ""
                        self._last_event = f"Run {ctx.run_index}/{ctx.total_runs} finished"

                        if self._restart_program_requested:
                            self._restart_program_requested = False
                            run_idx = 0
                            self._current_run_index = 0
                            self._run_retry_counts = {}
                            self._last_event = "Restarting full program"
                            continue

                        if self._restart_run_requested:
                            self._restart_run_requested = False
                            self.checkpoint_store.clear(ctx)
                            self._clear_run_retry(ctx.run_index)
                            self._last_event = "Restarting current run"
                            continue

                    run_idx += 1
                    continue

                # ------------------------------
                # run failed -> policy handling
                # ------------------------------
                with self._lock:
                    self._last_error = result.error_text or "Run failed"
                    self._last_event = f"Run {ctx.run_index}/{ctx.total_runs} failed"

                    if self._stop_requested:
                        self.state_machine.transition(SupervisorState.STOPPING)
                        self._last_event = "Stopping experiment after failure"
                        break

                    if self._restart_program_requested:
                        self._restart_program_requested = False
                        run_idx = 0
                        self._current_run_index = 0
                        self._run_retry_counts = {}
                        self._last_error = ""
                        self._last_event = "Restarting full program after failure"
                        continue

                    if self._restart_run_requested:
                        self._restart_run_requested = False
                        self.checkpoint_store.clear(ctx)
                        self._clear_run_retry(ctx.run_index)
                        self._last_error = ""
                        self._last_event = "Restarting current run after failure"
                        continue

                decision = self._decide_recovery(result)
                attempt = self._increment_run_retry(ctx.run_index)

                self.logger.info(
                    "supervisor",
                    "runtime",
                    "RECOVERY_DECISION",
                    decision.action.value,
                    run_index=ctx.run_index,
                    total_runs=ctx.total_runs,
                    attempt=attempt,
                    max_retries=decision.max_retries,
                    detail=decision.detail,
                )

                if decision.max_retries > 0 and attempt > decision.max_retries:
                    with self._lock:
                        self._last_error = (
                            f"{decision.detail}; exceeded retry limit "
                            f"({decision.max_retries})"
                        )
                        self._last_event = (
                            f"Run {ctx.run_index}/{ctx.total_runs} exceeded retry limit"
                        )
                        self.state_machine.transition(SupervisorState.ERROR)

                    self.logger.error(
                        "supervisor",
                        "runtime",
                        "RECOVERY_LIMIT_EXCEEDED",
                        detail=self._last_error,
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                        attempt=attempt,
                    )
                    return

                try:
                    if decision.reconnect_motion:
                        self.device_manager.recover_motion_basic()

                    if decision.reconnect_peripheral:
                        self.device_manager.recover_peripheral_basic(
                            do_home_all=decision.require_peripheral_home_all
                        )

                    if decision.reconnect_peo:
                        self.device_manager.reconnect_device(DeviceName.PEO)
                        self.device_manager.healthcheck_device(DeviceName.PEO)

                    if decision.reconnect_spectrometer:
                        self.device_manager.reconnect_device(DeviceName.SPECTROMETER)
                        self.device_manager.healthcheck_device(DeviceName.SPECTROMETER)

                except Exception as recovery_exc:
                    with self._lock:
                        self._last_error = f"Recovery failed: {recovery_exc}"
                        self._last_event = (
                            f"Recovery failed for run {ctx.run_index}/{ctx.total_runs}"
                        )
                        self.state_machine.transition(SupervisorState.ERROR)

                    self.logger.error(
                        "supervisor",
                        "runtime",
                        "RECOVERY_FAILED",
                        detail=str(recovery_exc),
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                        attempt=attempt,
                    )
                    return

                if decision.action == RecoveryAction.RESTART_RUN:
                    if decision.clear_current_run_checkpoint:
                        self.checkpoint_store.clear(ctx)

                    with self._lock:
                        self._last_error = ""
                        self._last_event = f"Restarting run {ctx.run_index}/{ctx.total_runs}"

                    self.logger.info(
                        "supervisor",
                        "runtime",
                        "RESTART_RUN",
                        "OK",
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                        attempt=attempt,
                    )
                    continue

                if decision.action in (
                    RecoveryAction.RETRY_STEP,
                    RecoveryAction.RECONNECT_AND_CONTINUE,
                ):
                    with self._lock:
                        self._last_error = ""
                        self._last_event = (
                            f"Recovering and continuing run {ctx.run_index}/{ctx.total_runs}"
                        )

                    self.logger.info(
                        "supervisor",
                        "runtime",
                        "CONTINUE_AFTER_RECOVERY",
                        "OK",
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                        attempt=attempt,
                    )
                    continue

                if decision.action in (
                    RecoveryAction.MANUAL_INTERVENTION,
                    RecoveryAction.STOP,
                    RecoveryAction.RESTART_PROGRAM,
                ):
                    with self._lock:
                        if decision.action == RecoveryAction.RESTART_PROGRAM:
                            self._last_error = ""
                            self._last_event = "Restarting full program by recovery policy"
                            self._run_retry_counts = {}
                            run_idx = 0
                            self._current_run_index = 0
                            continue

                        self._last_error = decision.detail or (result.error_text or "Run failed")
                        self._last_event = (
                            f"Run {ctx.run_index}/{ctx.total_runs} requires manual intervention"
                        )
                        self.state_machine.transition(SupervisorState.ERROR)

                    self.logger.error(
                        "supervisor",
                        "runtime",
                        "RUN_ONE",
                        detail=self._last_error,
                        run_index=ctx.run_index,
                        total_runs=ctx.total_runs,
                        attempt=attempt,
                    )
                    return

                with self._lock:
                    self._last_error = f"Unhandled recovery action: {decision.action}"
                    self._last_event = "Unhandled recovery action"
                    self.state_machine.transition(SupervisorState.ERROR)

                self.logger.error(
                    "supervisor",
                    "runtime",
                    "UNHANDLED_RECOVERY_ACTION",
                    detail=str(decision.action),
                    run_index=ctx.run_index,
                    total_runs=ctx.total_runs,
                    attempt=attempt,
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
        
    def has_program_loaded(self) -> bool:
        with self._lock:
            return self._program is not None

    def active_thread_alive(self) -> bool:
        with self._lock:
            return self._active_thread is not None and self._active_thread.is_alive()
        
    def _decide_recovery(self, result: EngineRunResult) -> RecoveryDecision:
        last = result.last_result
        if last is None:
            return RecoveryDecision(
                failure_class=FailureClass.UNKNOWN,
                action=RecoveryAction.MANUAL_INTERVENTION,
                detail="No last_result available",
            )

        fc = last.failure_class or FailureClass.UNKNOWN.value

        if fc == FailureClass.OPERATOR_STOP.value:
            return RecoveryDecision(
                failure_class=FailureClass.OPERATOR_STOP,
                action=RecoveryAction.RECONNECT_AND_CONTINUE,
                detail="Operator stop allows continue from checkpoint",
            )

        if fc == FailureClass.MOTION_POSE_UNCERTAIN.value:
            return RecoveryDecision(
                failure_class=FailureClass.MOTION_POSE_UNCERTAIN,
                action=RecoveryAction.RESTART_RUN,
                max_retries=3,
                clear_current_run_checkpoint=True,
                reconnect_motion=True,
                require_motion_status_check=True,
                detail="Motion pose uncertain, restart current run",
            )

        if fc == FailureClass.DEVICE_PROCESS.value:
            last_cmd = last.command.upper()
            if last_cmd.startswith("HOME ALL"):
                return RecoveryDecision(
                    failure_class=FailureClass.DEVICE_PROCESS,
                    action=RecoveryAction.RETRY_STEP,
                    max_retries=3,
                    reconnect_peripheral=False,
                    require_peripheral_status_check=True,
                    require_peripheral_home_all=True,
                    detail="Retry peripheral homing",
                )
            if last_cmd.startswith("SOLUTION"):
                return RecoveryDecision(
                    failure_class=FailureClass.DEVICE_PROCESS,
                    action=RecoveryAction.RESTART_RUN,
                    max_retries=3,
                    clear_current_run_checkpoint=True,
                    reconnect_peripheral=True,
                    require_peripheral_status_check=True,
                    require_peripheral_home_all=True,
                    detail="SOLUTION failure requires run restart",
                )

        if fc == FailureClass.TRANSPORT.value:
            cmd = (last.command or "").upper()
            if "PEO" in cmd:
                return RecoveryDecision(
                    failure_class=FailureClass.TRANSPORT,
                    action=RecoveryAction.RECONNECT_AND_CONTINUE,
                    max_retries=3,
                    reconnect_peo=True,
                    detail="Reconnect PEO and continue",
                )
            if "SPECTRUM" in cmd:
                return RecoveryDecision(
                    failure_class=FailureClass.TRANSPORT,
                    action=RecoveryAction.RECONNECT_AND_CONTINUE,
                    max_retries=3,
                    reconnect_spectrometer=True,
                    detail="Reconnect spectrometer and continue",
                )
            return RecoveryDecision(
                failure_class=FailureClass.TRANSPORT,
                action=RecoveryAction.MANUAL_INTERVENTION,
                max_retries=3,
                detail="Generic transport failure needs manual review",
            )

        return RecoveryDecision(
            failure_class=FailureClass.UNKNOWN,
            action=RecoveryAction.MANUAL_INTERVENTION,
            detail="Unknown failure class",
        )
    
    def _increment_run_retry(self, run_index: int) -> int:
        self._run_retry_counts[run_index] = self._run_retry_counts.get(run_index, 0) + 1
        return self._run_retry_counts[run_index]

    def _clear_run_retry(self, run_index: int) -> None:
        self._run_retry_counts.pop(run_index, None)