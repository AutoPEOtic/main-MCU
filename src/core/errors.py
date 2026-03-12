from __future__ import annotations


class PEOSystemError(Exception):
    """Base class for the new architecture."""


class ValidationError(PEOSystemError):
    """Configuration or instruction validation failed."""


class TransportError(PEOSystemError):
    """Serial / USB / Modbus transport failure."""


class ProtocolError(PEOSystemError):
    """Unexpected or invalid device reply."""


class DeviceProcessError(PEOSystemError):
    """Device is reachable, but the commanded process failed."""


class DeviceUnhealthyError(PEOSystemError):
    """Command rejected because the device is not currently healthy."""


class SupervisorStateError(PEOSystemError):
    """Illegal supervisor state transition."""


class StopRequested(PEOSystemError):
    """Controlled stop of active execution."""


class RestartProgramRequested(PEOSystemError):
    """Controlled restart of the full program."""


class RestartRunRequested(PEOSystemError):
    """Controlled restart of the current run."""