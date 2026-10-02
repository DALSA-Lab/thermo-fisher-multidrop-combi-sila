import logging
import typing
from typing import Literal, Optional

from unitelabs.cdk import Config, Connector, create_logger

from .io.multidrop_protocol import (
    MultidropRS232Protocol,
    MultidropUSBProtocol,
    DeviceType,
    PlateType
)
from .io.multidrop_protocol import MultidropBaseProtocol

from .multidrop_controller import MultidropController

DEFAULT_USB_VID = 0x0AB6
DEFAULT_USB_PID = 0x0344
DEFAULT_USB_ENDPOINT_OUT = 0x01
DEFAULT_USB_ENDPOINT_IN = 0x81
DEFAULT_USB_INTERFACE_NUM = 0
DEFAULT_USB_CONFIGURATION_NUM = 1


class DeviceConfig(Config):
    """Configuration for the Multidrop Connector, supporting Serial and USB."""
    connection_type: Literal["serial", "usb"] = "serial"

    serial_port: Optional[str] = "COM1"

    usb_vid: Optional[int] = DEFAULT_USB_VID
    usb_pid: Optional[int] = DEFAULT_USB_PID
    usb_endpoint_out: Optional[int] = DEFAULT_USB_ENDPOINT_OUT
    usb_endpoint_in: Optional[int] = DEFAULT_USB_ENDPOINT_IN
    usb_interface_num: Optional[int] = DEFAULT_USB_INTERFACE_NUM
    usb_configuration_num: Optional[int] = DEFAULT_USB_CONFIGURATION_NUM

    simulation_mode: bool = False
    device: Literal["Multidrop_Combi", "Multidrop_Micro", "Multidrop_DW", "Multidrop_384"] = "Multidrop_384"
    plate_type: Literal["WELL_PLATE_96", "WELL_PLATE_384"] = "WELL_PLATE_96"


async def create_app() -> typing.AsyncGenerator[Connector, None]:
    """Creates the connector application."""
    config = DeviceConfig()
    protocol: MultidropBaseProtocol

    if config.environment == "production":
        logger = create_logger("Multidrop", logging.INFO)
    else:
        logger = create_logger("Multidrop", logging.DEBUG)

    sila_server_name = f"{config.device.replace('_',' ')} ({config.connection_type.upper()})"
    sila_server_description = f"{config.device.replace('_',' ')} is a reagent dispenser. Configured for {config.connection_type} connection."

    app = Connector(
        {
            "sila_server": {
                "name": sila_server_name,
                "type": "Dispenser",
                "description": sila_server_description,
                "version": "0.0.3",
                "vendor_url": "https://unitelabs.io/",
            }
        }
    )

    if config.simulation_mode:
        logger.info("Starting in simulation mode.")
        raise NotImplementedError("Simulation mode is selected, but no simulation protocol is implemented.")
    else:
        logger.info(f"Attempting to start the connector in real mode with {config.connection_type} connection.")
        if config.connection_type == "serial":
            if not config.serial_port:
                logger.error("Serial connection selected, but SERIAL_PORT is not configured.")
                raise ValueError("SERIAL_PORT must be configured for 'serial' connection type.")
            logger.info(f"Initializing RS232 protocol on port: {config.serial_port}")
            protocol = MultidropRS232Protocol(
                port=config.serial_port,
                plate_type_str=config.plate_type,
                device_type_str=config.device
            )
        elif config.connection_type == "usb":
            if not all([config.usb_vid, config.usb_pid, config.usb_endpoint_in, config.usb_endpoint_out,
                        config.usb_interface_num is not None, config.usb_configuration_num is not None]):
                logger.error("USB connection selected, but one or more USB parameters are missing.")
                raise ValueError("USB_VID, USB_PID, Endpoints, Interface, and Configuration must be set for 'usb' type.")
            logger.info(f"Initializing USB protocol for VID={config.usb_vid:#06x}, PID={config.usb_pid:#06x}")
            protocol = MultidropUSBProtocol(
                vid=config.usb_vid,
                pid=config.usb_pid,
                endpoint_out=config.usb_endpoint_out,
                endpoint_in=config.usb_endpoint_in,
                interface_num=config.usb_interface_num,
                configuration_num=config.usb_configuration_num,
                plate_type_str=config.plate_type,
                device_type_str=config.device
            )
        else:
            logger.error(f"Unsupported connection_type: {config.connection_type}")
            raise ValueError(f"Unsupported connection_type: {config.connection_type}")

        await protocol.open()
        logger.info(f"{config.connection_type.upper()} Protocol opened.")

    multidrop_service = MultidropController(protocol=protocol, publisher=None)
    app.register(multidrop_service)
    logger.info(f"MultidropController registered with {config.connection_type} protocol.")

    try:
        yield app
    finally:
        logger.info("Shutting down connector, closing protocol connection.")
        if 'protocol' in locals() and hasattr(protocol, 'close') and callable(protocol.close):
            await protocol.close()
            logger.info("Protocol connection closed.")
        else:
            logger.info("Protocol was not initialized or does not have a close method.")