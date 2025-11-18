from micropython import const
import asyncio
import aioble
import bluetooth
import struct

rx_value = None
from display import sensor_data   # ADD THIS at top of ble.py

# =========================================================
# BLE OFFICIAL SIG UUIDs
# =========================================================

# Battery Service (standard)
_BAT_SERV_UUID = bluetooth.UUID(0x180F)

# Standard Characteristics
_VOLTAGE_UUID       = bluetooth.UUID(0x2B18)  # Voltage (uint16, mV)
_CURRENT_UUID       = bluetooth.UUID(0x2704)  # Electric Current (sint16, mA)
_POWER_UUID         = bluetooth.UUID(0x2726)  # Power (uint16, W)
_BATTERY_LEVEL_UUID = bluetooth.UUID(0x2A19)  # Battery Level (%)
_TEMPERATURE_UUID   = bluetooth.UUID(0x2A6E)  # Temperature (sint16, 0.01°C)

_RX_UUID = bluetooth.UUID("12345678-1234-5678-1234-56789abcdef0")	#data from phone

# =========================================================
# Advertising config
# =========================================================

_ADV_APPEARANCE_GENERIC_SENSOR = const(1344)
_ADV_INTERVAL_US = const(250_000)

# =========================================================
# BLE Services + Characteristics
# =========================================================

battery_service = aioble.Service(_BAT_SERV_UUID)

voltage_ch = aioble.Characteristic(
    battery_service, _VOLTAGE_UUID, read=True, notify=True
)

current_ch = aioble.Characteristic(
    battery_service, _CURRENT_UUID, read=True, notify=True
)

power_ch = aioble.Characteristic(
    battery_service, _POWER_UUID, read=True, notify=True
)

battery_ch = aioble.Characteristic(
    battery_service, _BATTERY_LEVEL_UUID, read=True, notify=True
)

temperature_ch = aioble.Characteristic(
    battery_service, _TEMPERATURE_UUID, read=True, notify=True
)

rx_ch = aioble.Characteristic(
    battery_service,
    _RX_UUID,
    read=False,
    write=True,        # <-- allow phone → Pico write
    notify=False
)

aioble.register_services(battery_service)

# =========================================================
# Whitelist: "trust first phone, block others"
# =========================================================

# (addr_type, addr_bytes) of the one "owner" device.
_authorized_peer = None  # type: tuple[int, bytes] | None


def _format_peer(dev) -> tuple[int, bytes]:
    """Return a stable representation (addr_type, addr_bytes)."""
    return (dev.addr_type, bytes(dev.addr))


# =========================================================
# API for main.py to push sensor data into BLE
# =========================================================

def ble_update(voltage: float, current: float, power: float,
               temperature: float, battery_level: int) -> None:
    """
    Update all BLE characteristics and notify any connected central.

    voltage      : Volts (float)
    current      : Amps  (float)
    power        : Watts (float)
    temperature  : Deg C (float)
    battery_level: Percent 0–100 (int)
    """
    # Standard Bluetooth SIG encodings:

    # VOLTAGE (0x2B18) — uint16, mV
    v_mv = int(voltage * 1000)
    voltage_ch.write(struct.pack("<H", v_mv), send_update=True)

    # CURRENT (0x2704) — sint16, mA
    i_ma = int(current * 1000)
    current_ch.write(struct.pack("<h", i_ma), send_update=True)

    # POWER (0x2726) — uint16, W
    p_w = int(power)
    if p_w < 0:
        p_w = 0
    if p_w > 0xFFFF:
        p_w = 0xFFFF
    power_ch.write(struct.pack("<H", p_w), send_update=True)

    # TEMPERATURE (0x2A6E) — sint16, 0.01°C
    t_100 = int(temperature * 100)
    temperature_ch.write(struct.pack("<h", t_100), send_update=True)

    # BATTERY LEVEL (0x2A19) — uint8, %
    lvl = max(0, min(100, int(battery_level)))
    battery_ch.write(struct.pack("B", lvl), send_update=True)


