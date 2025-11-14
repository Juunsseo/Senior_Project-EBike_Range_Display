# EBike Sensor System – Raspberry Pi Pico W + INA228 + BLE + E-Ink Display

This project implements a fully embedded **E-bike telemetry module** using the **Raspberry Pi Pico W**, featuring:

- **High-precision voltage/current/power sensing** via INA228  
- **Encrypted BLE connection with owner-only whitelist security**  
- **BLE notification of sensor data** (Voltage, Current, Power, Temperature, Battery %)  
- **Writable BLE channel** for receiving commands from a smartphone  
- **Concurrent asynchronous tasks** using MicroPython asyncio  
- **E-Ink display UI** showing sensor data + BLE-received messages  
- **Soft real-time loop (1Hz)** for sensing, BLE updates, and display refresh

## System Architecture

```
                +------------------------------+
                |     Raspberry Pi Pico W      |
                |------------------------------|
   INA228 ----> |  Sensor Task (I2C @ 400kHz)  |
                |          Reads:              |
                |  - VBUS Voltage              |
                |  - Shunt Current             |
                |  - Power                     |
                |  - Temperature               |
                |------------------------------|
                |   BLE Service (aioble)       |
                |   - Notify 5 characteristics |
                |   - Writable RX channel      |
                |   - Whitelist security       |
                |------------------------------|
                |     Display Task (E-Ink)     |
                |     Shows sensor + RX data   |
                +------------------------------+
```

## Features

### 1. High-Accuracy Power Monitoring (INA228)

- Voltages, currents, power, internal temperature  
- Sampled at **1 Hz**  
- Shared across BLE + display  

### 2. BLE Interface (aioble)

Includes:

| Metric         | UUID     | Format         |
|----------------|----------|----------------|
| Voltage (mV)   | 0x2B18   | `uint16`       |
| Current (mA)   | 0x2704   | `sint16`       |
| Power (W)      | 0x2726   | `uint16`       |
| Battery %      | 0x2A19   | `uint8`        |
| Temperature    | 0x2A6E   | `sint16`       |

Plus a custom **writable RX characteristic** for smartphone → Pico commands.

### 3. BLE Security: Owner-Only Whitelist

- First connected phone becomes the **trusted owner**  
- All other connections auto-rejected  
- Approximates secure pairing on platforms that do not support passkey  
- Optional: add hardware reset for clearing whitelist  

### 4. E-Ink UI Display

Shows:

- Voltage  
- Current  
- Power  
- BLE RX text  
- Large readable scale  
- Full/partial refresh  

### 5. Async Architecture

All tasks run concurrently under MicroPython asyncio:

- Sensor polling  
- BLE advertisement / connection handling  
- BLE RX writes  
- Display updates  

## Repository Structure

```
/
├── main.py              # INA228 reading + asyncio orchestration
├── ble.py               # BLE services + whitelist + RX handler
├── display.py           # E-Ink UI + scaled text drawing
├── ina228.py            # INA228 driver
├── epaper_driver.py     # Waveshare 3.7" E-Ink driver
└── README.md
```

## How to Use

1. Flash Pico W with MicroPython  
2. Upload all `.py` files  
3. Reboot  
4. Connect from smartphone (first device becomes owner)  
5. Use BLE scanner to write to RX channel  
6. Text appears instantly on E-Ink display  

## Example BLE RX

Write `"hello"` to the RX characteristic:

Console:

```
RX DATA = hello
```

E-Ink:

```
RX: hello
```

## Future Improvements

- Persistent whitelist in flash  
- Passkey-like workflow via app UI  
- OTA updates  
- Mobile app design  

## License

MIT License.

