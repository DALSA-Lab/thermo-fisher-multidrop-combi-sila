import asyncio
import logging
import typing
import enum
import platform
import usb.core
import usb.util
import time
from datetime import datetime

from unitelabs.bus import Protocol, create_serial_connection
from unitelabs.bus.commands.serial_command import SerialCommand
from unitelabs.bus.commands.command import Command

from .interfaces import DeviceState
from .errors import errors, MultidropException


# --- Constants ---
SERIAL_INPUT_TIMEOUT = 5.0
SERIAL_PRIME_TIMEOUT = 90.0
SERIAL_DISPENSE_TIMEOUT = SERIAL_PRIME_TIMEOUT + 20.0
SERIAL_EMPTY_TIMEOUT = 120.0

USB_DEFAULT_TIMEOUT_MS = 5 * 1000
USB_PRIME_TIMEOUT_MS = 10 * 1000
USB_DISPENSE_TIMEOUT_MS = 20 * 1000
USB_EMPTY_TIMEOUT_MS = 10 * 1000
USB_READ_CHUNK_TIMEOUT_MS = 200
USB_RESPONSE_SIZE_HINT = 128

# --- Enums (Shared) ---
class DeviceType(enum.Enum):
    MULTIDROP_COMBI = enum.auto()
    MULTIDROP_MICRO = enum.auto()
    MULTIDROP_384 = enum.auto()
    MULTIDROP_DW = enum.auto()
    UNKNOWN = enum.auto()

class PlateType(enum.Enum):
    WELL_PLATE_96 = 0
    WELL_PLATE_384 = 1

# --- Base Protocol (Interface Definition) ---
class MultidropBaseProtocol(Protocol):
    device_type: DeviceType = DeviceType.UNKNOWN
    plate_type: PlateType

    def __init__(self, plate_type_str: str, device_type_str: typing.Optional[str]):
        self._loop = asyncio.get_event_loop_policy().get_event_loop()
        try:
            normalized_plate_str = plate_type_str.upper().replace("-", "_")
            if not normalized_plate_str.startswith("WELL_PLATE_"):
                normalized_plate_str = "WELL_PLATE_" + normalized_plate_str
            self.plate_type = PlateType[normalized_plate_str]
        except KeyError:
            logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}").error(
                f"Invalid plate_type_str: '{plate_type_str}'. Defaulting to WELL_PLATE_96."
            )
            self.plate_type = PlateType.WELL_PLATE_96
        
        self._initialize_device_type_from_string(device_type_str)

    def _initialize_device_type_from_string(self, device_type_str: typing.Optional[str]):
        logger_instance = getattr(self, 'logger', logging.getLogger(f"{self.__class__.__module__}.{self.__class__.__name__}"))
        if device_type_str:
            try:
                processed_str = device_type_str.upper().replace(" ", "_").replace("-", "_")
                if "MULTIDROP" not in processed_str:
                    enum_key = "MULTIDROP_" + processed_str
                else:
                    enum_key = processed_str
                self.device_type = DeviceType[enum_key]
                logger_instance.info(f"Device type configured from string as: {self.device_type.name}")
            except KeyError:
                logger_instance.warning(f"Could not map device_type_str '{device_type_str}' to DeviceType enum. Will attempt hardware detection.")
                self.device_type = DeviceType.UNKNOWN
        else:
            self.device_type = DeviceType.UNKNOWN
            logger_instance.info("No device_type_str provided. Will attempt hardware detection if connection is made.")

    @property
    def logger(self) -> logging.Logger:
        return logging.getLogger(f"{self.__class__.__module__.split('.')[0]}.{self.__class__.__name__}")

    async def update_device_type_from_hardware(self) -> None:
        if not self.is_connected:
            self.logger.warning("Cannot update device type from hardware: not connected.")
            return
        version_str = ""
        try:
            version_str = await self.get_firmware_version()
        except Exception as e:
            self.logger.error(f"Failed to retrieve firmware version during device type update: {e}")
            self.device_type = DeviceType.UNKNOWN
            return

        if not version_str:
            self.logger.error("Empty firmware version received. Cannot determine device type.")
            self.device_type = DeviceType.UNKNOWN
            return

        upper_version_str = version_str.upper()
        if "MULTIDROPCOMBI" in upper_version_str:
            self.device_type = DeviceType.MULTIDROP_COMBI
        elif "MDMICRO V1.1" in upper_version_str:
            self.device_type = DeviceType.MULTIDROP_MICRO
        elif "MDROP384" in upper_version_str:
            self.device_type = DeviceType.MULTIDROP_384
        elif "MDROPDW" in upper_version_str:
            self.device_type = DeviceType.MULTIDROP_DW
        else:
            self.logger.warning(f"Could not determine device type from version string: {version_str!r}")
            self.device_type = DeviceType.UNKNOWN
        self.logger.info(f"Detected/Updated device type from hardware: {self.device_type.name}")

    async def get_device_type(self) -> DeviceType:
        if self.device_type == DeviceType.UNKNOWN and self.is_connected:
            try:
                await self.update_device_type_from_hardware()
            except Exception as e:
                self.logger.error(f"Could not update device type from hardware during get_device_type: {e}")
        return self.device_type

    async def get_plate_type(self) -> PlateType:
        return self.plate_type

    async def dispense_plate(self) -> str: raise NotImplementedError
    async def empty(self) -> str: raise NotImplementedError
    async def dispense_using_start(self) -> str: raise NotImplementedError
    async def dispense_next_n_columns(self, n: typing.Optional[int]) -> str: raise NotImplementedError
    async def get_firmware_version(self) -> str: raise NotImplementedError
    async def move_plate_out(self) -> str: raise NotImplementedError
    async def prime_volume(self, volume: typing.Optional[int]) -> str: raise NotImplementedError
    async def reset(self) -> None: raise NotImplementedError
    async def move_plate_column_to_dispensing_tips(self, column: typing.Optional[int]) -> str: raise NotImplementedError
    async def set_plate_type(self, plate_type_enum_val: PlateType) -> str: raise NotImplementedError
    async def set_volume(self, volume: int) -> str: raise NotImplementedError
    async def shake(self, duration: int) -> str: raise NotImplementedError

