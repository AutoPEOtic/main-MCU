from __future__ import annotations

import time
import settings.config as legacy_config

from src.config.runtime_config import from_legacy_config
from src.core.logging_utils import EventLogger
from src.core.models import ProgramDefinition
from src.devices.device_manager import DeviceManager
from src.engine.checkpoint_store import CheckpointStore
from src.engine.experiment_engine import ExperimentEngine
from src.supervisor.command_bridge import CommandBridge
from src.supervisor.runtime_store import RuntimeStore
from src.supervisor.supervisor import Supervisor


POLL_INTERVAL_S = 0.25


def build_default_program() -> ProgramDefinition:
    """
    Temporary bridge from legacy config to the new runtime.
    Later this can be replaced by true UI-selected programs.
    """
    return ProgramDefinition(
        name="default_program",
        instructions_path="settings/instructions.txt",
        Upos_values=list(legacy_config.Upos_array),
        PEO_time_values=list(legacy_config.time_array),
        KOH_targets=list(legacy_config.KOH_array),
        total_ml=float(getattr(legacy_config, "solution_volume_ml", 30.0)),
        water_channel="CH1",
        koh_stock_channel="CH2",
        water_conc=0.0,
        koh_stock_conc=1.0,
    )


def main() -> None:
    cfg = from_legacy_config(legacy_config)
    logger = EventLogger(cfg.event_log_path)

    device_manager = DeviceManager(cfg, logger)
    checkpoint_store = CheckpointStore("settings/checkpoints")
    engine = ExperimentEngine(device_manager, checkpoint_store, logger)
    supervisor = Supervisor(device_manager, engine, checkpoint_store, logger)

    command_bridge = CommandBridge("settings/ui_command.json")
    runtime_store = RuntimeStore("settings/runtime_snapshot.json")

    devices_started = False

    logger.info("app", "runtime", "APP_MAIN", "START")

    while True:
        try:
            runtime_store.write_snapshot(supervisor.runtime_snapshot())

            cmd = command_bridge.read_once()
            if cmd is not None:
                action = cmd.action
                payload = cmd.payload

                logger.info("app", "runtime", f"COMMAND:{action}", "START", **payload)

                if action == "load_program":
                    supervisor.load_program(build_default_program())

                elif action == "startup":
                    supervisor.startup()
                    devices_started = True

                elif action == "run":
                    if not supervisor.has_program_loaded():
                        supervisor.load_program(build_default_program())

                    if not devices_started:
                        supervisor.startup()
                        devices_started = True

                    if not supervisor.active_thread_alive():
                        supervisor.run_async(
                            resume_runs=bool(payload.get("resume_runs", True)),
                            clear_run_checkpoint_on_success=bool(
                                payload.get("clear_run_checkpoint_on_success", False)
                            ),
                            daemon=True,
                        )

                elif action == "startup_and_run":
                    if not supervisor.has_program_loaded():
                        supervisor.load_program(build_default_program())

                    if not devices_started:
                        supervisor.startup()
                        devices_started = True

                    if not supervisor.active_thread_alive():
                        checkpoint_store.clear_program(build_default_program().name)
                        supervisor.run_async(
                            resume_runs=False,
                            clear_run_checkpoint_on_success=bool(
                                payload.get("clear_run_checkpoint_on_success", False)
                            ),
                            daemon=True,
                        )

                elif action == "pause":
                    supervisor.request_pause()

                elif action == "resume":
                    supervisor.clear_pause()

                elif action == "stop":
                    supervisor.request_stop()

                elif action == "restart_run":
                    supervisor.request_restart_run()

                elif action == "restart_program":
                    supervisor.request_restart_program()

                elif action == "shutdown":
                    supervisor.shutdown()
                    devices_started = False

                elif action == "status":
                    # no-op: snapshot is already written every cycle
                    pass

                else:
                    logger.error("app", "runtime", f"COMMAND:{action}", detail="Unknown action")

                logger.info("app", "runtime", f"COMMAND:{action}", "OK")

        except Exception as exc:
            logger.error("app", "runtime", "LOOP", detail=str(exc))

        time.sleep(POLL_INTERVAL_S)


if __name__ == "__main__":
    main()