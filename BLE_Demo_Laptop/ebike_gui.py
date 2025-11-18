import asyncio
import threading
from bleak import BleakScanner, BleakClient
import pygame
import sys

# ---------- BLE UUIDs (must match Pico firmware) ----------
SERVICE_UUID       = "0000180F-0000-1000-8000-00805F9B34FB"
VOLTAGE_UUID       = "00002B18-0000-1000-8000-00805F9B34FB"
CURRENT_UUID       = "00002704-0000-1000-8000-00805F9B34FB"
POWER_UUID         = "00002726-0000-1000-8000-00805F9B34FB"
BATTERY_UUID       = "00002A19-0000-1000-8000-00805F9B34FB"
TEMP_UUID          = "00002A6E-0000-1000-8000-00805F9B34FB"

RX_UUID            = "12345678-1234-5678-1234-56789abcdef0"
TARGET_NAME        = "EBikeSensor"

# ---------- Shared state between BLE thread and Pygame ----------
sensor_state = {
    "voltage": None,
    "current": None,
    "power": None,
    "battery": None,
    "temp": None,
}

status_text = "Idle"
tx_buffer = ""          # text the user is typing to send to Pico
client = None           # BleakClient instance (set by BLE thread)
loop = asyncio.new_event_loop()  # BLE event loop (background thread)


def set_status(msg: str):
    global status_text
    print("[STATUS]", msg)
    status_text = msg


# ---------- Decode helpers ----------
def decode_voltage(b): return int.from_bytes(b, "little")
def decode_current(b): return int.from_bytes(b, "little", signed=True)
def decode_power(b):   return int.from_bytes(b, "little")
def decode_battery(b): return b[0]
def decode_temp(b):    return int.from_bytes(b, "little", signed=True) / 100.0


# ---------- BLE worker (runs in background thread) ----------
async def ble_worker():
    global client

    while True:
        set_status("Scanning for EBikeSensor...")

        device = await BleakScanner.find_device_by_filter(
            lambda d, ad: d.name and TARGET_NAME in d.name
        )

        if not device:
            set_status("Device NOT found. Retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue
        break

    set_status(f"Connecting to {device.address}...")
    client = BleakClient(device.address)
    await client.connect()
    set_status("Connected. Receiving data...")

    # Notification handlers (called in BLE thread)
    def voltage_handler(sender, data):
        sensor_state["voltage"] = decode_voltage(data)

    def current_handler(sender, data):
        sensor_state["current"] = decode_current(data)

    def power_handler(sender, data):
        sensor_state["power"] = decode_power(data)

    def battery_handler(sender, data):
        sensor_state["battery"] = decode_battery(data)

    def temp_handler(sender, data):
        sensor_state["temp"] = decode_temp(data)

    # Subscribe to notifications
    await client.start_notify(VOLTAGE_UUID, voltage_handler)
    await client.start_notify(CURRENT_UUID, current_handler)
    await client.start_notify(POWER_UUID,   power_handler)
    await client.start_notify(BATTERY_UUID, battery_handler)
    await client.start_notify(TEMP_UUID,    temp_handler)

    # Keep BLE alive
    while True:
        await asyncio.sleep(1)


def ble_thread_main():
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(ble_worker())
    except Exception as e:
        set_status(f"BLE error: {e}")


# ---------- Pygame UI ----------
pygame.init()
WIDTH, HEIGHT = 800, 480
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("E-Bike BLE Monitor")

FONT_BIG = pygame.font.SysFont("Arial", 36)
FONT_MED = pygame.font.SysFont("Arial", 28)
FONT_SMALL = pygame.font.SysFont("Arial", 22)

clock = pygame.time.Clock()


def draw_text(surface, text, x, y, font, color=(255, 255, 255)):
    img = font.render(text, True, color)
    surface.blit(img, (x, y))


def format_value(name, value, unit=""):
    if value is None:
        return f"{name}: ---"
    return f"{name}: {value:.3f} {unit}" if isinstance(value, float) else f"{name}: {value} {unit}"


# Start BLE thread
threading.Thread(target=ble_thread_main, daemon=True).start()


# ---------- Main Pygame loop ----------
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            # Text input
            if event.key == pygame.K_RETURN:
                # Send tx_buffer to Pico
                if client is not None and tx_buffer:
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            client.write_gatt_char(RX_UUID, tx_buffer.encode()),
                            loop
                        )
                        # ignore result; fire-and-forget
                        set_status(f"Sent: {tx_buffer}")
                        tx_buffer = ""
                    except Exception as e:
                        set_status(f"Send error: {e}")
                else:
                    set_status("Not connected or empty message")
            elif event.key == pygame.K_BACKSPACE:
                tx_buffer = tx_buffer[:-1]
            else:
                # Add character to buffer (basic ASCII only)
                if event.unicode.isprintable():
                    tx_buffer += event.unicode

    # Clear screen
    screen.fill((20, 20, 20))

    # Status line
    draw_text(screen, f"Status: {status_text}", 20, 20, FONT_SMALL, (0, 200, 255))

    # Sensor readings
    y0 = 80
    dy = 50

    draw_text(
        screen,
        format_value("Voltage", sensor_state["voltage"], "V"),
        20, y0,
        FONT_MED
    )
    draw_text(
        screen,
        format_value("Current", sensor_state["current"], "mA"),
        20, y0 + dy,
        FONT_MED
    )
    draw_text(
        screen,
        format_value("Power", sensor_state["power"], "W"),
        20, y0 + 2 * dy,
        FONT_MED
    )
    draw_text(
        screen,
        format_value("Battery", sensor_state["battery"], "%"),
        20, y0 + 3 * dy,
        FONT_MED
    )
    draw_text(
        screen,
        format_value("Temp", sensor_state["temp"], "°C"),
        20, y0 + 4 * dy,
        FONT_MED
    )

    # TX input line
    draw_text(screen, "Type message and press Enter to send to Pico:", 20, HEIGHT - 90, FONT_SMALL)
    draw_text(screen, tx_buffer + "|", 20, HEIGHT - 60, FONT_SMALL, (0, 255, 0))

    pygame.display.flip()
    clock.tick(30)

pygame.quit()
sys.exit()
