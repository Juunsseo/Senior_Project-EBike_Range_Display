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
ina = INA228(i2c, address=0x40, shunt_ohms=0.003, max_expected_current_a=25, adcrange=0)

ina.configure()


# =========================================================
# Battery % helper
# =========================================================
def estimate_battery(voltage): #depends on battery
    MIN = 43.0
    MAX = 53.0
    percent = int((voltage - MIN) / (MAX - MIN) * 100)
    return max(0, min(100, percent))


# =========================================================
# SENSOR POLLING
# =========================================================
async def sensor_poll_task():
    while True:
        v = ina.get_bus_voltage_v()
        c = ina.get_current_a()
        p = ina.get_power_w()
        t = ina.get_die_temp_c()
        batt = estimate_battery(v)

        # Update BLE
        ble_update(v, c, p, t, batt)

        # Update display data
        sensor_data["voltage"] = v
        sensor_data["current"] = c * 1000
        sensor_data["power"] = p
        sensor_data["battery"] = batt

        print(f"V={v:.3f}V I={c:.3f}A P={p:.2f}W")
        if rx_value is not None:
            num = int(rx_value.decode())
            print("Phone sent:", num)


        await asyncio.sleep(0.1)
#Testing
def dbg_dump(ina):
    # raw reads
    cfg = ina.read_register16(ina.REG_CONFIG)
    adc = ina.read_register16(ina.REG_ADC_CONFIG)
    shcal = ina.read_register16(ina.REG_SHUNT_CAL)
    vsh_raw24 = ina.read_register24(ina.REG_VSHUNT)
    cur_raw24 = ina.read_register24(ina.REG_CURRENT)
    pwr_raw24 = ina.read_register24(ina.REG_POWER)

    # extract 20-bit fields (bits 23-4)
    vsh20 = vsh_raw24 >> 4
    cur20 = cur_raw24 >> 4

    # signed convert
    if vsh20 & (1 << 19): vsh20 -= (1 << 20)
    if cur20 & (1 << 19): cur20 -= (1 << 20)

    # compute vshunt using datasheet LSB
    adcrange = (cfg >> 4) & 1
    vsh_lsb = 312.5e-9 if adcrange == 0 else 78.125e-9  # Table 7-9 :contentReference[oaicite:8]{index=8}
    vsh_v = vsh20 * vsh_lsb

    print("CONFIG=0x%04X ADCRANGE=%d" % (cfg, adcrange))
    print("ADC_CONFIG=0x%04X" % adc)
    print("SHUNT_CAL=0x%04X (%d)" % (shcal, shcal))
    print("VSHUNT raw24=0x%06X raw20=%d  -> %.6f V (expect ~0.030V @10A,3mΩ)" % (vsh_raw24, vsh20, vsh_v))
    print("CURRENT raw24=0x%06X raw20=%d" % (cur_raw24, cur20))
    print("POWER raw24=0x%06X (%d)" % (pwr_raw24, pwr_raw24))
    
    cfg = ina.read_register16(ina.REG_CONFIG)
    
    shcal = ina.read_register16(ina.REG_SHUNT_CAL)
    vsh = ina.read_register24(ina.REG_VSHUNT)
    cur = ina.read_register24(ina.REG_CURRENT)
    pwr = ina.read_register24(ina.REG_POWER)

    print("CONFIG:", hex(cfg), "SHUNT_CAL:", hex(shcal))
    print("VSHUNT raw24:", hex(vsh))
    print("CURRENT raw24:", hex(cur))
    print("POWER raw24:", hex(pwr))

    vsh = ina.get_shunt_voltage_v()
    ibus_from_vsh = vsh / 0.003
    ibus_from_cur = ina.get_current_a()

    print("VSHUNT(V):", vsh)
    print("I from VSHUNT/R:", ibus_from_vsh)
    print("I from CURRENT reg:", ibus_from_cur)
    print("VBUS:", ina.get_bus_voltage_v())
    print("P from reg:", ina.get_power_w())
    print("P calc:", ina.get_bus_voltage_v() * ibus_from_cur)

# =========================================================
# MAIN EVENT LOOP
# =========================================================
async def main():
    await asyncio.gather(
        sensor_poll_task(),
        peripheral_task(),
        #display_task(),
        rx_task(),
        # <-- new

    )
#Debugging Function
#dbg_dump(ina)


asyncio.run(main())
