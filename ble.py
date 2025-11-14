from micropython import const
import asyncio
import aioble
import bluetooth
import struct
from machine import I2C, Pin
from ina228 import INA228

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

# =========================================================
# Advertising config
# =========================================================

_ADV_APPEARANCE_GENERIC_SENSOR = const(1344)
_ADV_INTERVAL_US = const(250_000)

# Battery level estimation (adjust for your pack)
_BATTERY_MIN_VOLTAGE = 36.0
_BATTERY_MAX_VOLTAGE = 54.0

# =========================================================
# INA228 Setup
# =========================================================

_I2C = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
_INA = INA228(i2c=_I2C, address=0x40, shunt_ohms=0.015)
_INA.configure()

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

aioble.register_services(battery_service)

# =========================================================
# Battery Level Estimation
# =========================================================

def estimate_battery_level(voltage: float) -> int:
    span = _BATTERY_MAX_VOLTAGE - _BATTERY_MIN_VOLTAGE
    if span <= 0:
        return 0
    level = int(round((voltage - _BATTERY_MIN_VOLTAGE) / span * 100))
    return max(0, min(100, level))

# =========================================================
# SENSOR TASK — Standard SIG Formats
# =========================================================

async def sensor_task():
    while True:
        try:
            vbus = _INA.get_vbus_voltage()       # Volts
            current = _INA.get_current()         # Amps
            power = _INA.get_power()             # Watts
            temperature = _INA.get_temp_voltage()  # °C
        except Exception as exc:
            print("INA228 read error:", exc)
            await asyncio.sleep_ms(500)
            continue

        # ---------------------------------------------------------------------
        # Standard Bluetooth SIG Encodings
        # ---------------------------------------------------------------------

        # VOLTAGE (0x2B18) — uint16, unit: mV
        voltage_mv = int(vbus * 1000)
        voltage_ch.write(struct.pack("<H", voltage_mv), send_update=True)

        # CURRENT (0x2704) — sint16, unit: mA
        current_ma = int(current * 1000)
        current_ch.write(struct.pack("<h", current_ma), send_update=True)

        # POWER (0x2726) — uint16, unit: watt
        power_w = int(power)
        power_ch.write(struct.pack("<H", power_w), send_update=True)

        # TEMPERATURE (0x2A6E) — sint16, unit: 0.01 °C
        temp_hundredths = int(temperature * 100)
        temperature_ch.write(struct.pack("<h", temp_hundredths), send_update=True)

        # BATTERY LEVEL (0x2A19) — uint8, %
        battery_level = estimate_battery_level(vbus)
        battery_ch.write(struct.pack("B", battery_level), send_update=True)

        # Debug print
        print(
            "V={:.4f}V  I={:.4f}A  P={:.3f}W  Temp={:.2f}C  Batt={}%"\
            .format(vbus, current, power, temperature, battery_level)
        )

        await asyncio.sleep_ms(1000)

# =========================================================
# BLE Peripheral — Advertising / Connections
# =========================================================

async def peripheral_task():
    while True:
        try:
            async with await aioble.advertise(
                interval_us=_ADV_INTERVAL_US,
                name="EBikeSensor",
                services=[_BAT_SERV_UUID],
                appearance=_ADV_APPEARANCE_GENERIC_SENSOR,
            ) as connection:
                print("Connection from:", connection.device)
                await connection.disconnected()
                print("Disconnected")
        except Exception as exc:
            print("BLE error:", exc)
        finally:
            await asyncio.sleep_ms(100)

# =========================================================
# MAIN
# =========================================================

async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(peripheral_task())
    await asyncio.gather(t1, t2)

asyncio.run(main())
