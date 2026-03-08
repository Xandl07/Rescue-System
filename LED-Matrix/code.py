import time
import gc
import displayio
import terminalio
from adafruit_display_text import label
from adafruit_matrixportal.matrix import Matrix
import adafruit_imageload
import usb_cdc
import supervisor

supervisor.runtime.autoreload = False

displayio.release_displays()
matrix = Matrix(width=64, height=32)
display = matrix.display

root_ready = displayio.Group()
display.root_group = root_ready

status = label.Label(terminalio.FONT, text="READY", color=0x00FF00)
status.x = 1
status.y = 7
root_ready.append(status)

sub = label.Label(terminalio.FONT, text="WAITING", color=0x00FF00)
sub.x = 1
sub.y = 18
root_ready.append(sub)

scroll = label.Label(terminalio.FONT, text="", color=0xFFFFFF)
scroll.y = 16
root_ready.append(scroll)

def log_line(s: str):
    try:
        with open("/rx_log.txt", "a") as f:
            f.write(s + "\n")
    except Exception:
        pass

_scroll_text = ""
_scroll_x = display.width
_last_scroll = 0.0

def set_scroll(msg: str, color=0xFFFFFF):
    global _scroll_text, _scroll_x
    if msg is None:
        msg = ""
    if len(msg) > 200:
        msg = msg[:200] + "..."
    _scroll_text = msg
    scroll.text = _scroll_text
    scroll.color = color
    _scroll_x = display.width
    scroll.x = _scroll_x

def tick_scroll():
    global _scroll_x, _last_scroll
    if not _scroll_text:
        return
    now = time.monotonic()
    if now - _last_scroll < 0.03:
        return
    _last_scroll = now
    _scroll_x -= 1
    scroll.x = _scroll_x
    w = scroll.bounding_box[2]
    if _scroll_x < -w:
        _scroll_x = display.width

def show_error(e: Exception):
    lineno = None
    try:
        tb = e.__traceback__
        while tb and tb.tb_next:
            tb = tb.tb_next
        if tb:
            lineno = tb.tb_lineno
    except Exception:
        lineno = None

    try:
        emsg = repr(e)
    except Exception:
        emsg = str(type(e))

    if lineno is None:
        out = f"ERR {type(e).__name__} {emsg}"
    else:
        out = f"ERR L{lineno} {type(e).__name__} {emsg}"

    status.text = "ERR"
    status.color = 0xFF0000
    display.root_group = root_ready
    set_scroll(out, 0xFF0000)
    log_line(out)

# Ambu preload
ambu_group = None
try:
    bmp, pal = adafruit_imageload.load(
        "/ambu.bmp",
        bitmap=displayio.Bitmap,
        palette=displayio.Palette
    )
    ambu_group = displayio.Group()
    ambu_tile = displayio.TileGrid(
        bmp,
        pixel_shader=pal,
        x=(display.width - bmp.width) // 2,
        y=(display.height - bmp.height) // 2
    )
    ambu_group.append(ambu_tile)
    log_line("AMBU preload OK")
except Exception as e:
    show_error(e)
    log_line("AMBU preload FAILED")

# Party preload
party_group = None
party_grid = None
party_frame = 0
party_last = 0.0
PARTY_DT = 0.1 

try:
    p_bmp, p_pal = adafruit_imageload.load(
        "/partyParrotsTweet.bmp",
        bitmap=displayio.Bitmap,
        palette=displayio.Palette
    )
    party_group = displayio.Group()
    party_grid = displayio.TileGrid(
        p_bmp,
        pixel_shader=p_pal,
        width=1,
        height=1,
        tile_width=32,
        tile_height=32,
        x=16,
        y=0
    )
    party_group.append(party_grid)
    log_line("PARTY preload OK")
except Exception as e:
    show_error(e)
    log_line("PARTY preload FAILED")

# Custom load
custom_group = None

