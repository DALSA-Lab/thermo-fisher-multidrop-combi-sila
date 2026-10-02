import typing
from unitelabs.cdk import sila

from .features.thermo_multidrop.multidrop_controller import MultidropControllerBase
from .io.multidrop_protocol import MultidropBaseProtocol, PlateType


class MultidropController(MultidropControllerBase):
    """
    This Feature provides control over the Multidrop Reagent Dispenser. This feature directly exposes the underlying
    hardware interface.
    """

    def __init__(self, protocol: MultidropBaseProtocol, publisher: None):
        super().__init__()
        self.protocol: MultidropBaseProtocol = protocol
        self.publisher = publisher

    async def dispense_plate(self) -> None:
        """
        Dispense the volume set by the 'set volume' command to the entire plate. Primes 10 μl into the priming vessel
        before dispensing.
        """
        await self.protocol.dispense_plate()
        return None

    async def empty_pump(self) -> None:
        """
        Empty the pump. A volume of 880 μl is pumped backwards.
        """
        await self.protocol.empty()
        return None

    async def dispense_using_start(self) -> None:
        """
        Dispense the plate using parameters from the plate switch and the volume/columns thumbwheels. This command has
        the same effect as pressing the start key. This command has been added to version 1.7.
        """
        await self.protocol.dispense_using_start()
        return None

    async def dispense_next_n_columns(self, n: int) -> None:
        """
        Dispense the given number of columns starting from the current column. If the column count is not given, one
        column is dispensed. The dispensing volume is set by the 'set volume' command. After the command is completed,
        the dispensing tips remain at the last column dispensed. If this command is received when the plate is in the
        home position, dispensing starts from column 1. ER3 is reported if more columns are requested than left over
        from the current column to the last column of the plate.
        """
        await self.protocol.dispense_next_n_columns(n=n)
        return None

    async def firmware_version(self) -> str:
        """
        The internal software version of the instrument.
        """
        return await self.protocol.get_firmware_version()

    async def device_type(self) -> typing.Optional[str]:
        """
        The device model. Returns the name of the enum member (e.g., "MULTIDROP_COMBI") or None.
        """
        dt_enum = await self.protocol.get_device_type()
        return dt_enum.name if dt_enum else None

    async def plate_type(self) -> str:
        """
        The set plate type. Returns the name of the enum member (e.g., "WELL_PLATE_96").
        """
        pt_enum = await self.protocol.get_plate_type()
        return pt_enum.name

    async def move_plate_out(self) -> None:
        """
        Drive the plate out to the priming position.
        """
        await self.protocol.move_plate_out()
        return None

    async def prime_pump(self, volume: int) -> None:
        """
        Prime the given volume. For a 96-well plate the volume must be in the range of 5 to 1000 μl. For a 384-well
        plate the range is 5 to 100 μl. The volume must be dispensed in 5 μl increments. If the plate is not in the
        home position when the command is received, it is first driven
        into home position.
        """
        await self.protocol.prime_volume(volume=volume)
        return None

    async def reset(self) -> None:
        """
        Reset the instrument. There is no response to this command.
        """
        await self.protocol.reset()
        return None

    async def move_plate_column_to_dispensing_tips(self, column: int) -> None:
        """
        Drive the requested column under the dispensing tips. Valid columns are 1 to 12 for a 96-well plate and 1 to 24
        for a 384-well plate. If the column is not given, the steps are one column forward or the plate returns to home
        position after the last column.
        """
        await self.protocol.move_plate_column_to_dispensing_tips(column=column)
        return None

    async def set_plate_type(self, plate_type: int) -> None:
        """
        Set the plate type assumed for all other commands except the ‘G’ command. At startup the default type is read
        from the plate switch.
            0: 96-well plate
            1: 384-well plate
        This command has been added to version 1.7.
        """
        try:
            plate_type_enum = PlateType(plate_type)
        except ValueError:
            raise sila.errors.ValidationError(
                 parameter=str(self.fully_qualified_identifier) + "/Command/SetPlateType/Parameter/PlateType",
                 message=f"Invalid plate_type value: {plate_type}. Must be 0 or 1."
            )
        await self.protocol.set_plate_type(plate_type=plate_type_enum)
        return None

    async def set_volume(self, volume: int) -> None:
        """
        Sets the volume for dispensing. For a 96-well plate the volume must be in the range of 5 to 1000 μl. For a
        384-well plate the range is 5 to 140 μl. The volume must be dispensed in 5 μl increments.
        """
        current_plate_type = await self.protocol.get_plate_type()
        if current_plate_type == PlateType.WELL_PLATE_384 and volume > 140:
            raise sila.errors.ValidationError(
                parameter=str(self.fully_qualified_identifier) + "/Command/SetVolume/Parameter/Volume",
                message=f"Volume {volume}µL exceeds limit (140µL) for 384-well plate.",
            )
        await self.protocol.set_volume(volume=volume)
        return None

    async def shake(self, duration: int) -> None:
        """
        Shake the plate the desired amount of time. The time is seconds and may range from 1 to 60.
        """
        await self.protocol.shake(duration=duration)
        return None