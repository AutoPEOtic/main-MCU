import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

# The layered modules type-reference legacy adapters at import time. Stub their
# optional hardware libraries so this test suite cannot open a real device.
serial = types.ModuleType("serial")
serial.Serial = object
serial_tools = types.ModuleType("serial.tools")
serial_list_ports = types.ModuleType("serial.tools.list_ports")
serial_list_ports.comports = lambda: []
serial_tools.list_ports = serial_list_ports
serial.tools = serial_tools
sys.modules.setdefault("serial", serial)
sys.modules.setdefault("serial.tools", serial_tools)
sys.modules.setdefault("serial.tools.list_ports", serial_list_ports)

pymodbus = types.ModuleType("pymodbus")
pymodbus_client = types.ModuleType("pymodbus.client")
pymodbus_client.ModbusSerialClient = object
pymodbus.client = pymodbus_client
sys.modules.setdefault("pymodbus", pymodbus)
sys.modules.setdefault("pymodbus.client", pymodbus_client)

from src.core.errors import ValidationError
from src.core.models import CommandResult, DeviceName, ProgramDefinition, ResultCode
from src.engine.actions import PeripheralAction
from src.engine.checkpoint_store import CheckpointStore
from src.engine.experiment_engine import ExperimentEngine
from src.engine.instruction_parser import parse_instruction_line
from src.engine.run_plan import as_run_context, build_run_plan
from src.supervisor.supervisor import Supervisor
from src.transport.peripheral_protocol import validate_peripheral_reply


def program(run_count=2):
    return ProgramDefinition(
        name="disk-test",
        startup_instructions_path="settings/instructions_start.txt",
        run_instructions_path="settings/instructions_run.txt",
        Upos_values=list(range(run_count)),
        PEO_time_values=[1.0],
        KOH_targets=[0.1],
        total_ml=20.0,
    )


def context(run_index=1):
    definition = program(max(run_index, 1))
    runs = build_run_plan(definition)
    return as_run_context(definition, runs[run_index - 1], len(runs))


class ParserTests(unittest.TestCase):
    def test_supported_disk_commands_are_peripheral_actions(self):
        for command in ("DISK POSITION 0", "DISK POSITION 15", "DISK POSITION NEXT", "DISK STATUS"):
            with self.subTest(command=command):
                action = parse_instruction_line(command)
                self.assertIsInstance(action, PeripheralAction)
                self.assertEqual(action.command, command)
                self.assertEqual(action.timeout_s, 10.0)

    def test_invalid_disk_commands_are_rejected(self):
        for command in ("DISK POSITION -1", "DISK POSITION 16", "DISK POSITION abc", "DISK NEXT", "DISK"):
            with self.subTest(command=command), self.assertRaises(ValidationError):
                parse_instruction_line(command)


class ReplyValidationTests(unittest.TestCase):
    def assert_valid(self, command, reply):
        self.assertTrue(validate_peripheral_reply(command, reply).ok)

    def assert_invalid(self, command, reply):
        self.assertFalse(validate_peripheral_reply(command, reply).ok)

    def test_absolute_reply_must_match_exact_position(self):
        self.assert_valid("DISK POSITION 5", "OK DISK POSITION 5")
        for reply in ("OK", "OK DISK POSITION 4", "OK DISK POSITION 5 EXTRA", "OK CUT"):
            with self.subTest(reply=reply):
                self.assert_invalid("DISK POSITION 5", reply)

    def test_next_and_status_reply_shapes(self):
        self.assert_valid("DISK POSITION NEXT", "OK DISK POSITION NEXT 6")
        self.assert_invalid("DISK POSITION NEXT", "OK DISK POSITION NEXT 16")
        self.assert_valid("DISK STATUS", "OK DISK STATUS POSITION UNKNOWN BUSY 0")
        self.assert_valid("DISK STATUS", "OK DISK STATUS POSITION 15 BUSY 1")
        self.assert_invalid("DISK STATUS", "OK DISK STATUS POSITION 16 BUSY 0")

    def test_disk_error_is_device_process_failure(self):
        result = validate_peripheral_reply("DISK POSITION NEXT", "ERR DISK NOT_INITIALIZED")
        self.assertFalse(result.ok)
        self.assertTrue(result.is_device_error)
        self.assertEqual(result.failure_class, "DEVICE_PROCESS")


class RunContextAndRecoveryTests(unittest.TestCase):
    def test_run_context_has_deterministic_absolute_position(self):
        definition = program(17)
        runs = build_run_plan(definition)
        self.assertEqual(runs[0].required_disk_position, 0)
        self.assertEqual(runs[15].required_disk_position, 15)
        self.assertEqual(runs[16].required_disk_position, 0)

    def test_next_is_bound_to_absolute_run_position(self):
        engine = ExperimentEngine.__new__(ExperimentEngine)
        action = PeripheralAction("DISK POSITION NEXT", 10.0)
        bound = engine._bind_actions_for_run([action], context(2))
        self.assertEqual(bound[0].command, "DISK POSITION 1")
        self.assertNotIn("NEXT", bound[0].command)

    def test_checkpoint_persists_required_absolute_position(self):
        ctx = context(2)
        with tempfile.TemporaryDirectory() as directory:
            store = CheckpointStore(directory)
            store.save_success(ctx, 0, 1, "PeripheralAction")
            checkpoint_path = Path(store.list_program_checkpoints(ctx.program_name)[0])
            data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
            self.assertEqual(data["params"]["required_disk_position"], 1)

    def test_reconnect_recovery_sends_absolute_never_next(self):
        sent = []

        class FakeDeviceManager:
            def send_peripheral_text(self, command, timeout_s):
                sent.append((command, timeout_s))
                return CommandResult(DeviceName.PERIPHERAL, command, ResultCode.OK)

        supervisor = Supervisor.__new__(Supervisor)
        supervisor.device_manager = FakeDeviceManager()
        supervisor._recover_disk_absolute(context(3))
        self.assertEqual(sent, [("DISK POSITION 2", 10.0)])
        self.assertNotIn("NEXT", sent[0][0])

    def test_startup_initializes_full_program_at_zero(self):
        startup = Path("settings/instructions_start.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(startup.count("DISK POSITION 0"), 1)


if __name__ == "__main__":
    unittest.main()