def load_custom():
    global custom_group
    try:
        bmp, pal = adafruit_imageload.load(
            "/custom.bmp",
            bitmap=displayio.Bitmap,
            palette=displayio.Palette
        )
        g = displayio.Group()
        t = displayio.TileGrid(
            bmp, pixel_shader=pal,
            x=(display.width - bmp.width)//2,
            y=(display.height - bmp.height)//2
        )
        g.append(t)
        custom_group = g
        return True
    except Exception as e:
        show_error(e)
        return False

# Serial Read
buf = bytearray()
MAX_LINE = 220

def read1_data():
    d = None
    try:
        d = usb_cdc.data
    except Exception:
        d = None
    if not d:
        return None
    try:
        if d.in_waiting:
            b = d.read(1)
            if b:
                return b[0]  
    except Exception:
        return None
    return None

# modes
mode = "READY" 

def switch_to_ready(msg="WAITING"):
    global mode
    mode = "READY"
    display.root_group = root_ready
    status.text = "READY"
    status.color = 0x00FF00
    sub.text = msg
    sub.color = 0x00FF00
    set_scroll("", 0xFFFFFF)  

def switch_to_custom():
    global mode, custom_group
    mode = "CUSTOM"

    display.root_group = root_ready
    status.text = "CUSTOM"
    sub.text = "LOADING..."
    set_scroll("")

    custom_group = None
    gc.collect()

    if load_custom() and custom_group:
        display.root_group = custom_group
    else:
        switch_to_ready("CUSTOM not loaded!")

def switch_to_ambu():
    global mode
    mode = "AMBU"
    if ambu_group:
        display.root_group = ambu_group
        log_line("SWITCH -> AMBU")
    else:
        switch_to_ready("AMBU not loaded!")

def switch_to_party():
    global mode, party_frame, party_last
    mode = "PARTY"
    if party_group and party_grid:
        party_frame = 0
        party_grid[0] = party_frame
        party_last = time.monotonic()
        display.root_group = party_group
        log_line("SWITCH -> PARTY")
    else:
        switch_to_ready("PARTY not loaded!")

def switch_to_text(text):
    global mode
    mode = "TEXT"
    display.root_group = root_ready
    status.text = ""        
    sub.text = ""           
    set_scroll(text, 0xFFFFFF)
    log_line("SWITCH -> TEXT")

switch_to_ready("WAITING")

while True:
    try:
        if mode == "PARTY" and party_grid:
            now = time.monotonic()
            if now - party_last >= PARTY_DT:
                party_last = now
                party_frame = (party_frame + 1) % 10
                party_grid[0] = party_frame

        if mode in ("READY", "TEXT"):
            tick_scroll()

        b = read1_data()
        if b is None:
            time.sleep(0.002)
            continue

        if b == 10: 
            line = bytes(buf).decode("utf-8", "ignore").strip()
            buf[:] = b""  

            if line:
                log_line("RX: " + line)
                if mode in ("READY", "TEXT"):
                    set_scroll("RX: " + line, 0xFFFFFF)

            u = line.upper()

            if u == "AMBU" or u.startswith("MODE:AMBU"):
                switch_to_ambu()

            elif u.startswith("MODE:CUSTOM"):
                switch_to_custom()

            elif u.startswith("MODE:PARTY"):
                switch_to_party()

            elif u.startswith("MODE:NOTHING") or u.startswith("MODE:READY"):
                switch_to_ready("WAITING")

            elif u.startswith("TEXT:"):
                txt = line[5:] if len(line) > 5 else ""
                switch_to_text(txt)

            else:
                if mode in ("READY", "TEXT"):
                    set_scroll("UNKNOWN: " + line, 0xFF0000)

        elif b == 13:
            pass
        else:
            if len(buf) < MAX_LINE:
                buf.append(b)
            else:
                buf[:] = b""
                if mode in ("READY", "TEXT"):
                    status.text = "OVF"
                    status.color = 0xFF0000
                    set_scroll("ERR:OVF line too long", 0xFF0000)
                log_line("ERR:OVF line too long")

    except Exception as e:
        show_error(e)
        time.sleep(0.2)