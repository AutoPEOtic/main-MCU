from __future__ import annotations

import sys

from src.supervisor.command_bridge import CommandBridge


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python3 -m src.command_test <action>")
        print("Actions: load_program, startup, run, startup_and_run, pause, resume, stop, restart_run, restart_program, shutdown, status")
        return

    action = sys.argv[1].strip().lower()
    bridge = CommandBridge("settings/ui_command.json")

    payload = {}
    if action in ("run", "startup_and_run"):
        payload = {
            "resume_runs": True,
            "clear_run_checkpoint_on_success": False,
        }

    bridge.write_command(action, payload)
    print(f"Wrote command: {action}")


if __name__ == "__main__":
    main()