import _thread
import uasyncio as asyncio
import utime
from machine import I2C, Pin

import ble as ble_module
from ble import ble_update, peripheral_task
from display import epd, render_dashboard
from ina228 import INA228


# =========================================================
# INA228 SETUP
# =========================================================
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
ina = INA228(i2c, address=0x40, shunt_ohms=0.003, max_expected_current_a=25, adcrange=0)
ina.configure()


# =========================================================
# Shared display state (protected across cores)
# =========================================================
_display_lock = _thread.allocate_lock()
_display_state = {
    "voltage": 0.0,
    "current": 0.0,
    "power": 0.0,
    "pas": "",
    "speed": 0.0,
    "c_range": 0.0,
    "dist": 0.0,
    "battery": 0.0,
    "connected": False,
}


def _display_update(**kwargs):
    with _display_lock:
        for key, value in kwargs.items():
            _display_state[key] = value


def _display_snapshot():
    with _display_lock:
        return dict(_display_state)


# =========================================================
# Battery % helper
# =========================================================
def estimate_battery(voltage):
    min_v = 43.0
    max_v = 53.0
    percent = int((voltage - min_v) / (max_v - min_v) * 100)
    return max(0, min(100, percent))


# =========================================================
# Core 1 display worker (blocking e-paper calls stay off main loop)
# =========================================================
def display_worker():
    while True:
        snap = _display_snapshot()
        epd.image1Gray.fill(0xFF)
        render_dashboard(epd.image1Gray, snap)
        epd.EPD_3IN7_1Gray_Display_Part(epd.buffer_1Gray)
        utime.sleep_ms(1000)


# =========================================================
# SENSOR POLLING (core 0, asyncio)
# =========================================================
async def sensor_poll_task():
    while True:
        v = ina.get_bus_voltage_v()
        c = ina.get_current_a()
        p = ina.get_power_w()
        t = ina.get_die_temp_c()
        batt = estimate_battery(v)

        ble_update(v, c, p, t, batt)

        _display_update(
            voltage=v,
            current=c * 1000,
            power=p,
            battery=batt,
            connected=bool(ble_module.sensor_data.get("connected")),
        )

        print("V={:.3f}V I={:.3f}A P={:.2f}W".format(v, c, p))
        await asyncio.sleep(0.1)


# =========================================================
# RX task mirrored locally (replaces ble.rx_task)
# =========================================================
async def rx_task_new():
    while True:
        await ble_module.rx_ch.written()
        data = ble_module.rx_ch.read()

        if isinstance(data, (bytes, bytearray)):
            ble_module.rx_value = data
            text = data.decode("utf-8", "ignore").strip()
            print("RX DATA =", text)

            def parse_float(token):
                try:
                    return float(token)
                except Exception:
                    return 0.0

            pas_val = ""
            speed_val = 0.0
            c_range_val = 0.0
            dist_val = 0.0

            if text:
                parts = [p.strip() for p in text.split(",")]
                if len(parts) >= 1:
                    pas_val = parts[0]
                if len(parts) >= 2:
                    speed_val = parse_float(parts[1])
                if len(parts) >= 3:
                    c_range_val = parse_float(parts[2])
                if len(parts) >= 4:
                    dist_val = parse_float(parts[3])

            _display_update(
                pas=pas_val,
                speed=speed_val,
                c_range=c_range_val,
                dist=dist_val,
            )

        await asyncio.sleep(0.1)


# =========================================================
# MAIN
# =========================================================
async def main():
    _thread.start_new_thread(display_worker, ())
    await asyncio.gather(
        sensor_poll_task(),
        peripheral_task(),
        rx_task_new(),
    )


asyncio.run(main())
