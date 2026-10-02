import usb.core
import usb.util
import time
from datetime import datetime
import platform
import threading # For a more robust (but more complex) async read eventually

# --- Device Specifics ---
VID = 0x0AB6
PID = 0x0344
ENDPOINT_OUT = 0x01
ENDPOINT_IN = 0x81
INTERFACE_NUM = 0
CONFIGURATION_NUM = 1 

# --- Timeouts (from multidrop_protocol.py for consistency) ---
INPUT_TIMEOUT = 5  # [s] timeout on receiving message
PRIME_TIMEOUT_SECONDS = 90  # [s] special long timeout for priming
EMPTY_TIMEOUT_SECONDS = 120 # [s] special long timeout for emptying

# --- Global Variables ---
dev = None

# --- Helper Functions ---
def find_and_init_device():
    """Finds the USB device, sets configuration, and claims interface."""
    global dev
    dev = usb.core.find(idVendor=VID, idProduct=PID)

    if dev is None:
        raise ValueError("Multidrop Combi device not found.")
    print("Multidrop Combi device found.")

    if platform.system() == "Linux" or platform.system() == "Darwin":
        try:
            if dev.is_kernel_driver_active(INTERFACE_NUM):
                print(f"Detaching kernel driver from interface {INTERFACE_NUM}")
                dev.detach_kernel_driver(INTERFACE_NUM)
        except usb.core.USBError as e:
            print(f"Could not detach kernel driver (might be okay, or already detached): {e}")
        except NotImplementedError:
            print("is_kernel_driver_active/detach not implemented or not necessary.")
    
    try:
        dev.set_configuration(CONFIGURATION_NUM)
        print(f"Set configuration {CONFIGURATION_NUM}")
    except usb.core.USBError as e:
        if e.errno == 16 or "resource busy" in str(e).lower(): #errno 16 is 'Resource busy'
            print(f"Configuration {CONFIGURATION_NUM} likely already set (Resource busy).")
        else:
            print(f"Error setting configuration: {e}")
            raise

    try:
        usb.util.claim_interface(dev, INTERFACE_NUM)
        print(f"Claimed interface {INTERFACE_NUM}")
    except usb.core.USBError as e:
        if e.errno == 16 or "resource busy" in str(e).lower():
            print(f"Interface {INTERFACE_NUM} likely already claimed (Resource busy).")
        else:
            print(f"Error claiming interface: {e}")
            raise

def perform_control_transfer_poll(timeout=200):
    """
    Performs a control transfer to poll device status / bytes available.
    Returns the number of bytes available, or 0 if error/timeout.
    """
    if dev is None: return 0
    try:
        bmRequestType = usb.util.CTRL_IN | usb.util.CTRL_TYPE_VENDOR | usb.util.CTRL_RECIPIENT_DEVICE # 0xC0
        bRequest = 1      
        wValue = 0
        wIndex = 0        
        wLength = 2       
        ret = dev.ctrl_transfer(bmRequestType, bRequest, wValue, wIndex, wLength, timeout)
        if ret and len(ret) > 0:
            bytes_available = ret[0] 
            return bytes_available
        return 0
    except usb.core.USBError as e:
        if not (e.errno == 110 or e.errno == 60 or "timeout" in str(e).lower()):
             print(f"DEBUG: Control transfer poll USBError: {e} (Errno: {e.errno})")
        return 0

