"""Draws the ESP32-C3 Super Mini tracker wiring schematic (SVG + PNG)."""
import sys
import cairosvg

out_svg, out_png = sys.argv[1], sys.argv[2]
W, H = 1560, 1120
el = []
FONT = "DejaVu Sans"
RED, ORG, BLU, GRN, PUR, BLK, GRY = "#c62828", "#e65100", "#1565c0", "#2e7d32", "#6a1b9a", "#111", "#666"


def ln(pts, c=BLK, w=3):
    el.append(f'<polyline points="{" ".join(f"{x},{y}" for x, y in pts)}" fill="none" stroke="{c}" stroke-width="{w}" stroke-linejoin="round"/>')


def tx(x, y, s, size=18, c=BLK, anchor="start", bold=False):
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    el.append(f'<text x="{x}" y="{y}" font-family="{FONT}" font-size="{size}" fill="{c}" text-anchor="{anchor}"'
              f'{" font-weight=\"bold\"" if bold else ""}>{s}</text>')


def box(x1, y1, x2, y2, title, c, sub=None):
    el.append(f'<rect x="{x1}" y="{y1}" width="{x2-x1}" height="{y2-y1}" rx="8" fill="{c}" fill-opacity="0.07" stroke="{c}" stroke-width="3"/>')
    tx((x1 + x2) / 2, y1 + 28, title, 20, c, "middle", True)
    if sub:
        tx((x1 + x2) / 2, y1 + 50, sub, 15, GRY, "middle")


def dot(x, y, c=BLK):
    el.append(f'<circle cx="{x}" cy="{y}" r="6" fill="{c}"/>')


def gnd(x, y):                       # ground symbol hanging from (x, y)
    ln([(x, y), (x, y + 14)])
    ln([(x - 16, y + 14), (x + 16, y + 14)])
    ln([(x - 10, y + 21), (x + 10, y + 21)])
    ln([(x - 4, y + 28), (x + 4, y + 28)])


def flag(x, y, name, c, left=False):  # net label
    w = 14 * len(name) + 18
    x2 = x - w if left else x + w
    el.append(f'<rect x="{min(x, x2)}" y="{y-15}" width="{w}" height="30" rx="4" fill="#fff" stroke="{c}" stroke-width="2.5"/>')
    tx((x + x2) / 2, y + 6, name, 17, c, "middle", True)


def res_h(x1, x2, y, label, c=BLK):  # horizontal resistor between x1 and x2
    m, half = (x1 + x2) / 2, 30
    ln([(x1, y), (m - half, y)], c)
    zz = [(m - half, y)] + [(m - half + 7.5 * (i + 1), y + (-10 if i % 2 == 0 else 10)) for i in range(7)] + [(m + half, y)]
    ln(zz, c)
    ln([(m + half, y), (x2, y)], c)
    tx(m, y - 18, label, 16, c, "middle", True)


def res_v(x, y1, y2, label, c=BLK):
    m, half = (y1 + y2) / 2, 30
    ln([(x, y1), (x, m - half)], c)
    zz = [(x, m - half)] + [(x + (-10 if i % 2 == 0 else 10), m - half + 7.5 * (i + 1)) for i in range(7)] + [(x, m + half)]
    ln(zz, c)
    ln([(x, m + half), (x, y2)], c)
    tx(x + 18, m + 6, label, 16, c, "start", True)


def cap_v(x, y_top, label, polar=False):  # capacitor from rail at y_top down to GND
    ln([(x, y_top), (x, y_top + 40)])
    ln([(x - 20, y_top + 40), (x + 20, y_top + 40)], w=4)
    if polar:
        el.append(f'<path d="M {x-20} {y_top+58} Q {x} {y_top+46} {x+20} {y_top+58}" fill="none" stroke="{BLK}" stroke-width="4"/>')
        tx(x - 32, y_top + 38, "+", 18, BLK, "middle", True)
    else:
        ln([(x - 20, y_top + 52), (x + 20, y_top + 52)], w=4)
    ln([(x, y_top + 52), (x, y_top + 90)])
    gnd(x, y_top + 90)
    tx(x, y_top + 140, label, 15, BLK, "middle", True)


def pin(x, y, name, side, c=BLK):   # pin stub + name inside a box edge
    if side == "R":
        ln([(x, y), (x + 30, y)], c)
        tx(x - 8, y + 6, name, 16, c, "end", True)
    else:
        ln([(x - 30, y), (x, y)], c)
        tx(x + 8, y + 6, name, 16, c, "start", True)