# --- RS232 Specific Implementation ---
class MultidropSerialCommand(SerialCommand):
    def __init__(self, command_str: str, timeout: float, is_void: bool = False):
        super().__init__(
            command_str,
            write_terminator=b"\r\n",
            read_terminator=b"\r\n",
            timeout=timeout,
            is_void=is_void
        )

    def deserialize(self, response: typing.Optional[bytes]) -> str:
        message = super().deserialize(response=response)
        if message.startswith("ER"):
            error_code = message.split(' ')[0]
            error_description = errors.get(error_code, errors.get("ER", "Unknown Multidrop Error"))
            logger_to_use = getattr(self.receiver, 'logger', logging.getLogger(f"{self.__class__.__module__}.FallBack"))
            logger_to_use.error(f"Device error for RS232 command '{self.message}': {error_description} (Raw: {message})")
            raise MultidropException(description=error_description)
        return message

class MultidropRS232Protocol(MultidropBaseProtocol):
    def __init__(self, port: str, plate_type_str: str, device_type_str: typing.Optional[str]):
        Protocol.__init__(self,
            create_serial_connection,
            port=port,
            baudrate=9600
        )
        MultidropBaseProtocol.__init__(self, plate_type_str=plate_type_str, device_type_str=device_type_str)
        self.logger.info(f"RS232 Protocol initialized for port {port}")

    async def open(self) -> None:
        await Protocol.open(self)
        try:
            if self.device_type == DeviceType.UNKNOWN:
                 await self.update_device_type_from_hardware()
            if self.device_type == DeviceType.MULTIDROP_COMBI:
                await self.execute(MultidropSerialCommand("EAK", SERIAL_INPUT_TIMEOUT))
                tim_command = datetime.now().strftime("TIM %d.%m.%Y %H:%M:%S")
                await self.execute(MultidropSerialCommand(tim_command, SERIAL_INPUT_TIMEOUT))
                await self.execute(MultidropSerialCommand("SRE 2", SERIAL_INPUT_TIMEOUT))
            await self.set_plate_type(self.plate_type)
        except TimeoutError as e:
            self.logger.error(f"Timeout during RS232 initial open sequence: {e}")
            await Protocol.close(self)
            raise
        except Exception as e:
            self.logger.error(f"Error during RS232 initial open sequence: {e}")
            await Protocol.close(self)
            raise

    async def close(self) -> None:
        if self.device_type == DeviceType.MULTIDROP_COMBI and self.is_connected:
            try:
                await self.execute(MultidropSerialCommand("EAK", 1.0, is_void=True))
                await self.execute(MultidropSerialCommand("QIT", 1.0, is_void=True))
            except Exception as e_cmd: self.logger.warning(f"Issue sending EAK/QIT on RS232 close: {e_cmd}")
        await Protocol.close(self)

    async def dispense_plate(self) -> str: return await self.execute(MultidropSerialCommand("D", SERIAL_DISPENSE_TIMEOUT))
    async def empty(self) -> str: return await self.execute(MultidropSerialCommand("E", SERIAL_EMPTY_TIMEOUT))
    async def dispense_using_start(self) -> str: return await self.execute(MultidropSerialCommand("G", SERIAL_INPUT_TIMEOUT))
    async def dispense_next_n_columns(self, n: typing.Optional[int]) -> str:
        cmd = "M" if n is None else f"M{n}"; return await self.execute(MultidropSerialCommand(cmd, SERIAL_INPUT_TIMEOUT))
    async def get_firmware_version(self) -> str: return await self.execute(MultidropSerialCommand("VER", SERIAL_INPUT_TIMEOUT))
    async def move_plate_out(self) -> str: return await self.execute(MultidropSerialCommand("O", SERIAL_INPUT_TIMEOUT))
    
    async def prime_volume(self, volume: typing.Optional[int]) -> str:
        if volume is not None and volume % 5 != 0: 
            raise MultidropException(description="Volume must be multiple of 5 µL.")
        current_dev_type = await self.get_device_type()
        cmd_str: str
        if current_dev_type == DeviceType.MULTIDROP_COMBI:
            base_cmd = "PRI"; cmd_arg_str = str(volume) if volume is not None else "200" 
            cmd_str = f"{base_cmd} {cmd_arg_str}"
        else:
            base_cmd = "P"
            if volume is not None: cmd_str = f"{base_cmd}{volume}"
            else: cmd_str = base_cmd
        return await self.execute(MultidropSerialCommand(cmd_str, SERIAL_PRIME_TIMEOUT))

    async def reset(self) -> None:
        try: await self.execute(MultidropSerialCommand("Q", 1.0, is_void=True))
        except Exception: pass
        self.logger.info("RS232 Reset 'Q' command sent. Device state may be reset.")
        await asyncio.sleep(5)
        try:
            if self.device_type == DeviceType.UNKNOWN:
                await self.update_device_type_from_hardware()
            if self.device_type == DeviceType.MULTIDROP_COMBI:
                await self.execute(MultidropSerialCommand("EAK", SERIAL_INPUT_TIMEOUT))
                tim_command = datetime.now().strftime("TIM %d.%m.%Y %H:%M:%S")
                await self.execute(MultidropSerialCommand(tim_command, SERIAL_INPUT_TIMEOUT))
                await self.execute(MultidropSerialCommand("SRE 2", SERIAL_INPUT_TIMEOUT))
            await self.set_plate_type(self.plate_type)
        except Exception as e_reinit:
            self.logger.error(f"Failed to re-initialize RS232 state post-reset: {e_reinit}")

    async def move_plate_column_to_dispensing_tips(self, column: typing.Optional[int]) -> str:
        cmd = "S" if column is None else f"S{column}"; return await self.execute(MultidropSerialCommand(cmd, SERIAL_INPUT_TIMEOUT))
    
    async def set_plate_type(self, plate_type_enum_val: PlateType) -> str:
        response = await self.execute(MultidropSerialCommand(f"T{plate_type_enum_val.value}", SERIAL_INPUT_TIMEOUT))
        current_dev_type = await self.get_device_type()
        is_combi_like = current_dev_type in [DeviceType.MULTIDROP_COMBI, DeviceType.UNKNOWN]
        if "OK" in response.upper() or (is_combi_like and "T END 0" in response.upper()):
             self.plate_type = plate_type_enum_val
             self.logger.info(f"Plate type set to {plate_type_enum_val.name}")
        else:
            self.logger.warning(f"Unexpected response when setting plate type via RS232: {response!r}")
        return response

    async def set_volume(self, volume: int) -> str:
        if volume % 5 != 0: raise MultidropException(description="Volume must be multiple of 5 µL.")
        return await self.execute(MultidropSerialCommand(f"V{volume}", SERIAL_INPUT_TIMEOUT))
    async def shake(self, duration: int) -> str:
        if not (1 <= duration <= 60): raise MultidropException(description="Shake duration must be between 1 and 60 seconds.")
        return await self.execute(MultidropSerialCommand(f"Z{duration}", float(duration + 5)))

