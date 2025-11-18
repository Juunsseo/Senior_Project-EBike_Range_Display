# main.py
import uasyncio as asyncio
from machine import I2C, Pin
from ina228 import INA228

from ble import ble_update, peripheral_task
from display import sensor_data, display_task
from ble import rx_value
from ble import rx_task




# =========================================================
# INA228 SETUP
# =========================================================
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)

ina = INA228(i2c=i2c, address=0x40, shunt_ohms=0.015)
ina.reset_all()
ina.set_config()
ina.set_adc_config()
ina.shunt_calib()
ina.shunt_tempco()


# =========================================================
# Battery % helper
# =========================================================
def estimate_battery(voltage):
    MIN = 36.0
    MAX = 54.0
    percent = int((voltage - MIN) / (MAX - MIN) * 100)
    return max(0, min(100, percent))


# =========================================================
# SENSOR POLLING
# =========================================================
async def sensor_poll_task():
    while True:
        v = ina.get_vbus_voltage()
        c = ina.get_current()
        p = ina.get_power()
        t = ina.get_temp_voltage()
        batt = estimate_battery(v)

        # Update BLE
        ble_update(v, c * 1000, p, t, batt)

        # Update display data
        sensor_data["voltage"] = v
        sensor_data["current"] = c * 1000
        sensor_data["power"] = p

        print(f"V={v:.3f}V I={c:.3f}A P={p:.2f}W")
        if rx_value is not None:
            num = int(rx_value.decode())
            print("Phone sent:", num)


        await asyncio.sleep(1)


# =========================================================
# MAIN EVENT LOOP
# =========================================================
async def main():
    await asyncio.gather(
        sensor_poll_task(),
        peripheral_task(),
        display_task(),
        rx_task(),          # <-- new

    )


asyncio.run(main())