def read_device_response(command_echo_base, overall_timeout_ms=2000, chunk_timeout_ms=500, response_size_hint=128):
    """
    Revised function to read data from the bulk IN endpoint.
    It accumulates data, splits by lines, filters SREs, and looks for an expected END marker.
    """
    if dev is None: return None, []
    
    accumulated_data_for_command = []
    sre_messages = []
    buffer = "" 
    start_time = time.time()
    
    if command_echo_base.upper() == "SRE":
        expected_end_marker = "SRE END 0"
    else:
        expected_end_marker = f"{command_echo_base.upper()} END 0"

    found_command_end_marker = False

    while (time.time() - start_time) * 1000 < overall_timeout_ms:
        perform_control_transfer_poll(timeout=50) 

        try:
            data_chunk = dev.read(ENDPOINT_IN, response_size_hint, chunk_timeout_ms)
            if data_chunk:
                buffer += bytes(data_chunk).decode('ascii', errors='replace')
                
                while '\n' in buffer:
                    line_part, buffer = buffer.split('\n', 1)
                    line = line_part.strip('\r').strip() 
                    
                    if not line: continue
                    
                    if line.startswith("SRE"):
                        if command_echo_base.upper() == "SRE" and line.upper() == expected_end_marker:
                            accumulated_data_for_command.append(line)
                            found_command_end_marker = True
                        else: 
                            sre_messages.append(line)
                    else:
                        accumulated_data_for_command.append(line)
                        if expected_end_marker in line.upper():
                            found_command_end_marker = True
                
                if found_command_end_marker:
                    break 
            else: 
                time.sleep(0.02)

        except usb.core.USBError as e:
            if e.errno == 110 or e.errno == 60 or "[Errno 10060]" in str(e) or "timeout" in str(e).lower(): # Timeout
                if found_command_end_marker: 
                    break
                time.sleep(0.05) 
                continue
            else:
                print(f"Read USBError for '{command_echo_base.strip()}': {e} (Errno: {e.errno})")
                break 
        
        if found_command_end_marker: 
            break

    if buffer.strip():
        line = buffer.strip('\r').strip()
        if line:
            if line.startswith("SRE"):
                if not (command_echo_base.upper() == "SRE" and line.upper() == expected_end_marker):
                     sre_messages.append(line)
                else:
                    accumulated_data_for_command.append(line)
                    if expected_end_marker in line.upper(): found_command_end_marker = True
            else:
                accumulated_data_for_command.append(line)
                if expected_end_marker in line.upper(): found_command_end_marker = True
    
    final_response_str = "\n".join(accumulated_data_for_command).strip()

    if not found_command_end_marker:
        print(f"Warning: Overall read timeout or END marker '{expected_end_marker}' not found for '{command_echo_base}'. Received: '{final_response_str}'")
        
    return final_response_str if final_response_str else None, list(set(sre_messages))


def send_command(command_str, timeout_ms=(INPUT_TIMEOUT * 1000)): # Default to INPUT_TIMEOUT
    """Sends a command and handles its specific response including SREs."""
    if dev is None:
        print("Device not initialized.")
        return None, []

    command_base = command_str.split(' ')[0] 
    print(f"Sending: {command_str.strip()}")
    payload = (command_str + "\r\n").encode('ascii') 

    try:
        bytes_sent = dev.write(ENDPOINT_OUT, payload, timeout_ms) # Use the passed timeout_ms
        
        response, sre_messages = read_device_response(command_base, overall_timeout_ms=timeout_ms)
        
        if response:
            print(f"Received for {command_base}: \n{response}")
        else:
            print(f"No definitive command-specific response for {command_base} within timeout.")
        
        if sre_messages:
            print(f"Associated SREs during {command_base}: {sre_messages}")

        return response, sre_messages 
            
    except usb.core.USBError as e:
        print(f"Write USBError for '{command_str.strip()}': {e} (Errno: {e.errno})")
        return None, []
    return None, []


# --- Sequence Functions ---
def connect_sequence():
    print("\n--- Starting Connect Sequence ---")
    find_and_init_device()
    
    send_command("VER") 
    send_command("EAK") 
    tim_command = datetime.now().strftime("TIM %d.%m.%Y %H:%M:%S") 
    send_command(tim_command)
    send_command("SRE 2") 
    send_command("REP 0") 
    print("--- Connect Sequence Finished ---\n")