# --- USB Specific Implementation ---
class MultidropUSBCommand(Command[str, str]):
    def __init__(self, command_str: str, timeout_ms: int,
                 device_mode_for_parsing: DeviceType, 
                 logger: logging.Logger,
                 is_void: bool = False):
        super().__init__(message=command_str, timeout=float(timeout_ms / 1000.0), is_void=is_void)
        self.device_mode_for_parsing = device_mode_for_parsing
        self.command_text = command_str
        self.logger = logger

    def _serialize(self, message: str) -> bytes:
        return (message.strip() + "\r\n").encode('ascii')

    def _deserialize(self, response_bytes: typing.Optional[bytes]) -> str:
        if self.is_void and not response_bytes: return "OK_VOID"
        if not response_bytes: return ""

        raw_decoded_str = response_bytes.decode('ascii', errors='replace')
        lines = raw_decoded_str.strip().splitlines()
        primary_response_parts, error_details_list = [], []

        for line_content in lines:
            line = line_content.strip();            
            if not line: continue
            if line.startswith("ER"):
                err_code = line.split(' ')[0]
                error_description = errors.get(err_code, errors.get("ER", f"Unknown Multidrop Error: {err_code}"))
                error_details_list.append(f"{err_code}: {error_description}")
            elif not line.startswith("SRE"):
                primary_response_parts.append(line)
        
        clean_primary_response = "\n".join(primary_response_parts).strip()

        if error_details_list:
            full_error_message = "; ".join(error_details_list)
            self.logger.error(f"Device error content for USB command '{self.command_text}': {full_error_message} (Raw: {raw_decoded_str!r})")
            raise MultidropException(description=full_error_message)
        return clean_primary_response

