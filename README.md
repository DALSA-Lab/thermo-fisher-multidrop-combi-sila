# Thermo Scientific Multidrop Combi 836 - SiLA 2 Server

This repository contains integration resources for the **Thermo Scientific Multidrop Combi 836** liquid dispenser, featuring a custom standalone USB driver and a SiLA 2 server implementation.

The primary enhancement of this project is the addition of **direct USB communication support** via `pyusb`, bypassing the need for legacy RS-232 serial adapters. 

## Demonstration

A video demonstration of a multi-instrument workflow—showing a robotic arm transferring a plate between a washer, sealer, and this **multidrop dispenser** in a fully automated sequence—is available below.

<p align="center">
  <a href="https://youtu.be/lHVm9IDciZc" target="_blank">
    <img src="https://img.youtube.com/vi/lHVm9IDciZc/0.jpg" alt="Watch the Video Demo" width="640" height="480" />
  </a>
</p>

## Repository Structure

### 1. Standalone USB API (`/examples/`)
The `examples/` directory contains `multidrop_usb_test.py`, a standalone Python script developed by DALSA-Lab. 
- **Accessibility:** This script is fully open and has no external dependencies other than `pyusb`.
- **Usage:** It demonstrates low-level USB commands (prime, set volume, dispense, shake) for the "Multidrop Micro" mode.
- **Adaptability:** Because it relies only on standard Python libraries, this API can be easily adapted and ported into any other SiLA SDK (such as `sila2-python`, `sila_csharp`, etc.) or custom automation script.

### 2. SiLA 2 Server (`/SILA_UniteLabs/`)
This directory contains a complete SiLA 2 server implementation supporting both USB and Serial communication.

**⚠️ Important Note Regarding Dependencies:**
The SiLA 2 server in this repository was built using the **UniteLabs CDK** (`unitelabs-cdk` and `unitelabs-bus`). These specific dependencies are hosted on a private package registry maintained by UniteLabs AG. 
- **Credentials Required:** To build and run this specific SiLA server via Poetry, you must have valid authentication credentials for the UniteLabs GitLab package registry.
- **Attribution:** The foundational architecture and serial communication logic for this SiLA 2 connector were originally developed by UniteLabs AG. The USB protocol integration was subsequently developed and added by DALSA-Lab.

*If you have the necessary credentials, you can start the server from within the `SILA_UniteLabs` directory using:*
```bash
poetry install
poetry run connector start --app connector:create_app --verbose
```

## Linux USB Permissions (`udev` Rules)
If running the standalone USB script or the SiLA server on Linux via USB, you must grant your user permission to access the device to avoid `[Errno 13] Access denied` errors:

1. Create a new `udev` rule file:
   ```bash
   sudo nano /etc/udev/rules.d/99-multidrop.rules
   ```
2. Add the following line (matching the VID/PID of the Multidrop):
   ```udev
   SUBSYSTEM=="usb", ATTR{idVendor}=="0ab6", ATTR{idProduct}=="0344", MODE="0666", GROUP="plugdev"
   ```
3. Reload rules and re-plug the device:
   ```bash
   sudo udevadm control --reload-rules
   sudo udevadm trigger