el.append(f'<rect width="{W}" height="{H}" fill="#fff"/>')
tx(30, 42, "GSM/GPS Tracker - ESP32-C3 Super Mini wiring (matches carrier PCB v2)", 26, BLK, "start", True)

# ------------------------------------------------------------------ power section
tx(30, 88, "1. Power", 20, GRY, "start", True)
# battery
bx = 90
ln([(bx, 150), (bx, 168)])
ln([(bx - 26, 168), (bx + 26, 168)], w=4)
ln([(bx - 14, 180), (bx + 14, 180)], w=6)
ln([(bx - 26, 192), (bx + 26, 192)], w=4)
ln([(bx - 14, 204), (bx + 14, 204)], w=6)
ln([(bx, 204), (bx, 230)])
gnd(bx, 230)
tx(bx - 40, 165, "+", 20, RED, "middle", True)
tx(bx, 288, "BT1  1S Li-ion", 15, BLK, "middle", True)
tx(bx, 306, "3.7-4.2 V, protected", 14, GRY, "middle")
tx(bx, 324, "via JST J1", 14, GRY, "middle")
# switch
ln([(bx, 150), (bx, 120), (210, 120)], RED)
dot(210, 120, RED)
ln([(210, 120), (262, 100)], RED, 4)
dot(270, 120, RED)
tx(240, 90, "SW1", 15, BLK, "middle", True)
tx(240, 150, "power switch", 14, GRY, "middle")
# VBAT rail
ln([(270, 120), (700, 120)], RED, 4)
dot(370, 120, RED); dot(480, 120, RED)
flag(560, 85, "VBAT", RED)
ln([(560, 100), (560, 120)], RED)
dot(560, 120, RED)
cap_v(370, 120, "C1 1000 uF", True)
cap_v(480, 120, "C2 100 nF")
tx(425, 280, "C1, C2 next to SIM800L VCC", 14, GRY, "middle")
# MT3608
box(700, 85, 900, 255, "U3 MT3608", PUR, "boost -> 5.0 V")
pin(700, 160, "IN+", "L", RED)
pin(700, 215, "IN-", "L")
pin(900, 160, "OUT+", "R", ORG)
pin(900, 215, "OUT-", "R")
ln([(670, 215), (650, 215), (650, 230)])
gnd(650, 230)
ln([(930, 215), (950, 215), (950, 230)])
gnd(950, 230)
tx(800, 244, "set 5.0 V before use!", 14, RED, "middle", True)
ln([(670, 160), (670, 120)], RED)
dot(670, 120, RED)
# +5V rail
ln([(930, 160), (970, 160), (970, 130), (1130, 130)], ORG, 4)
dot(1040, 130, ORG)
cap_v(1040, 130, "C3 100 uF", True)
flag(1130, 130, "+5V", ORG)
tx(1220, 120, "feeds ESP32-C3 5V pin", 14, GRY)
tx(1220, 140, "and GPS VCC", 14, GRY)

# ------------------------------------------------------------------ modules
tx(30, 350, "2. Modules and signals", 20, GRY, "start", True)

# SIM800L
box(110, 420, 330, 800, "U2 SIM800L", RED, "2G GSM/GPRS")
ln([(290, 420), (290, 392)])
ln([(274, 372), (290, 392), (306, 372)], BLK)
ln([(290, 372), (290, 392)])
tx(314, 390, "NET pad: GSM antenna", 14, GRY)
pin(110, 520, "VCC", "L", RED)
flag(80, 520, "VBAT", RED, left=True)
pin(110, 740, "GND", "L")
ln([(80, 740), (60, 740), (60, 760)])
gnd(60, 760)
pin(330, 620, "TXD", "R", BLU)
pin(330, 670, "RXD", "R", BLU)
pin(330, 780, "RST", "R", BLU)
tx(220, 560, "2.8 V logic", 14, GRY, "middle")
tx(220, 580, "RING DTR MIC SPK:", 14, GRY, "middle")
tx(220, 598, "not connected", 14, GRY, "middle")

# GPS
box(110, 860, 330, 1070, "U4 NEO-M8N GPS", GRN, "+ patch antenna (u.FL)")
pin(110, 950, "VCC", "L", ORG)
flag(80, 950, "+5V", ORG, left=True)
pin(110, 1020, "GND", "L")
ln([(80, 1020), (60, 1020), (60, 1035)])
gnd(60, 1035)
pin(330, 930, "TX", "R", GRN)
pin(330, 980, "RX", "R", GRN)

