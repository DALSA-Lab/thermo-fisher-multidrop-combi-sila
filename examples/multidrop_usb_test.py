import usb.core
import usb.util
import time
from datetime import datetime
import platform
import enum
import re

# --- Device Specifics ---
VID = 0x0AB6
PID = 0x0344
ENDPOINT_OUT = 0x01
ENDPOINT_IN = 0x81
INTERFACE_NUM = 0
CONFIGURATION_NUM = 1

# --- Timeouts ---
INPUT_TIMEOUT_MS = 5 * 1000
PRIME_TIMEOUT_MS = 10 * 1000  # For P commands
DISPENSE_TIMEOUT_MS = 20 * 1000 # Increased for D command (prime + dispense)
EMPTY_TIMEOUT_MS = 10 * 1000
MAX_SHAKE_TIME_S = 60

# --- Error Dictionary ---
errors = {
    "ER1": "Internal firmware error. Contact service.",
    "ER2": "The instrument did not recognize the command it received. Contact the SiLAConverter vendor.",
    "ER3": "Unrecognized command or invalid command argument.",
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
    "ER31": "description", # Placeholder, typically specific error
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

# --- Global Variables ---
dev = None

class DeviceMode(enum.Enum):
    UNKNOWN = 0
    MICRO = 1
    COMBI = 2

current_device_mode = DeviceMode.UNKNOWN
current_plate_type_value = 0 # 0 for 96-well, 1 for 384-well

test_results = {}
test_passed_count = 0
test_total_count = 0

# --- Helper Functions ---
def find_and_init_device():
    global dev
    dev = usb.core.find(idVendor=VID, idProduct=PID)
    if dev is None: raise ValueError("Multidrop device not found.")
    print("Multidrop device found.")
    if platform.system() in ["Linux", "Darwin"]:
        try:
            if dev.is_kernel_driver_active(INTERFACE_NUM):
                print(f"Detaching kernel driver from interface {INTERFACE_NUM}")
                dev.detach_kernel_driver(INTERFACE_NUM)
        except Exception as e: print(f"Kernel driver detach issue (might be okay): {e}")
    try:
        dev.set_configuration(CONFIGURATION_NUM)
        print(f"Set configuration {CONFIGURATION_NUM}")
    except usb.core.USBError as e:
        if hasattr(e, 'errno') and e.errno == 16 or "resource busy" in str(e).lower():
            print(f"Config {CONFIGURATION_NUM} likely already set.")
        else: raise
    try:
        usb.util.claim_interface(dev, INTERFACE_NUM)
        print(f"Claimed interface {INTERFACE_NUM}")
    except usb.core.USBError as e:
        if hasattr(e, 'errno') and e.errno == 16 or "resource busy" in str(e).lower():
            print(f"Interface {INTERFACE_NUM} likely already claimed.")
        else: raise

def perform_control_transfer_poll(timeout=200):
    if dev is None: return 0
    try:
        ret = dev.ctrl_transfer(0xC0, 1, 0, 0, 2, timeout)
        return ret[0] if ret and len(ret) > 0 else 0
    except usb.core.USBError as e:
        if not (hasattr(e, 'errno') and (e.errno == 110 or e.errno == 60) or "timeout" in str(e).lower()):
            pass
        return 0

def parse_raw_response(raw_response_str, command_base):
    lines = raw_response_str.strip().splitlines()
    primary_response_parts, sre_list, error_details_list = [], [], []
    for line in (l.strip() for l in lines if l.strip()):
        if line.startswith("SRE"): sre_list.append(line)
        elif line.startswith("ER"):
            err_code = line.split(' ')[0]
            error_details_list.append(f"{err_code}: {errors.get(err_code, f'Unknown error: {err_code}')}")
        elif command_base == "VER" and "MDMICRO V1.1" in line.upper():
            primary_response_parts.append(line)
        elif line.upper().startswith(command_base.upper()) and not line.startswith("ER") and not line.startswith("SRE"):
             primary_response_parts.append(line)
        elif not line.upper().startswith("ER") and not line.upper().startswith("SRE"):
            primary_response_parts.append(line)

    return "\n".join(primary_response_parts).strip(), list(set(sre_list)), list(set(error_details_list))


def check_command_success(command_base, primary_response, error_list_with_desc, mode: DeviceMode,
                          expected_response_override=None, expected_error_override=None):
    if expected_error_override:
        for err_detail in error_list_with_desc:
            if expected_error_override in err_detail:
                return True, f"Successfully received expected error: {err_detail}"
        return False, f"Expected error '{expected_error_override}' not found. Errors: {error_list_with_desc}. Response: '{primary_response}'"

    if error_list_with_desc:
        return False, f"Unexpected error(s) received: {'; '.join(error_list_with_desc)}"

    if expected_response_override is not None:
        if expected_response_override.upper() == primary_response.upper().strip():
             return True, f"Matches expected response: '{expected_response_override}'"
        elif expected_response_override in primary_response:
             return True, f"Contains expected response: '{expected_response_override}'"
        else:
             return False, f"Expected '{expected_response_override}', got '{primary_response}'"

    if command_base == "VER":
        if "MDMICRO V1.1" in primary_response.upper(): return True, "Device identified as Micro (MDMicro V1.1)"
        if "MULTIDROPCOMBI" in primary_response.upper() and "VER END 0" in primary_response.upper():
            return True, "Device identified as Combi (MultidropCombi and VER END 0)"
        return False, f"VER response '{primary_response}' not recognized by generic check."

    if mode == DeviceMode.MICRO:
        if command_base == "Q": return True, "Reset 'Q' (Micro) sent (no error, response not checked beyond errors)"
        if command_base in ["V", "EAK", "E", "P", "PRI", "T", "D", "M", "G", "O", "S", "Z"]:
            return "OK" == primary_response.upper().strip(), f"Expected 'OK' for {command_base}, got '{primary_response}'"
        if primary_response:
            return True, f"Cmd '{command_base}' (Micro) received: '{primary_response}' (no specific expectation beyond no error)"
        return True, f"Cmd '{command_base}' (Micro) sent (no direct resp/error, verify SREs/action)"

    elif mode == DeviceMode.COMBI or mode == DeviceMode.UNKNOWN:
        if command_base == "Q": return True, "Reset 'Q' (Combi) sent (no error, response not checked beyond errors)"
        if command_base == "SRE": return "SRE END 0" in primary_response.upper(), f"Expected 'SRE END 0', got '{primary_response}'"
        expected_marker = f"{command_base.upper()} END 0"
        if expected_marker in primary_response.upper(): return True, f"Successful ({expected_marker})"
        status_2_marker = f"{command_base.upper()} END 2"
        if status_2_marker in primary_response.upper(): return True, f"Cmd acknowledged status 2 ({status_2_marker})"

    return False, f"Success condition for '{command_base}' in {mode.name} not met. Response: '{primary_response}'"


def read_usb_response_data(command_base, overall_timeout_ms, chunk_timeout_ms, response_size_hint, mode: DeviceMode, expect_no_response=False):
    if expect_no_response:
        return ""

    raw_accumulator = bytearray()
    start_time = time.monotonic()
    last_data_time = start_time

    while (time.monotonic() - start_time) * 1000 < overall_timeout_ms:
        perform_control_transfer_poll(timeout=50)
        try:
            data_chunk = dev.read(ENDPOINT_IN, response_size_hint, chunk_timeout_ms)
            if data_chunk:
                raw_accumulator.extend(data_chunk)
                last_data_time = time.monotonic()
                temp_decoded_full_response = raw_accumulator.decode('ascii', errors='replace')
                temp_primary, _, temp_errors = parse_raw_response(temp_decoded_full_response, command_base)

                if temp_errors: break

                if mode == DeviceMode.MICRO:
                    if command_base in ["V", "EAK", "E", "T", "P", "PRI", "D", "M", "G", "O", "S", "Z"] and "OK" in temp_primary.upper(): break
                    if command_base == "VER" and "MDMICRO V1.1" in temp_primary.upper(): break
                elif "END " in temp_decoded_full_response.upper():
                    time.sleep(0.05)
                    break
            else:
                current_idle_time = time.monotonic() - last_data_time
                if raw_accumulator and current_idle_time > 0.3: break
                elif not raw_accumulator and current_idle_time > 0.5: break
            time.sleep(0.02)
        except usb.core.USBError as e:
            if hasattr(e, 'errno') and (e.errno == 110 or e.errno == 60) or "timeout" in str(e).lower():
                if (time.monotonic() - start_time) * 1000 >= overall_timeout_ms: break
                if raw_accumulator and (time.monotonic() - last_data_time) > 0.3 : break
                time.sleep(0.05)
                continue
            else:
                print(f"Read USBError for '{command_base.strip()}': {e}")
                break
    return bytes(raw_accumulator).decode('ascii', errors='replace')


def send_usb_command(command_str, timeout_ms=INPUT_TIMEOUT_MS, mode_override: DeviceMode = None,
                     expected_response_str=None, expect_error_code=None,
                     expect_no_response=False):
    global current_device_mode
    effective_mode = mode_override if mode_override is not None else current_device_mode
    if dev is None: return None, [], ["Device not initialized."], False

    command_base = command_str.split(' ')[0].strip()
    print(f"Sending ({effective_mode.name} mode): {command_str.strip()}")
    payload = (command_str.strip() + "\r\n").encode('ascii')

    try:
        dev.write(ENDPOINT_OUT, payload, timeout_ms)
        raw_response_str = ""
        if not expect_no_response:
            raw_response_str = read_usb_response_data(command_base, timeout_ms, max(200, timeout_ms // 20), 128, effective_mode, expect_no_response)

        primary_resp_str, sre_list, error_details_list = parse_raw_response(raw_response_str, command_base)

        if command_base == "VER" and not error_details_list:
            if "MDMICRO V1.1" in primary_resp_str.upper(): current_device_mode = DeviceMode.MICRO
            elif "MULTIDROPCOMBI" in primary_resp_str.upper(): current_device_mode = DeviceMode.COMBI
            else: current_device_mode = DeviceMode.UNKNOWN
            effective_mode = current_device_mode
            print(f"DEBUG: Device mode auto-set to: {current_device_mode.name} based on VER response: '{primary_resp_str}'")

        success, status_message = check_command_success(command_base, primary_resp_str, error_details_list, effective_mode,
                                                      expected_response_override=expected_response_str,
                                                      expected_error_override=expect_error_code)

        if primary_resp_str or error_details_list or (expect_no_response and not raw_response_str):
             print(f"Received for {command_base}: \n{primary_resp_str if primary_resp_str else ('No response (as expected)' if expect_no_response else 'No primary response data.')}")
        if sre_list: print(f"Associated SREs during {command_base}: {sre_list}")
        print(f"Command Status for '{command_str.strip()}': {'Success' if success else 'Failed/Uncertain'}. Detail: {status_message}")
        return primary_resp_str, sre_list, error_details_list, success

    except usb.core.USBError as e:
        err_msg = f"USB Write/Read Error for '{command_str.strip()}': {e}"
        print(err_msg); return None, [], [err_msg], False
    return None, [], ["Unknown issue in send_usb_command"], False


# --- USB Command Functions (Wrapper functions that call send_usb_command) ---
def connect_sequence_usb():
    global current_device_mode
    print("\n--- Starting Connect Sequence (USB) ---")
    try:
        find_and_init_device()
    except Exception as e:
        print(f"Failed to find/init device: {e}")
        return False

    _, _, _, ver_success_micro = send_usb_command("VER", timeout_ms=INPUT_TIMEOUT_MS, mode_override=DeviceMode.UNKNOWN, expected_response_str="MDMicro V1.1")
    if ver_success_micro and current_device_mode == DeviceMode.MICRO:
        print("Device confirmed in Micro mode via VER. Connect sequence complete.")
        print("--- Connect Sequence Finished ---\n")
        return True
    
    _, _, _, ver_success_combi = send_usb_command("VER", timeout_ms=INPUT_TIMEOUT_MS, mode_override=DeviceMode.UNKNOWN, expected_response_str="MULTIDROPCOMBI")
    if ver_success_combi and current_device_mode == DeviceMode.COMBI:
        print("Device confirmed in Combi mode via VER. Proceeding with Combi handshake.")
        send_usb_command("EAK", timeout_ms=INPUT_TIMEOUT_MS)
        tim_command = datetime.now().strftime("TIM %d.%m.%Y %H:%M:%S")
        send_usb_command(tim_command, timeout_ms=INPUT_TIMEOUT_MS)
        send_usb_command("SRE 2", timeout_ms=INPUT_TIMEOUT_MS)
        send_usb_command("REP 0", timeout_ms=INPUT_TIMEOUT_MS)
        print("--- Connect Sequence Finished (Combi) ---\n")
        return True

    print(f"VER command failed or mode not determinable. Current mode detected: {current_device_mode.name}. Aborting connect.")
    print("--- Connect Sequence Finished (Failed) ---\n")
    return False

def set_plate_type_usb(plate_type_val: int, expected_response_str="OK", expect_error_code=None):
    global current_plate_type_value
    # print(f"\n--- Setting Plate Type to T{plate_type_val} ({current_device_mode.name} mode) ---")
    res_tuple = send_usb_command(f"T{plate_type_val}", timeout_ms=INPUT_TIMEOUT_MS,
                                 expected_response_str=expected_response_str if not expect_error_code else None,
                                 expect_error_code=expect_error_code)
    if res_tuple[3] and not expect_error_code:
        current_plate_type_value = plate_type_val
    return res_tuple

def set_volume_usb(volume_ul: int, expected_response_str="OK", expect_error_code=None, force_send=False):
    if not force_send and volume_ul % 5 != 0 and not expect_error_code:
        print(f"Error (Client-side): Volume ({volume_ul}uL) must be multiple of 5 uL.")
        return None, [], [f"Client-side validation: Vol not multiple of 5"], False
    return send_usb_command(f"V{volume_ul}", timeout_ms=INPUT_TIMEOUT_MS,
                            expected_response_str=expected_response_str if not expect_error_code else None,
                            expect_error_code=expect_error_code)

def prime_pump_usb(volume_ul: int = None, count: int = 1, expected_response_str="OK", expect_error_code=None):
    if volume_ul is not None and volume_ul % 5 != 0 and not expect_error_code:
        print(f"Error: Prime volume ({volume_ul}uL) must be a multiple of 5 uL if specified.")
        return None, [], ["Client-side prime vol validation"], False

    prime_cmd_str = f"P{volume_ul}" if volume_ul is not None else "P"
    current_expected_resp = expected_response_str
    if current_device_mode == DeviceMode.COMBI:
        prime_cmd_str = f"PRI {volume_ul if volume_ul is not None else 200}"
        current_expected_resp = f"{prime_cmd_str.split(' ')[0].upper()} END 2" if not expect_error_code else None

    overall_op_success = True
    last_res_tuple = (None, [], [], False)
    for i in range(count):
        print(f"Priming attempt {i+1}/{count} with command: '{prime_cmd_str}'")
        last_res_tuple = send_usb_command(prime_cmd_str, timeout_ms=PRIME_TIMEOUT_MS,
                                           expected_response_str=current_expected_resp if not expect_error_code else None,
                                           expect_error_code=expect_error_code)
        if not last_res_tuple[3]:
            overall_op_success = False
            print(f"Priming attempt {i+1} failed/uncertain.")
        print(f"Pausing after prime command attempt {i+1}...");
        time.sleep(max(3, (volume_ul if volume_ul is not None else 100) // 20))
    return last_res_tuple[0], last_res_tuple[1], last_res_tuple[2], overall_op_success


def dispense_plate_usb(expected_response_str=None, expect_error_code=None):
    if expected_response_str is None and expect_error_code is None:
        expected_response_str = "OK" if current_device_mode == DeviceMode.MICRO else "D END 0"
    res = send_usb_command("D", timeout_ms=DISPENSE_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def empty_pump_usb(expected_response_str="OK", expect_error_code=None):
    res = send_usb_command("E", timeout_ms=EMPTY_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def dispense_using_start_usb(expected_response_str="OK", expect_error_code=None):
    res = send_usb_command("G", timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def dispense_next_n_columns_usb(n: int = None, expected_response_str="OK", expect_error_code=None):
    cmd = "M"
    if n is not None: cmd = f"M{n}"
    res = send_usb_command(cmd, timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def get_firmware_version_N_usb(expected_response_str="MDMicro V1.1", expect_error_code=None):
    res = send_usb_command("N", timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def get_firmware_version_V_paramless_usb(expected_response_str="MDMicro V1.1", expect_error_code=None):
    res = send_usb_command("V", timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def move_plate_out_usb(expected_response_str="OK", expect_error_code=None):
    res = send_usb_command("O", timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def reset_usb(): 
    global dev
    # print(f"\n--- Resetting Instrument ('Q') ({current_device_mode.name} mode) ---")
    res_tuple = send_usb_command("Q", timeout_ms=2000, expect_no_response=True)
    if res_tuple[3]:
        print("Reset command 'Q' sent. Device handle will be invalidated and connection considered lost.")
        dev = None
    return res_tuple

def move_plate_column_to_dispensing_tips_usb(column: int = None, expected_response_str="OK", expect_error_code=None):
    cmd = "S"
    if column is not None: cmd = f"S{column}"
    res = send_usb_command(cmd, timeout_ms=INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def shake_usb(duration_s: int, expected_response_str="OK", expect_error_code=None):
    if not expect_error_code and not (1 <= duration_s <= MAX_SHAKE_TIME_S) :
        print(f"Warning (Client-side): Shake duration ({duration_s}s) outside 1-60s. Still attempting to send command.")
    res = send_usb_command(f"Z{duration_s}", timeout_ms=duration_s * 1000 + INPUT_TIMEOUT_MS,
                           expected_response_str=expected_response_str if not expect_error_code else None,
                           expect_error_code=expect_error_code)
    return res

def get_device_type_usb():
    return current_device_mode.name if current_device_mode != DeviceMode.UNKNOWN else "Unknown"

def get_plate_type_usb():
    return "96-well" if current_plate_type_value == 0 else "384-well" if current_plate_type_value == 1 else "Unknown"


def disconnect_sequence_usb():
    global dev, current_device_mode
    mode_name = current_device_mode.name if current_device_mode != DeviceMode.UNKNOWN else 'Unknown (or disconnected)'
    print(f"\n--- Starting Disconnect Sequence ({mode_name} mode) ---")
    if dev:
        if current_device_mode == DeviceMode.COMBI:
            print("Attempting EAK (Combi)...")
            send_usb_command("EAK", timeout_ms=INPUT_TIMEOUT_MS, expect_no_response=True)
            print("Attempting QIT (Combi)...")
            send_usb_command("QIT", timeout_ms=INPUT_TIMEOUT_MS, expect_no_response=True)
        elif current_device_mode == DeviceMode.MICRO:
            print("Disconnect for Micro mode: No specific EAK/QIT sent.")
        
        try:
            print("Attempting to release USB interface...")
            usb.util.release_interface(dev, INTERFACE_NUM)
            print(f"Released interface {INTERFACE_NUM}")
        except Exception as e:
            print(f"Error releasing interface: {e}")
        dev = None
        print("USB device object reference removed.")
    else:
        print("Device not connected or already cleaned up.")
    current_device_mode = DeviceMode.UNKNOWN
    print("--- Disconnect Sequence Finished ---\n")


if __name__ == "__main__":
    print("IMPORTANT: Ensure device is in 'Multidrop Micro' mode for this automated test suite.")
    print("Starting test suite in 3 seconds...")
    time.sleep(3)

    test_results = {}
    test_passed_count = 0
    test_total_count = 0

    def run_test(command_description, function_to_call_lambda,
                 expected_response_val=None, expect_error_code_val=None):
        global test_passed_count, test_total_count, test_results

        test_total_count += 1
        print(f"\n--- TEST: {command_description} ---")
        print(f"Running: {command_description} (Expect: {expected_response_val or expect_error_code_val or 'Default Success'})")

        _, _, _, success_flag = function_to_call_lambda()

        if success_flag:
            print(f"PASS: {command_description}")
            test_passed_count +=1
        else:
            print(f"FAIL: {command_description}")
        test_results[command_description] = success_flag
        time.sleep(1.5)

    # --- Start Test Suite ---
    if not connect_sequence_usb():
        print("Initial connection failed. Aborting test suite.")
        if dev: disconnect_sequence_usb()
        exit()

    if current_device_mode != DeviceMode.MICRO:
        print(f"Device not in MICRO mode (detected: {current_device_mode.name}). Aborting Micro-specific test suite.")
        if dev: disconnect_sequence_usb()
        exit()

    print(f"\n======= Starting Test Suite for Multidrop Micro (Initial Plate Type: {get_plate_type_usb()}) =======")

    print("\nSetting initial state for tests (Plate Type T0, Volume V10, Prime)...")
    run_test("Set Plate Type to 96-well 'T0'", lambda: set_plate_type_usb(0, expected_response_str="OK"), "OK")
    run_test("Set Volume to 10uL 'V10'", lambda: set_volume_usb(10, expected_response_str="OK"), "OK")
    run_test("Initial Prime (param-less 'P', 2x)", lambda: prime_pump_usb(count=2, expected_response_str="OK"), "OK")

    run_test("Dispense Plate 'D'", lambda: dispense_plate_usb(expected_response_str="OK"), "OK")
    run_test("Empty Pump 'E'", lambda: empty_pump_usb(expected_response_str="OK"), "OK")
    
    # Test G - Dispense using Start Key - EXPECT ER4 after Emptying
    run_test("Dispense using Start Key 'G'", lambda: dispense_using_start_usb(expect_error_code="ER4"), None, "ER4")

    print("\nRe-priming before M-command and S-command tests to ensure defined state...")
    run_test("Re-Prime (param-less 'P', 1x)", lambda: prime_pump_usb(count=1, expected_response_str="OK"), "OK")
    
    print("Moving to column 1 before M-command tests...")
    run_test("Move to Column 1 'S1'", lambda: move_plate_column_to_dispensing_tips_usb(1, expected_response_str="OK"), "OK")
    time.sleep(1)

    run_test("Dispense Next Column 'M'", lambda: dispense_next_n_columns_usb(expected_response_str="OK"), "OK")
    run_test("Dispense Next 2 Columns 'M2'", lambda: dispense_next_n_columns_usb(n=2, expected_response_str="OK"), "OK")
    run_test("Dispense 12 Columns 'M12' (expect ER3)", lambda: dispense_next_n_columns_usb(n=12, expect_error_code="ER3"), None, "ER3")

    run_test("Get Version 'N'", lambda: get_firmware_version_N_usb(expected_response_str="MDMicro V1.1"), "MDMicro V1.1")
    run_test("Get Version 'V' (param-less)", lambda: get_firmware_version_V_paramless_usb(expected_response_str="MDMicro V1.1"), "MDMicro V1.1")

    run_test("Move Plate Out 'O'", lambda: move_plate_out_usb(expected_response_str="OK"), "OK")

    print("\n--- Further Priming Tests ---")
    run_test("Prime 5uL 'P5'", lambda: prime_pump_usb(volume_ul=5, count=1, expected_response_str="OK"), "OK")
    run_test("Prime Default (param-less 'P')", lambda: prime_pump_usb(count=1, expected_response_str="OK"), "OK")

    run_test("Reset Instrument 'Q'", reset_usb, None)

    print("\nAttempting to reconnect and set up after Reset (if 'Q' was tested and successful)...")
    if 'Reset Instrument \'Q\'' in test_results and test_results['Reset Instrument \'Q\'']:
        if dev is not None: disconnect_sequence_usb()
        print("Waiting 15 seconds for device to reset and re-enumerate...")
        time.sleep(15)
        reconnected_successfully = False
        for attempt in range(3):
            print(f"Reconnection attempt {attempt + 1}/3 after reset...")
            if connect_sequence_usb() and current_device_mode == DeviceMode.MICRO:
                print("Reconnected successfully to Micro mode after reset.")
                set_plate_type_usb(0, expected_response_str="OK")
                set_volume_usb(10, expected_response_str="OK")
                prime_pump_usb(count=1, expected_response_str="OK")
                reconnected_successfully = True
                break
            else:
                print(f"Reconnection attempt {attempt + 1} failed or not in Micro mode.")
                if dev: disconnect_sequence_usb()
                if attempt < 2: time.sleep(7)
        if not reconnected_successfully:
            print("Failed to reconnect or verify Micro mode after reset. Subsequent tests may fail or be unreliable.")
    else:
        print("Reset command did not pass or was not run; skipping post-reset re-initialization.")

    if dev and current_device_mode == DeviceMode.MICRO :
        run_test("Move to Column 2 'S2'", lambda: move_plate_column_to_dispensing_tips_usb(column=2, expected_response_str="OK"), "OK")
        run_test("Move Plate One Step 'S'", lambda: move_plate_column_to_dispensing_tips_usb(expected_response_str="OK"), "OK")
        run_test("Set Plate Type 384-well 'T1'", lambda: set_plate_type_usb(1, expected_response_str="OK"), "OK")

        run_test("Set Volume 6uL 'V6' (device returns OK)",
                 lambda: set_volume_usb(6, expected_response_str="OK", force_send=True), "OK")

        run_test("Shake 1s 'Z1'", lambda: shake_usb(1, expected_response_str="OK"), "OK")
        run_test("Shake 65s 'Z65' (expect device ER3)",
                 lambda: shake_usb(duration_s=65, expect_error_code="ER3"), None, "ER3")
    else:
        print("Skipping some post-reset tests due to connection/mode issues after reset attempt.")


    print("\n======= Test Suite Finished =======")
    print(f"Results: {test_passed_count}/{test_total_count} tests met expectations.")
    for test_desc, result_ok in test_results.items():
        print(f"- {test_desc}: {'PASS' if result_ok else 'FAIL'}")

    if dev: disconnect_sequence_usb()
    else: print("Exiting (device already disconnected or not initialized).")