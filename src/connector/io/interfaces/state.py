import enum


class DeviceState(enum.Enum):
    """The state of the device as kept by the connector. The state is not synced with the device."""

    OFF = enum.auto()
    READY = enum.auto()
    BUSY = enum.auto()
