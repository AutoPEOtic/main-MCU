from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

from src.core.errors import DeviceProcessError, StopRequested, ValidationError
from src.core.logging_utils import EventLogger
from src.core.models import CommandResult, ResultCode, RunContext
from src.devices.device_manager import DeviceManager
from src.engine.actions import (
    Action,
    DelayAction,
    HomeAction,
    MotionAction,
    MotionConfigAction,
    PEOOffAction,
    PEOOnAction,
    PEOSendValuesAction,
    PeripheralAction,
    ReconnectAction,
    SolutionAction,
    SpectrumAcquireAction,
)
from src.engine.checkpoint_store import CheckpointStore, CheckpointRecord
from src.engine.instruction_parser import parse_instruction_file


@dataclass
class EngineRunResult:
    ok: bool
    run_context: RunContext
    started_from_action: int
    completed_actions: int
    total_actions: int
    last_result: Optional[CommandResult] = None
    error_text: str = ""


class ExperimentEngine:
    """
    Executes parsed actions through DeviceManager.
    Owns:
      - instruction parsing
      - run-context injection
      - per-action execution
      - per-run checkpointing
    Does NOT own:
      - UI command polling
      - global supervisor state transitions
      - transport-level reconnect internals
    """

    def __init__(
        self,
        device_manager: DeviceManager,
        checkpoint_store: CheckpointStore,
        logger: EventLogger,
    ) -> None:
        self.device_manager = device_manager
        self.checkpoint_store = checkpoint_store
        self.logger = logger
        self._stop_requested = False

    def request_stop(self) -> None:
        self._stop_requested = True

    def clear_stop(self) -> None:
        self._stop_requested = False

    def load_actions(self, instructions_path: str) -> List[Action]:
        actions = parse_instruction_file(instructions_path)
        if not actions:
            raise ValidationError(f"No executable actions found in {instructions_path}")
        return actions

    def execute_run(
        self,
        ctx: RunContext,
        instructions_path: str,
        *,
        resume: bool = True,
        clear_checkpoint_on_success: bool = False,
    ) -> EngineRunResult:
        self.clear_stop()

        raw_actions = self.load_actions(instructions_path)
        actions = self._bind_actions_for_run(raw_actions, ctx)

        start_index = 0
        checkpoint = self.checkpoint_store.load(ctx) if resume else None
        if checkpoint is not None:
            # checkpoint.action_index is last SUCCESSFUL action, so resume from next one
            start_index = checkpoint.action_index + 1
            start_index = min(start_index, len(actions))

        self.logger.info(
            "engine",
            "run",
            "EXECUTE_RUN",
            "START",
            program=ctx.program_name,
            run_index=ctx.run_index,
            total_runs=ctx.total_runs,
            action_start=start_index,
            action_total=len(actions),
            Upos=ctx.Upos,
            PEO_time=ctx.PEO_time,
            KOH_target=ctx.KOH_target,
        )

        last_result: Optional[CommandResult] = None

        try:
            for action_index in range(start_index, len(actions)):
                self._check_stop()

                action = actions[action_index]
                action_name = self._action_name(action)

                self.logger.info(
                    "engine",
                    "run",
                    action_name,
                    "START",
                    action_index=action_index,
                    total_actions=len(actions),
                    run_index=ctx.run_index,
                )

                result = self._execute_action(ctx, action)
                last_result = result

                if result.code != ResultCode.OK:
                    self.checkpoint_store.mark_failed(
                        ctx=ctx,
                        action_index=max(action_index - 1, -1),
                        total_actions=len(actions),
                        action_name=action_name,
                        error_text=result.detail or result.code.value,
                    )
                    self.logger.error(
                        "engine",
                        "run",
                        action_name,
                        detail=result.detail or result.code.value,
                        action_index=action_index,
                        run_index=ctx.run_index,
                    )
                    return EngineRunResult(
                        ok=False,
                        run_context=ctx,
                        started_from_action=start_index,
                        completed_actions=action_index,
                        total_actions=len(actions),
                        last_result=result,
                        error_text=result.detail or result.code.value,
                    )

                self.checkpoint_store.save_success(
                    ctx=ctx,
                    action_index=action_index,
                    total_actions=len(actions),
                    action_name=action_name,
                )

                self.logger.info(
                    "engine",
                    "run",
                    action_name,
                    "OK",
                    action_index=action_index,
                    total_actions=len(actions),
                    run_index=ctx.run_index,
                )

            if clear_checkpoint_on_success:
                self.checkpoint_store.clear(ctx)

            self.logger.info(
                "engine",
                "run",
                "EXECUTE_RUN",
                "OK",
                program=ctx.program_name,
                run_index=ctx.run_index,
                total_runs=ctx.total_runs,
                total_actions=len(actions),
            )

            return EngineRunResult(
                ok=True,
                run_context=ctx,
                started_from_action=start_index,
                completed_actions=len(actions),
                total_actions=len(actions),
                last_result=last_result,
                error_text="",
            )

        except StopRequested as exc:
            self.checkpoint_store.mark_failed(
                ctx=ctx,
                action_index=start_index - 1,
                total_actions=len(actions),
                action_name="STOP",
                error_text=str(exc),
            )
            self.logger.error(
                "engine",
                "run",
                "STOP",
                detail=str(exc),
                run_index=ctx.run_index,
            )
            return EngineRunResult(
                ok=False,
                run_context=ctx,
                started_from_action=start_index,
                completed_actions=start_index,
                total_actions=len(actions),
                last_result=last_result,
                error_text=str(exc),
            )

    def _check_stop(self) -> None:
        if self._stop_requested:
            raise StopRequested("Execution stop requested")

    def _bind_actions_for_run(self, actions: List[Action], ctx: RunContext) -> List[Action]:
        bound: List[Action] = []

        for action in actions:
            if isinstance(action, SolutionAction):
                bound.append(
                    SolutionAction(
                        total_ml=ctx.total_ml,
                        channels=dict(ctx.mix_channels),
                        timeout_s=action.timeout_s,
                    )
                )
            elif isinstance(action, PEOOnAction):
                duration_s = ctx.PEO_time if action.duration_s < 0 else action.duration_s
                bound.append(PEOOnAction(duration_s=duration_s))
            else:
                bound.append(action)

        return bound

    def _execute_action(self, ctx: RunContext, action: Action) -> CommandResult:
        if isinstance(action, DelayAction):
            time.sleep(action.seconds)
            return CommandResult(
                device="engine",
                command=f"PAUSE {action.seconds}",
                code=ResultCode.OK,
                detail=f"slept {action.seconds} s",
            )

        if isinstance(action, ReconnectAction):
            if action.target != "all":
                raise ValidationError(f"Unsupported reconnect target: {action.target}")
            self.device_manager.reconnect_all(cycle_bus=True)
            return CommandResult(
                device="engine",
                command="RECONNECT",
                code=ResultCode.OK,
                detail="all devices reconnected",
            )

        if isinstance(action, MotionAction):
            return self.device_manager.send_motion(action.command)

        if isinstance(action, MotionConfigAction):
            return self.device_manager.send_motion_config(action.command, wait_idle=False)

        if isinstance(action, HomeAction):
            return self.device_manager.home_motion()

        if isinstance(action, PeripheralAction):
            return self.device_manager.send_peripheral_text(
                cmd=action.command,
                timeout_s=action.timeout_s,
            )

        if isinstance(action, SolutionAction):
            return self.device_manager.send_solution(
                total_ml=action.total_ml,
                channels=action.channels,
                timeout_s=action.timeout_s,
            )

        if isinstance(action, SpectrumAcquireAction):
            return self.device_manager.acquire_spectrum()

        if isinstance(action, PEOSendValuesAction):
            return self.device_manager.peo_send_values(ctx.Upos)

        if isinstance(action, PEOOnAction):
            return self.device_manager.peo_on(action.duration_s)

        if isinstance(action, PEOOffAction):
            return self.device_manager.peo_off()

        raise ValidationError(f"Unsupported action type: {type(action).__name__}")

    @staticmethod
    def _action_name(action: Action) -> str:
        return type(action).__name__