# =========================================================
# BLE Peripheral — Advertising / Connections with whitelist / Wait for rx from Phone
# =========================================================


async def rx_task():
    global rx_value

    while True:
        conn = await rx_ch.written()
        data = rx_ch.read()       # <-- actual bytes from the phone

        if isinstance(data, (bytes, bytearray)):
            rx_value = data
            text = data.decode("utf-8", "ignore")
            print("RX DATA =", text)

            # Parse incoming payload into `pas`, `speed`, and `c_range`.
            pas_val = ""
            speed_val = 0.0
            c_range_val = 0.0

            s = text.strip()

            # Try JSON first (use ujson on MicroPython if available)
            try:
                import ujson as json
            except Exception:
                json = None

            parsed = False
            if json and s.startswith("{") and s.endswith("}"):
                try:
                    obj = json.loads(s)
                    pas_val = obj.get("pas", obj.get("rx", pas_val))
                    speed_val = float(obj.get("speed", speed_val) or 0)
                    c_range_val = float(obj.get("c_range", c_range_val) or 0)
                    parsed = True
                except Exception:
                    parsed = False

            # Key:Value pairs like "pas:1,speed:12.3,c_range:45"
            if not parsed and ":" in s and "," in s:
                try:
                    parts = [p.strip() for p in s.split(",")]
                    for p in parts:
                        if ":" in p:
                            k, v = p.split(":", 1)
                            k = k.strip().lower()
                            v = v.strip()
                            if k in ("pas", "rx"):
                                pas_val = v
                            elif k == "speed":
                                try:
                                    speed_val = float(v)
                                except Exception:
                                    pass
                            elif k in ("c_range", "range", "crange"):
                                try:
                                    c_range_val = float(v)
                                except Exception:
                                    pass
                    parsed = True
                except Exception:
                    parsed = False

            # Simple CSV: pas,speed,c_range
            if not parsed and "," in s:
                try:
                    parts = [p.strip() for p in s.split(",")]
                    if len(parts) >= 1:
                        pas_val = parts[0]
                    if len(parts) >= 2:
                        try:
                            speed_val = float(parts[1])
                        except Exception:
                            pass
                    if len(parts) >= 3:
                        try:
                            c_range_val = float(parts[2])
                        except Exception:
                            pass
                    parsed = True
                except Exception:
                    parsed = False

            # Fallback: single token -> treat as pas
            if not parsed:
                pas_val = s

            # UPDATE DISPLAY SHARED VALUE
            sensor_data["pas"] = pas_val
            sensor_data["speed"] = speed_val
            sensor_data["c_range"] = c_range_val

        await asyncio.sleep(0.01)


async def peripheral_task():
    global _authorized_peer

    while True:
        try:
            # Advertise so phone can see "EBikeSensor"
            async with await aioble.advertise(
                interval_us=_ADV_INTERVAL_US,
                name="EBikeSensor",
                services=[_BAT_SERV_UUID],
                appearance=_ADV_APPEARANCE_GENERIC_SENSOR,
            ) as connection:
                dev = connection.device
                peer = _format_peer(dev)
                print("Incoming connection from:", peer)

                # First ever connection → treat as owner
                if _authorized_peer is None:
                    _authorized_peer = peer
                    print("Authorized device set to:", _authorized_peer)
                else:
                    # Already have an owner: only allow that one
                    if peer != _authorized_peer:
                        print("Unauthorized device, disconnecting.")
                        await connection.disconnect()
                        await asyncio.sleep_ms(100)
                        continue

                print("Authorized device connected, awaiting disconnect...")
                await connection.disconnected()
                print("Authorized device disconnected.")

        except Exception as exc:
            print("BLE peripheral error:", exc)
       
       # Global variable updated by BLE writes
        rx_value = None  


        # Small pause before re-advertising
        await asyncio.sleep_ms(100)

