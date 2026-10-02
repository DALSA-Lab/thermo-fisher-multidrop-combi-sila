from unitelabs.cdk import sila


class MultidropException(sila.DefinedExecutionError):
    """
    Raised when a command or attribute is invalid for the Multidrop device. Specific to errors raised by the device
    """


errors = {
    "ER1": "Internal firmware error. Contact service.",
    "ER2": "The instrument did not recognize the command it received. Contact the SiLAConverter vendor.",
    "ER3": "Unrecognized command or invalid command argument.",
    # Not combi error: "ER4": "The pump is not primed.",
    # Not combi error: "ER5": "The priming vessel is not inserted into its slot.",
    # Not combi error: "ER6": "Hardware error.",
    # Not combi error: "ER7": "The pump has lost steps. The next priming, manual or in conjunction with the “D”
    # command, will readjust the rotor home position. ",
    "ER4": "Pump position error. Reduce dispensing speed or, if using the small tube cassette, use standard tube "
    "cassette instead. If the problem persists even with normal viscosity fluids, contact service.",
    "ER5": "Plate X position error. If this error is reported repeatedly, contact service.",
    "ER6": "Plate Y position error. If this error is reported repeatedly, contact service.",
    "ER7": "Z position error. If this error is reported repeatedly, contact service.",
    "ER8": "Selector position error. If this error is reported repeatedly, contact service.",
    "ER9": "Attempt to reset the serial number. Do not try to reprogram the serial number.",
    "ER10": "Nonvolatile parameters lost. Contact service.",
    "ER11": "No more memory for storing user data. Release some user data no longer needed.",
    "ER12": "A previous command is executing in the background. Do not use commands interfering with the ongoing "
    "operation without first stopping the operation.",
    "ER13": "X and Z positions conflict. Contact service.",
    "ER14": "Cannot dispense when pump not primed. Prime the pump before dispensing.",
    "ER15": "Missing prime vessel. Insert the priming vessel.",
    "ER16": "Rotor shield not in place. Slide the rotor cover in place.",
    "ER17": "Dispense volume for all wells is 0. Select a nonezero volume for at least one plate well.",
    "ER18": "Cannot dispense because the plate type is invalid (bad plate index). Use a valid plate index.",
    "ER19": "Cannot dispense because the plate has not beend defined. Define the plate.",
    "ER20": "Invalid rows in plate definition. Check the WPL or PLA command.",
    "ER21": "Invalid columns in plate definition. Check the WPL or PLA command.",
    "ER22": "Plate height is invalid. Check the WPL or PLA command.",
    "ER23": "Plate well volume is invalid (too small or too big). Check the WPL or PLA command.",
    "ER24": "The cassette type is invalid (bad cassette index). Use a valid cassette index.",
    "ER25": "Cassette not defined. Define the cassette.",
    "ER26": "Volume increment defined for cassette is invalid.",
    "ER27": "Maximum volume defined for the cassette is invalid.",
    "ER28": "Minimum volume defined for the cassette is invalid.",
    "ER29": "Minimum or maximum pump speed defined for the cassette is invalid.",
    "ER30": "Pump rotor offset in the cassete definition is invalid.",
    "ER31": "description",
    "ER32": "Dispensing volume is not within limits allowed for the cassette. Correct the volume or use a different "
    "cassette.",
    "ER33": "Invalid selector channel. Correct the selector channel number.",
    "ER34": "Invalid dispensing speed. Use a valid value.",
    "ER35": "Invalid dispensing height. Correct the dispensing heigth.",
    "ER36": "Invalid predispense volume. Change the predispense volume of the protocol.",
    "ER37": "Invalid dispensing order of the plate. Use dispensing order 0 or 1.",
    "ER38": "Invalid X or Y dispensing offset. Fix the offsets. Note that the limits depend on the used plate type.",
    "ER39": "RFID option not present. Purchase the RFID option for the instrument.",
    "ER40": "RFID tag not present. Insert a cassette type containing a RFID tag.",
    "ER41": "RFID tag data checksum is incorrect. If the cassette has never been calibrated, calibrate it. Else "
    "discard the cassette.",
    "ER42": "Selector valve not installed. Do not try to operate the selector unless it is installed.",
    "ER43": "Wrong cassette type. Use a cassette type matching the cassette type of the current protocol.",
    "ER44": "Protocol, plate or liquid profile may not be modified or deleted because it is currenty used.",
    "ER45": "Cannot modify or delete protocol or a plate because it is read only.",
    "ER46": "Pressure failure. Adjusting the pressure to the required value failed. Check that the reagent bottle cap "
    "is properly closed and that all tubes are tightly fitted.",
    "ER47": "Hash collision. Two different commands have the same hash value. This error is not fatal, but should "
    "never be reported.",
    "ER48": "Too high pressure measurement electronics offset. Contact service.",
    "ER49": "Pressure is off. This error is reported in return to dispense or prime commands if the pressure is off.",
    "ER": " - unknown error number. Take a look to the manual or contact service.",
}
