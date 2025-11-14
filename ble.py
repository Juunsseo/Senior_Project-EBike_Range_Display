from micropython import const
import asyncio
import aioble
import bluetooth
import struct
from machine import I2C, Pin

from ina228 import INA228


# BLE UUIDs
_BAT_SERV_UUID = bluetooth.UUID(0x180F)
_VOLTAGE_UUID = bluetooth.UUID(0x2B18)
_CURRENT_UUID = bluetooth.UUID(0x2704)
_POWER_UUID = bluetooth.UUID(0x2726)
_BATTERY_LEVEL_UUID = bluetooth.UUID(0x2A19)
_TEMPERATURE_UUID = bluetooth.UUID(0x2A6E)


# Advertising configuration
_ADV_APPEARANCE_GENERIC_THERMOMETER = const(768)
_ADV_INTERVAL_US = const(250_000)


# Battery level estimation (adjust the values to match your pack)
_BATTERY_MIN_VOLTAGE = 36.0
_BATTERY_MAX_VOLTAGE = 54.0


# INA228 setup (matches the main application)
_I2C = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
_INA = INA228(i2c=_I2C, address=0x40, shunt_ohms=0.015)
_INA.configure()


# Register the battery service and characteristics
battery_service = aioble.Service(_BAT_SERV_UUID)
voltage_characteristic = aioble.Characteristic(
    battery_service, _VOLTAGE_UUID, read=True, notify=True
)
current_characteristic = aioble.Characteristic(
    battery_service, _CURRENT_UUID, read=True, notify=True
)
power_characteristic = aioble.Characteristic(
    battery_service, _POWER_UUID, read=True, notify=True
)
battery_level_characteristic = aioble.Characteristic(
    battery_service, _BATTERY_LEVEL_UUID, read=True, notify=True
)
temperature_characteristic = aioble.Characteristic(
    battery_service, _TEMPERATURE_UUID, read=True, notify=True
)
aioble.register_services(battery_service)


def _encode_temperature(temp_deg_c: float) -> bytes:
    """Temperature characteristic uses sint16 in hundredths of a degree."""

    scaled = int(round(temp_deg_c * 100))
    scaled = max(min(scaled, 0x7FFF), -0x8000)
    return struct.pack("<h", scaled)


def _encode_float(value: float) -> bytes:
    return struct.pack("<f", float(value))


def _estimate_battery_level(voltage: float) -> int:
    span = _BATTERY_MAX_VOLTAGE - _BATTERY_MIN_VOLTAGE
    if span <= 0:
        return 0
    level = int(round((voltage - _BATTERY_MIN_VOLTAGE) / span * 100))
    return max(0, min(100, level))


async def sensor_task():
    while True:
        try:
            vbus = _INA.get_vbus_voltage()
            current = _INA.get_current()
            power = _INA.get_power()
        except Exception as exc:  # keep the loop alive on transient I2C errors
            print("INA228 read error:", exc)
            await asyncio.sleep_ms(500)
            continue

        battery_level = _estimate_battery_level(vbus)
        try:
            temperature = _INA.get_temperature()
        except Exception as exc:
            print("INA228 temperature read error:", exc)
            temperature = 0.0

        voltage_characteristic.write(_encode_float(vbus), send_update=True)
        current_characteristic.write(_encode_float(current), send_update=True)
        power_characteristic.write(_encode_float(power), send_update=True)
        battery_level_characteristic.write(
            struct.pack("B", battery_level), send_update=True
        )
        temperature_characteristic.write(
            _encode_temperature(temperature), send_update=True
        )

        print(
            "V={:.3f}V I={:.3f}A P={:.3f}W Level={} Temp={:.2f}C".format(
                vbus, current, power, battery_level, temperature
            )
        )
        await asyncio.sleep_ms(1000)


async def peripheral_task():
    while True:
        try:
            async with await aioble.advertise(
                interval_us=_ADV_INTERVAL_US,
                name="RPi-Pico",
                services=[_BAT_SERV_UUID],
                appearance=_ADV_APPEARANCE_GENERIC_THERMOMETER,
            ) as connection:
                print("Connection from", connection.device)
                await connection.disconnected()
        except asyncio.CancelledError:
            print("Peripheral task cancelled")
        except Exception as exc:
            print("Error in peripheral_task:", exc)
        finally:
            await asyncio.sleep_ms(100)


async def main():
    t1 = asyncio.create_task(sensor_task())
    t2 = asyncio.create_task(peripheral_task())
    await asyncio.gather(t1, t2)


asyncio.run(main())