class MultidropUSBProtocol(MultidropBaseProtocol):
    _VID: int; _PID: int; _EP_OUT: int; _EP_IN: int
    _INTERFACE_NUM: int; _CONFIGURATION_NUM: int
    _dev: typing.Optional[usb.core.Device] = None
    _connected_usb_transport: bool = False
    _closing: bool = False

    def __init__(self,
                 vid: int, pid: int,
                 endpoint_out: int, endpoint_in: int,
                 plate_type_str: str, device_type_str: typing.Optional[str],
                 interface_num: int = 0, configuration_num: int = 1):
        MultidropBaseProtocol.__init__(self, plate_type_str=plate_type_str, device_type_str=device_type_str)
        self._VID = vid; self._PID = pid
        self._EP_OUT = endpoint_out; self._EP_IN = endpoint_in
        self._INTERFACE_NUM = interface_num; self._CONFIGURATION_NUM = configuration_num
        self.logger.info(f"USB Protocol (pyusb) pending for VID={vid:#06x}, PID={pid:#06x}")

    @property
    def is_connected(self) -> bool:
        return self._connected_usb_transport and self._dev is not None

    def _usb_connection_made(self):
        self._connected_usb_transport = True; self._closing = False
        self.logger.info(f"{self.__class__.__name__} USB transport connection established (pyusb).")

    def _usb_connection_lost(self, exc: typing.Optional[Exception]):
        self._connected_usb_transport = False
        if exc: self.logger.error(f"{self.__class__.__name__} USB transport connection lost (pyusb): {exc}")
        else: self.logger.info(f"{self.__class__.__name__} USB transport connection cleanly closed (pyusb).")

    async def open(self) -> None:
        if self.is_connected:
            await self.close()
        self.logger.info(f"Opening USB device (pyusb): VID={self._VID:#06x}, PID={self._PID:#06x}")
        try:
            def find_device_sync(vid, pid): return usb.core.find(idVendor=vid, idProduct=pid)
            self._dev = await self._loop.run_in_executor(None, find_device_sync, self._VID, self._PID)
            if self._dev is None: raise MultidropException(description=f"Multidrop USB (VID:{self._VID:#06x}, PID:{self._PID:#06x}) not found.")
            if platform.system() in ["Linux", "Darwin"]:
                try:
                    if await self._loop.run_in_executor(None, self._dev.is_kernel_driver_active, self._INTERFACE_NUM):
                        await self._loop.run_in_executor(None, self._dev.detach_kernel_driver, self._INTERFACE_NUM)
                except Exception as e_detach: self.logger.warning(f"Kernel driver detach issue (might be okay): {e_detach}")
            try:
                await self._loop.run_in_executor(None, self._dev.set_configuration, self._CONFIGURATION_NUM)
            except usb.core.USBError as e_cfg:
                if hasattr(e_cfg, 'errno') and e_cfg.errno == 16 or "resource busy" in str(e_cfg).lower(): pass
                else: raise
            try:
                await self._loop.run_in_executor(None, usb.util.claim_interface, self._dev, self._INTERFACE_NUM)
            except usb.core.USBError as e_claim:
                if hasattr(e_claim, 'errno') and e_claim.errno == 16 or "resource busy" in str(e_claim).lower(): pass
                else: raise
            self._usb_connection_made()
            if self.device_type == DeviceType.UNKNOWN: await self.update_device_type_from_hardware()
            if self.device_type == DeviceType.MULTIDROP_COMBI:
                await self.execute(MultidropUSBCommand("EAK", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
                tim_str = datetime.now().strftime("TIM %d.%m.%Y %H:%M:%S")
                await self.execute(MultidropUSBCommand(tim_str, USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
                await self.execute(MultidropUSBCommand("SRE 2", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
            await self.set_plate_type(self.plate_type)
        except Exception as e:
            self.logger.error(f"Error during USB (pyusb) open: {e}")
            if self._dev:
                try: await self._loop.run_in_executor(None, usb.util.release_interface, self._dev, self._INTERFACE_NUM)
                except: pass
            self._dev = None
            self._usb_connection_lost(MultidropException(description=f"Failed to open USB (pyusb): {e}"))
            raise

    async def close(self) -> None:
        if self._closing: return
        self._closing = True
        try:
            if self.is_connected and self._dev:
                if self.device_type == DeviceType.MULTIDROP_COMBI:
                    try:
                        await self.execute(MultidropUSBCommand("EAK", 500, self.device_type, self.logger, is_void=True))
                        await self.execute(MultidropUSBCommand("QIT", 500, self.device_type, self.logger, is_void=True))
                    except Exception as e_cmd: self.logger.warning(f"Issue sending EAK/QIT on USB close: {e_cmd}")
                try:
                    await self._loop.run_in_executor(None, usb.util.release_interface, self._dev, self._INTERFACE_NUM)
                except Exception as e_close: self.logger.error(f"Error during USB close (release_interface): {e_close}")
                finally: self._dev = None; self._usb_connection_lost(None)
            elif self._connected_usb_transport: self._usb_connection_lost(None)
        finally: self._closing = False

    async def _perform_control_transfer_poll(self, timeout_ms=200) -> int:
        if not self.is_connected: return 0
        try:
            ret = await self._loop.run_in_executor(None, self._dev.ctrl_transfer, 0xC0, 1, 0, 0, 2, timeout_ms)
            return ret[0] if ret and len(ret) > 0 else 0
        except usb.core.USBError as e:
            if not (hasattr(e, 'errno') and (e.errno == 110 or e.errno == 60) or "timeout" in str(e).lower()): self.logger.warning(f"Control transfer poll USBError: {e}")
            return 0
        except Exception as e_other: self.logger.warning(f"Unexpected error in control transfer poll: {e_other}"); return 0
            
    async def _read_usb_response_data(self, command: MultidropUSBCommand) -> bytes:
        if not self.is_connected: raise MultidropException(description="USB device (pyusb) not connected for read.")
        raw_accumulator = bytearray()
        overall_timeout_sec = command.timeout if command.timeout is not None else (USB_DEFAULT_TIMEOUT_MS / 1000.0)
        start_time = time.monotonic(); last_data_time = start_time
        while (time.monotonic() - start_time) < overall_timeout_sec:
            await self._perform_control_transfer_poll(timeout_ms=50)
            try:
                data_chunk = await self._loop.run_in_executor(None, self._dev.read, self._EP_IN, USB_RESPONSE_SIZE_HINT, USB_READ_CHUNK_TIMEOUT_MS)
                if data_chunk:
                    chunk_bytes = bytes(data_chunk); raw_accumulator.extend(chunk_bytes); last_data_time = time.monotonic()
                    temp_decoded_str = raw_accumulator.decode('ascii', errors='replace')
                    try:
                        temp_error_check_cmd = MultidropUSBCommand(command.command_text, 1, command.device_mode_for_parsing, self.logger)
                        temp_error_check_cmd._deserialize(raw_accumulator)
                    except MultidropException: break 
                    if command.device_mode_for_parsing == DeviceType.MULTIDROP_MICRO:
                        lines_in_response = temp_decoded_str.strip().splitlines()
                        if lines_in_response and lines_in_response[-1].upper() == "OK": break
                        if command.command_text.split(' ')[0].strip() == "VER" and "MDMICRO V1.1" in temp_decoded_str.upper(): break
                    elif command.device_mode_for_parsing in [DeviceType.MULTIDROP_COMBI, DeviceType.UNKNOWN, DeviceType.MULTIDROP_384, DeviceType.MULTIDROP_DW]:
                        if "END " in temp_decoded_str.upper(): await asyncio.sleep(0.05); break
                else: 
                    current_idle_time_ms = (time.monotonic() - last_data_time) * 1000
                    if raw_accumulator and current_idle_time_ms > 300: break
                    elif not raw_accumulator and current_idle_time_ms > 500: break
                await asyncio.sleep(0.01)
            except usb.core.USBError as e:
                if hasattr(e, 'errno') and (e.errno in [110, 60, 32]) or "timeout" in str(e).lower():
                    if (time.monotonic() - start_time) >= overall_timeout_sec: break
                    if raw_accumulator and (time.monotonic() - last_data_time > 0.3): break
                    await asyncio.sleep(0.05); continue
                else: self._usb_connection_lost(e); raise MultidropException(description=f"USB Read Error: {e}") from e
        return bytes(raw_accumulator)

    async def execute(self, command: MultidropUSBCommand) -> str:
        if not self.is_connected: raise MultidropException(description="USB device (pyusb) not connected or not open.")
        serialized_cmd: bytes = command.serialize()
        try:
            write_timeout_ms = int(command.timeout * 1000) if command.timeout else USB_DEFAULT_TIMEOUT_MS
            await self._loop.run_in_executor(None, self._dev.write, self._EP_OUT, serialized_cmd, write_timeout_ms)
        except usb.core.USBError as e:
            self._usb_connection_lost(e)
            raise MultidropException(description=f"USB Write Error: {e}") from e
        if command.is_void: await asyncio.sleep(0.1); return "OK_VOID" 
        response_bytes = await self._read_usb_response_data(command)
        return command.deserialize(response_bytes)

    async def dispense_plate(self) -> str: return await self.execute(MultidropUSBCommand("D", USB_DISPENSE_TIMEOUT_MS, self.device_type, self.logger))
    async def empty(self) -> str: return await self.execute(MultidropUSBCommand("E", USB_EMPTY_TIMEOUT_MS, self.device_type, self.logger))
    async def dispense_using_start(self) -> str: return await self.execute(MultidropUSBCommand("G", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
    async def dispense_next_n_columns(self, n: typing.Optional[int]) -> str:
        cmd = "M" if n is None else f"M{n}"; return await self.execute(MultidropUSBCommand(cmd, USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
    async def get_firmware_version(self) -> str: return await self.execute(MultidropUSBCommand("VER", USB_DEFAULT_TIMEOUT_MS, DeviceType.UNKNOWN, self.logger))
    async def move_plate_out(self) -> str: return await self.execute(MultidropUSBCommand("O", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
    
    async def prime_volume(self, volume: typing.Optional[int]) -> str:
        if volume is not None and volume % 5 != 0: 
            raise MultidropException(description="Volume must be multiple of 5 µL.")
        current_dev_type = await self.get_device_type()
        cmd_str: str
        if current_dev_type == DeviceType.MULTIDROP_COMBI:
            base_cmd = "PRI"; cmd_arg_str = str(volume) if volume is not None else "200" 
            cmd_str = f"{base_cmd} {cmd_arg_str}"
        else:
            base_cmd = "P"
            if volume is not None: cmd_str = f"{base_cmd}{volume}"
            else: cmd_str = base_cmd
        return await self.execute(MultidropUSBCommand(cmd_str, USB_PRIME_TIMEOUT_MS, current_dev_type, self.logger))

    async def reset(self) -> None:
        was_connected_before_reset = self.is_connected
        try:
            if was_connected_before_reset:
                await self.execute(MultidropUSBCommand("Q", 2000, self.device_type, self.logger, is_void=True))
            else:
                self.logger.warning("Reset called but protocol was not connected. Will skip sending 'Q' and attempt to open.")
        except MultidropException as e:
            if "OK_VOID" not in str(e).upper():
                 self.logger.warning(f"Reset command 'Q' send resulted in an exception: {e}. Proceeding with reset sequence.")
        except Exception as e_generic:
            self.logger.error(f"Unexpected error sending 'Q' command: {e_generic}. Proceeding with reset sequence.")
        finally:
            if self._dev:
                self.logger.info("Invalidating current pyusb device handle due to reset.")
                self._dev = None
            
            reset_exception_desc = "Device was reset and connection is being re-initialized."
            if not was_connected_before_reset:
                reset_exception_desc = "Reset called on disconnected protocol; attempting to initialize connection."
            self._usb_connection_lost(MultidropException(description=reset_exception_desc))

            await asyncio.sleep(5)

            try:
                await self.open()
            except Exception as e_reopen:
                self.logger.error(f"Exception during re-open attempt after reset: {e_reopen}. Protocol likely remains disconnected.")

    async def move_plate_column_to_dispensing_tips(self, column: typing.Optional[int]) -> str:
        cmd = "S" if column is None else f"S{column}"; return await self.execute(MultidropUSBCommand(cmd, USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
    
    async def set_plate_type(self, plate_type_enum_val: PlateType) -> str:
        response = await self.execute(MultidropUSBCommand(f"T{plate_type_enum_val.value}", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
        current_dev_type = await self.get_device_type()
        is_combi_like = current_dev_type in [DeviceType.MULTIDROP_COMBI, DeviceType.UNKNOWN]
        if "OK" in response.upper() or (is_combi_like and "T END 0" in response.upper()):
            self.plate_type = plate_type_enum_val
            self.logger.info(f"Plate type set to {plate_type_enum_val.name}")
        else:
            self.logger.warning(f"Unexpected response setting plate type via USB: {response!r}")
        return response

    async def set_volume(self, volume: int) -> str:
        if volume % 5 != 0: raise MultidropException(description="Volume must be multiple of 5 µL.")
        return await self.execute(MultidropUSBCommand(f"V{volume}", USB_DEFAULT_TIMEOUT_MS, self.device_type, self.logger))
    async def shake(self, duration: int) -> str:
        if not (1 <= duration <= 60): raise MultidropException(description="Shake duration must be between 1 and 60 seconds.")
        timeout_ms = (duration * 1000) + USB_DEFAULT_TIMEOUT_MS
        return await self.execute(MultidropUSBCommand(f"Z{duration}", timeout_ms, self.device_type, self.logger))