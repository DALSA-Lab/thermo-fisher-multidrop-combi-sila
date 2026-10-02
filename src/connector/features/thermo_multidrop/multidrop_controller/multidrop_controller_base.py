import abc
import typing

from unitelabs.cdk import sila

from connector.io.errors import MultidropException


class MultidropControllerBase(sila.Feature, metaclass=abc.ABCMeta):
    """
    This Feature provides control over the Multidrop Reagent Dispenser. This feature directly exposes the underlying
    hardware interface.
    """

    def __init__(self):
        super().__init__(
            originator="io.unitelabs",
            category="dispenser",
            version="0.1",
            maturity_level="Draft",
        )

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def dispense_plate(self) -> None:
        """
        Dispense the volume set by the 'set volume' command to the entire plate. Primes 10 μl into the priming vessel
        before dispensing.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def empty_pump(self) -> None:
        """
        Empty the pump. A volume of 880 μl is pumped backwards.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def dispense_using_start(self) -> None:
        """
        Dispense the plate using parameters from the plate switch and the volume/columns thumbwheels. This command has
        the same effect as pressing the start key. This command has been added to version 1.7.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def dispense_next_n_columns(self, n: int) -> None:
        """
        Dispense the given number of columns starting from the current column. If the column count is not given, one
        column is dispensed. The dispensing volume is set by the 'set volume' command. After the command is completed,
        the dispensing tips remain at the last column dispensed. If this command is received when the plate is in the
        home position, dispensing starts from column 1. ER3 is reported if more columns are requested than left over
        from the current column to the last column of the plate.
        .. parameter:: The number of columns to dispense next. The number of columns n must be in the range of the
        number of columns left on the plate.
        """

    @abc.abstractmethod
    @sila.UnobservableProperty(errors=[MultidropException])
    async def firmware_version(self) -> str:
        """
        The internal software version of the instrument.
        """

    @abc.abstractmethod
    @sila.UnobservableProperty(errors=[MultidropException])
    async def device_type(self) -> str:
        """
        The device type. The default on startup can be set with the environmental variable DEVICE. The device type is
        overwritten if another device type is found via the version command during initialization.
        """

    @abc.abstractmethod
    @sila.UnobservableProperty(errors=[MultidropException])
    async def plate_type(self) -> str:
        """
        The set plate type. The default on startup can be set with the environmental variable PLATE_TYPE.
        0: 96-well plate
        1: 384-well plate
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def move_plate_out(self) -> None:
        """
        Drive the plate out to the priming position.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def prime_pump(
        self,
        volume: typing.Annotated[
            int,
            sila.constraints.MinimalInclusive(value=5),
            sila.constraints.MaximalInclusive(value=1000),
            sila.constraints.Unit(
                label="uL",
                components=[sila.constraints.UnitComponent(unit=sila.constraints.SIUnit.METER, exponent=3)],
                factor=1000000000,
            ),
        ],
    ) -> None:
        """
        Prime the given volume. For a 96-well plate the volume must be in the range of 5 to 1000 μl. For a 384-well
        plate the range is 5 to 100 μl. The volume must be dispensed in 5 μl increments. If the volume is not given,
        200 μl is primed. If the plate is not in the home position when the command is received, it is first driven
        into home position.
        .. parameter:: The volume to prime in μl. Must be passed in 5 μl increments and may not exceed 1000 μl for
        96-well plate and 100 μl for a 384-well-plate.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def reset(self) -> None:
        """
        Reset the instrument. There is no response to this command.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def move_plate_column_to_dispensing_tips(
        self,
        column: typing.Annotated[
            int, sila.constraints.MinimalInclusive(value=1), sila.constraints.MaximalInclusive(value=24)
        ],
    ) -> None:
        """
        Drive the requested column under the dispensing tips. Valid columns are 1 to 12 for a 96-well plate and 1 to 24
        for a 384-well plate. If the column is not given, the steps are one column forward or the plate returns to home
        position after the last column.
        .. parameter:: The plate column to move under the dispensing tip. Must be in the range of available columns for
        the selected plate type.
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def set_plate_type(
        self,
        plate_type: typing.Annotated[
            int, sila.constraints.MinimalInclusive(value=0), sila.constraints.MaximalInclusive(value=1)
        ],
    ) -> None:
        """
        Set the plate type assumed for all other commands except the ‘G’ command. At startup the default type is read
        from the plate switch.
            t = 0 96-well plate
            t = 1 384-well plate
        This command has been added to version 1.7.
        .. parameter:: The plate type may be either a 96-well plate (0) or a 384-well plate (1).
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def set_volume(
        self,
        volume: typing.Annotated[
            int,
            sila.constraints.MinimalInclusive(value=5),
            sila.constraints.MaximalInclusive(value=1000),
            sila.constraints.Unit(
                label="uL",
                components=[sila.constraints.UnitComponent(unit=sila.constraints.SIUnit.METER, exponent=3)],
                factor=1000000000,
            ),
        ],
    ) -> None:
        """
        Sets the volume for dispensing. For a 96-well plate the volume must be in the range of 5 to 1000 μl. For a
        384-well plate the range is 5 to 140 μl. The volume must be dispensed in 5 μl increments.
        .. parameter:: The volume must be set in 5 μl increments and may not exceed the respective limits for 96-well
        plates (1000 μl) and 384-well-plates (140 μl).
        """

    @abc.abstractmethod
    @sila.UnobservableCommand(errors=[MultidropException])
    async def shake(
        self,
        duration: typing.Annotated[
            int,
            sila.constraints.MinimalInclusive(value=1),
            sila.constraints.MaximalInclusive(value=60),
            sila.constraints.Unit(
                label="s",
                components=[sila.constraints.UnitComponent(unit=sila.constraints.SIUnit.SECOND, exponent=1)],
                factor=1,
            ),
        ],
    ) -> None:
        """
        Shake the plate the desired amount of time. The time is seconds and may range from 1 to 60.
        .. parameter:: The duration to shake the plate in seconds. Must be in the range from 1 to 60 s.
        """