def prime_sequence_usb(count=1, volume=100): # Default to priming 100ul once
    print(f"\n--- Starting USB Prime Sequence ({count} times, {volume}uL) ---")
    prime_command = f"P{volume}" # Using P as per MultidropProtocol.py for prime_volume
    # In your MultidropProtocol.py, prime_volume uses "P" and prime_pump calls it.
    # The "PRI" command was from earlier C# analysis, "P" seems more aligned with your protocol file.
    # Let's stick to "P" if it's the one used in your RS232 implementation.
    # If "PRI" is the correct USB command from FILLit, use that.
    # For now, assuming "P" based on your new .py files.
    
    # If the device uses "PRI" for USB based on FillIt software, change this:
    # prime_command = f"PRI {volume}"

    for i in range(count):
        print(f"Priming attempt {i+1}/{count}")
        response, sres = send_command(prime_command, timeout_ms=(PRIME_TIMEOUT_SECONDS * 1000))
        time.sleep(0.5) 
    print("--- USB Prime Sequence Finished ---\n")

# --- New USB Command Function ---
def dispense_plate_usb():
    """
    Dispense the volume set by the 'V' command to the entire plate.
    The instrument internally primes 10 μl into the priming vessel before dispensing.
    Command: "D"
    """
    print("\n--- Starting USB Dispense Plate ---")
    # Assumes volume for dispensing has been set previously via a "V<volume>" command.
    # If not, you might need to send a set_volume_usb command first.
    # For example: set_volume_usb(50) # to set 50uL
    
    response, sres = send_command("D", timeout_ms=(PRIME_TIMEOUT_SECONDS * 1000)) # Uses PRIME_TIMEOUT
    
    if response and "D END 0" in response.upper():
        print("Dispense Plate command successful.")
    elif response:
        print("Dispense Plate command sent, but response was not 'D END 0'.")
    else:
        print("Dispense Plate command did not receive a conclusive response.")
    print("--- USB Dispense Plate Finished ---\n")
    return response, sres

def disconnect_sequence():
    global dev
    print("\n--- Starting Disconnect Sequence ---")
    if dev:
        send_command("EAK", timeout_ms=1000) 
        send_command("QIT", timeout_ms=1000) 
        
        try:
            usb.util.release_interface(dev, INTERFACE_NUM)
            print(f"Released interface {INTERFACE_NUM}")
        except usb.core.USBError as e:
            print(f"Error releasing interface (might be already released or not needed): {e} (Errno: {e.errno})")
        
        dev = None 
        print("Device disconnected (PyUSB object released).")
    else:
        print("Device not connected or already released.")
    print("--- Disconnect Sequence Finished ---\n")

# Example of how you might add set_volume if needed
def set_volume_usb(volume: int):
    """
    Sets the volume for dispensing via USB.
    Volume must be in 5 μl increments.
    Command: "V<volume>"
    """
    print(f"\n--- Setting Volume to {volume}uL via USB ---")
    if volume % 5 != 0:
        print("Error: Volume value must be a multiple of 5 μL.")
        return None, []
    
    command_str = f"V{volume}"
    response, sres = send_command(command_str)

    if response and f"V{volume} END 0" in response.upper(): # Instrument might echo V<vol> or just V
        print(f"Set Volume to {volume}uL successful.")
    elif response:
        print(f"Set Volume command sent, but response was not '{command_base.upper()} END 0'.")
    else:
        print(f"Set Volume command did not receive a conclusive response.")
    print("--- Set Volume Finished ---\n")
    return response, sres


if __name__ == "__main__":
    try:
        connect_sequence()
        if dev: 
            prime_sequence_usb(count=1, volume=100) # Prime 100uL once
            
            # Before dispensing, you usually need to set the volume
            set_volume_usb(20) # Example: Set dispense volume to 20uL

            dispense_plate_usb() # Call the new dispense plate function

    except ValueError as e:
        print(f"Setup or Script error: {e}")
    except usb.core.USBError as e:
        print(f"A major USB communication error occurred: {e} (Errno: {e.errno})")
        if hasattr(e, 'errno') and e.errno == 19: # LIBUSB_ERROR_NO_DEVICE
             print("The device may have been disconnected or reset.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if dev: 
            disconnect_sequence()
        else:
            print("Exiting (device was not connected or already handled).")