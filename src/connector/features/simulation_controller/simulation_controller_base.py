import abc

from unitelabs.cdk import sila


class StartSimulationModeFailed(sila.DefinedExecutionError):
    """
    The server cannot change to Simulation Mode.

    This error can, e.g., be thrown, if a real-world process needs to be ended before switching to simulation mode.
    """

    def __init__(self, *args, description: str = "", **kwargs):
        super().__init__(
            *args,
            identifier="StartSimulationModeFailed",
            display_name="The start of Simulation Mode failed.",
            description=description,
            **kwargs,
        )


class StartRealModeFailed(sila.DefinedExecutionError):
    """
    The server cannot change to Real Mode.

    This error can, e.g., be thrown, if a device is not ready to change into Real Mode.
    """

    def __init__(self, *args, description: str = "", **kwargs):
        super().__init__(
            *args,
            identifier="StartRealModeFailed",
            display_name="The start of Real Mode failed.",
            description=description,
            **kwargs,
        )


class SimulationControllerBase(sila.Feature, metaclass=abc.ABCMeta):
    """
    This Feature provides control over the simulation behaviour of a SiLA Server.

    A SiLA Server can run in two modes:
    (a) Real Mode - with real activities, e.g. addressing or controlling real hardware,
        e.g. through serial/CANBus commands, writing to real databases, moving real objects etc.
    (b) Simulation Mode - where every command is only simulated and responses are just example returns.

    Note that certain commands and properties might not be affected by this feature if they
    do not interact with the real world.
    """

    _simulation_mode = False

    def __init__(self):
        super().__init__(
            originator="org.silastandard",
            category="core",
            version="1.0",
            maturity_level="Verified",
        )

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[StartSimulationModeFailed])
    def start_simulation_mode(self):
        """
        Sets the SiLA Server to run in Simulation Mode, i.e. all following commands are executed in simulation mode.

        The Simulation Mode can only be entered, if all hardware operations have been safely terminated
        or are in a controlled, safe state.

        The simulation mode can be stopped by issuing the 'Start Real Mode' command.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[StartRealModeFailed])
    def start_real_mode(self):
        """
        Sets the SiLA Server to run in real mode, i.e. all following commands are executed with real-world
        interactions, like serial port/CAN communication, motor actions etc.

        If the server is in Simulation Mode it can be interrupted at any time. A re-initialization of
        the hardware might be required. The Real Mode can be stopped by issuing the 'Start Simulation Mode' command.
        """

    @abc.abstractmethod
    @sila.UnobservableProperty()
    def simulation_mode(self) -> bool:
        """Indication whether SiLA Server is in Simulation Mode or not."""