# ESP32-C3 Super Mini
EX = 760
box(EX, 420, 1010, 870, "U1 ESP32-C3", BLU, "Super Mini")
tx(885, 490, "5V/GND/3V3/4..0 row", 13, GRY, "middle")
tx(885, 508, "(RIGHT row, chip up)", 13, GRY, "middle")
for name, y, c in [("5V", 470, ORG), ("GND", 520, BLK), ("3V3", 570, GRY), ("GPIO4", 620, BLU),
                   ("GPIO3", 670, BLU), ("GPIO2", 720, BLU), ("GPIO1", 770, GRN), ("GPIO0", 820, GRN)]:
    pin(EX, y, name, "L", c)
flag(EX - 30, 470, "+5V", ORG, left=True)
ln([(EX - 30, 520), (EX - 60, 520), (EX - 60, 540)])
gnd(EX - 60, 540)
tx(EX - 40, 576, "NC", 14, GRY, "end", True)
tx(885, 640, "GPIO8 = blue LED", 14, GRY, "middle")
tx(885, 660, "(active LOW)", 14, GRY, "middle")
tx(885, 690, "USB-C: upload +", 14, GRY, "middle")
tx(885, 710, "Serial Monitor", 14, GRY, "middle")
tx(885, 760, "other row (GPIO5..10,", 13, GRY, "middle")
tx(885, 778, "20, 21): not used,", 13, GRY, "middle")
tx(885, 796, "socketed for support", 13, GRY, "middle")

# signal wires
ln([(360, 620), (EX - 30, 620)], BLU)                       # SIM TXD -> GPIO4
tx(550, 610, "SIM TXD -> GPIO4 (direct)", 14, BLU, "middle")
ln([(360, 670), (430, 670)], BLU)                           # SIM RXD <- divider <- GPIO3
dot(430, 670, BLU)
res_h(430, 600, 670, "R1 10k", BLU)
ln([(600, 670), (EX - 30, 670)], BLU)
res_v(430, 670, 750, "R2 20k", BLU)
gnd(430, 750)
tx(640, 700, "GPIO3 -> 10k/20k -> SIM RXD", 14, BLU, "middle")
tx(640, 716, "(3.3 V -> 2.2 V)", 13, GRY, "middle")
ln([(360, 780), (640, 780), (640, 720), (EX - 30, 720)], BLU)  # SIM RST <- GPIO2
tx(520, 800, "SIM RST <- GPIO2", 14, BLU, "middle")
ln([(EX - 30, 770), (690, 770), (690, 930), (360, 930)], GRN)  # GPS TX -> GPIO1
tx(520, 922, "GPS TX -> GPIO1", 14, GRN, "middle")
ln([(EX - 30, 820), (720, 820), (720, 980), (360, 980)], GRN)  # GPS RX <- GPIO0
tx(520, 972, "GPS RX <- GPIO0", 14, GRN, "middle")

# ------------------------------------------------------------------ notes
NX = 1060
tx(NX, 350, "3. Notes", 20, GRY, "start", True)
notes = [
    ("All GND pins are connected together.", BLK),
    ("SIM800L runs straight from the cell (VBAT).", BLK),
    ("  Never feed it 5 V or 3.3 V from the ESP32.", RED),
    ("  Peaks of 2 A: short, thick VBAT/GND wires,", BLK),
    ("  C1 1000 uF right at its VCC pin.", BLK),
    ("SIM800L RXD is 2.8 V logic, so ESP TX goes", BLK),
    ("  through the R1/R2 divider. TXD is direct.", BLK),
    ("GPIO2 is a strapping pin; SIM800L RST", BLK),
    ("  pulls it high, so boot is safe.", BLK),
    ("Firmware: MODEM_RX_PIN 4, MODEM_TX_PIN 3,", BLU),
    ("  MODEM_RST_PIN 2, GPS_RX_PIN 1, GPS_TX_PIN 0", BLU),
    ("Arduino: USB CDC On Boot = Enabled.", BLU),
    ("The board has no protection between USB", RED),
    ("  5 V and the 5V pin: switch SW1 OFF while", RED),
    ("  USB is plugged in, or fit a 1N5819", RED),
    ("  diode from MT3608 OUT+ to the 5V pin.", RED),
    ("Charge the cell outside the board", BLK),
    ("  (TP4056 with protection).", BLK),
]
y = 420
for s, c in notes:
    tx(NX, y, s, 16, c)
    y += 26

el.append(f'<rect x="1040" y="395" width="500" height="{y-395}" rx="10" fill="none" stroke="#bbb" stroke-width="2"/>')

svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">' + "".join(el) + "</svg>"
open(out_svg, "w").write(svg)
cairosvg.svg2png(bytestring=svg.encode(), write_to=out_png, output_width=W)
print("ok")
