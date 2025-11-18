# display.py
import uasyncio as asyncio
from epaper_driver import EPD_3in7
import framebuf

# Shared data structure, updated by main.py
sensor_data = {
    "voltage": 0.0,
    "current": 0.0,
    "power": 0.0,
    "pas": "",    # pedal-assist / incoming short text
    "speed": 0.0,  # km/h (float)
    "c_range": 0.0, # calculated range (km)

}

def draw_big_text(fb, text, x, y, color=0x00, scale=3):
    tmp = framebuf.FrameBuffer(bytearray(8 * 8 // 8), 8, 8, framebuf.MONO_HLSB)

    for idx, ch in enumerate(text):
        tmp.fill(1)
        tmp.text(ch, 0, 0, 0)

        for yy in range(8):
            for xx in range(8):
                if tmp.pixel(xx, yy) == 0:
                    for dy in range(scale):
                        for dx in range(scale):
                            fb.pixel(
                                x + idx * 8 * scale + xx * scale + dx,
                                y + yy * scale + dy,
                                color
                            )

# E-ink initialization
epd = EPD_3in7()
epd.EPD_3IN7_1Gray_init()
epd.EPD_3IN7_1Gray_Clear()


async def display_task():
    """Updates e-ink display using the shared sensor_data."""
    while True:
        v = sensor_data["voltage"]
        c = sensor_data["current"]
        p = sensor_data["power"]
        pas = sensor_data.get("pas", "")
        speed = sensor_data.get("speed", 0.0)
        c_range = sensor_data.get("c_range", 0.0)

        epd.image1Gray.fill(0xFF)

        draw_big_text(epd.image1Gray, "Battery Monitor", 20, 20, epd.black, 2)
        draw_big_text(epd.image1Gray, f"V: {v:.3f}V", 10, 90, epd.black, 3)
        draw_big_text(epd.image1Gray, f"I: {c:.3f}mA", 10, 140, epd.black, 2)
        draw_big_text(epd.image1Gray, f"P: {p:.3f}W", 10, 190, epd.black, 3)
        draw_big_text(epd.image1Gray, f"PAS: {pas}", 10, 240, epd.black, 2)
        draw_big_text(epd.image1Gray, f"SPD: {speed:.1f}km/h", 10, 280, epd.black, 2)
        draw_big_text(epd.image1Gray, f"RNG: {c_range:.1f}km", 10, 320, epd.black, 2)


        epd.EPD_3IN7_1Gray_Display_Part(epd.buffer_1Gray)

        await asyncio.sleep(1)   # update every 1 sec

