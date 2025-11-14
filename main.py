from machine import I2C, Pin
import time
from ina228 import INA228
from epaper_driver import EPD_3in7   # rename your e-ink file to Pico_ePaper_3in7.py



# ======== INA228 Setup ========
i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
ina = INA228(i2c=i2c, address=0x40, shunt_ohms=0.015)
ina.reset_all()
time.sleep_ms(3)
ina.set_config()
ina.set_adc_config()
ina.shunt_calib()
ina.shunt_tempco()

# ==============================================================
# BIG TEXT SCALING — works with any Waveshare e-paper FrameBuffer
# ==============================================================
import framebuf

def draw_big_text(fb, text, x, y, color=0x00, scale=3):
    """Render larger text by scaling MicroPython's 8×8 built-in font."""
    temp_fb = framebuf.FrameBuffer(bytearray(8 * 8 // 8), 8, 8, framebuf.MONO_HLSB)

    for idx, ch in enumerate(text):
        temp_fb.fill(1)                # white bg
        temp_fb.text(ch, 0, 0, 0)      # draw small glyph in black

        # scale each pixel
        for yy in range(8):
            for xx in range(8):
                if temp_fb.pixel(xx, yy) == 0:  # black pixel
                    for dy in range(scale):
                        for dx in range(scale):
                            fb.pixel(
                                x + idx * 8 * scale + xx * scale + dx,
                                y + yy * scale + dy,
                                color
                            )



# ======== E-ink Setup ========
epd = EPD_3in7()
epd.image1Gray.fill(0xff)  # White
epd.EPD_3IN7_1Gray_init()
epd.EPD_3IN7_1Gray_Clear()

# ======== Timers ========
last_display = time.ticks_ms()
display_interval = 1000  # update every 5 seconds

while True:
    vbus   = ina.get_vbus_voltage()
    vshunt = ina.get_shunt_voltage() * 1e3
    curr   = ina.get_current() * 1e3
    pwr    = ina.get_power()

    print("V=%.5fV I=%.5fmA P=%.5fW" % (vbus, curr, pwr))

    if time.ticks_diff(time.ticks_ms(), last_display) > display_interval:
        last_display = time.ticks_ms()

        epd.image1Gray.fill(0xff)  # clear

        # --- Bigger text with scaling ---
        draw_big_text(epd.image1Gray, "Battery Monitor", 20, 20, epd.black, scale=2)
        draw_big_text(epd.image1Gray, "V: %.4fV" % vbus, 10, 90, epd.black, scale=3)
        draw_big_text(epd.image1Gray, "I: %.5fmA" % curr, 10, 140, epd.black, scale=2)
        draw_big_text(epd.image1Gray, "P: %.4fW" % pwr, 10, 190, epd.black, scale=3)

        epd.EPD_3IN7_1Gray_Display_Part(epd.buffer_1Gray)

    time.sleep(0.5)
