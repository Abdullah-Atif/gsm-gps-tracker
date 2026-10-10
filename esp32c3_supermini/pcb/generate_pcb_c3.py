"""
generate_pcb_c3.py  (v2 - every module plugs straight into the board)
=====================================================================
Generates the KiCad 7 PCB for the ESP32-C3 Super Mini version of the
GSM/GPS tracker (2 layers, 53 x 52 mm).

No module hangs on wires. Every module sits on female sockets that take ALL of
its pins (unused pins too), so each module is held mechanically on both sides.

  FRONT : ESP32-C3 Super Mini   2 x 1x8 sockets (all 16 pins), USB-C at the top edge
          NEO-M8N GPS board     1x4 socket; the module lies over the lower half of
                                the board (its far end rests on a foam pad / spacer)
          Li-ion JST, slide switch, 1000 uF + 100 nF, 100 uF, 10k/20k divider
  BACK  : SIM800L mini          1x6 socket for the interface row (NET..GND) plus a
                                1x6 socket for the audio row (RING..SPKN, no connection).
                                Two audio-row positions are provided (J8 = 17.78 mm,
                                J9 = 20.32 mm row spacing): fit only the one that matches.
          MT3608 boost module   lies flat, connected by its 4 pads

Power: 1S Li-ion -> SW1 -> VBAT -> SIM800L (direct, 1000 uF buffer)
                               -> MT3608 boost -> 5.0 V -> C3 "5V" pin + GPS VCC

Super Mini, seen from the component side with USB-C up (= as it sits on this board):
  RIGHT row (USB end first): 5V, GND, 3V3, GPIO4, GPIO3, GPIO2, GPIO1, GPIO0
  LEFT  row (USB end first): GPIO5, 6, 7, 8, 9, 10, 20, 21
  (The printed pin labels are on the underside, where the rows appear swapped.)
  GPIO4 <- SIM800L TXD
  GPIO3 -> R1 10k -> SIM800L RXD (R2 20k to GND)
  GPIO2 -> SIM800L RST
  GPIO1 <- GPS TX        GPIO0 -> GPS RX
The left row (GPIO5..10, 20, 21) is only mechanical support.

Firmware for this board: MODEM_RX_PIN 4, MODEM_TX_PIN 3, MODEM_RST_PIN 2,
                         GPS_RX_PIN 1, GPS_TX_PIN 0.

Module footprints were estimated from a breadboard photo (not measured).
Check the assumptions listed in README.md before ordering.

Run with KiCad 7's Python:   python3 generate_pcb_c3.py
"""

import os
import pcbnew

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PCB_FILE = os.path.join(OUT_DIR, "gsm_tracker_c3.kicad_pcb")
FP_ROOT = "/usr/share/kicad/footprints"

BOARD_W, BOARD_H = 53.0, 52.0


def mm(v):
    return pcbnew.FromMM(v)


def pt(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


board = pcbnew.BOARD()

# ---------------------------------------------------------------------------
# Design rules (well inside JLCPCB / PCBWay standard capabilities)
# ---------------------------------------------------------------------------
ds = board.GetDesignSettings()
ds.m_MinClearance = mm(0.2)
ds.m_TrackMinWidth = mm(0.2)
ds.m_ViasMinSize = mm(0.6)
ds.m_MinThroughDrill = mm(0.3)
ds.m_CopperEdgeClearance = mm(0.5)
ds.m_MinResolvedSpokes = 1          # a pad may connect with a single thermal spoke per layer
ds.m_MinSilkTextHeight = mm(0.8)
nc = ds.m_NetSettings.m_DefaultNetClass
nc.SetClearance(mm(0.2))
nc.SetTrackWidth(mm(0.3))
nc.SetViaDiameter(mm(0.8))
nc.SetViaDrill(mm(0.4))

# ---------------------------------------------------------------------------
# Nets
# ---------------------------------------------------------------------------
NETS = {}
for name in ["GND", "VBAT_RAW", "VBAT", "+5V", "SIM_TXD", "SIM_RXD", "ESP_TX_SIM",
             "SIM_RST", "GPS_RX", "GPS_TX"]:
    n = pcbnew.NETINFO_ITEM(board, name)
    board.Add(n)
    NETS[name] = n


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def load_fp(lib, name):
    fp = pcbnew.FootprintLoad(os.path.join(FP_ROOT, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError(f"footprint not found: {lib}:{name}")
    return fp


def place(lib, name, ref, value, pad1_xy, rot=0.0, nets=None, ref_offset=None, hide_value=True, back=False):
    """Place a library footprint so that its pad '1' lands on pad1_xy (back=True: bottom side)."""
    fp = load_fp(lib, name)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pt(0, 0))
    if back:
        board.Add(fp)                    # Flip() needs the footprint to belong to a board
        fp.Flip(pt(0, 0), True)          # mirror left-right: pad order along Y is kept
    pad1 = fp.FindPadByNumber("1")
    p1 = pad1.GetPosition() if pad1 is not None else pcbnew.VECTOR2I(0, 0)   # holes: no pad 1
    fp.SetPosition(pcbnew.VECTOR2I(mm(pad1_xy[0]) - p1.x, mm(pad1_xy[1]) - p1.y))
    fp.SetReference(ref)
    fp.SetValue(value)
    fp.Value().SetVisible(not hide_value)
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(mm(0.9), mm(0.9)))
    fp.Reference().SetTextThickness(mm(0.15))
    if ref_offset is not None:
        fp.Reference().SetPosition(pt(*ref_offset))
    if back:
        fp.Reference().SetMirrored(True)
    else:
        board.Add(fp)
    for num, net in (nets or {}).items():
        for pad in fp.Pads():
            if pad.GetNumber() == str(num):
                pad.SetNet(NETS[net])
    return fp


def track(points, net, width=0.3, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(points[:-1], points[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(pt(x1, y1))
        t.SetEnd(pt(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(NETS[net])
        board.Add(t)


def via(x, y, net, size=0.8, drill=0.4):
    v = pcbnew.PCB_VIA(board)
    v.SetPosition(pt(x, y))
    v.SetWidth(mm(size))
    v.SetDrill(mm(drill))
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    v.SetNet(NETS[net])
    board.Add(v)


def line(x1, y1, x2, y2, layer, width=0.15):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(pt(x1, y1))
    s.SetEnd(pt(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def rect(x1, y1, x2, y2, layer, width=0.15):
    line(x1, y1, x2, y1, layer, width)
    line(x2, y1, x2, y2, layer, width)
    line(x2, y2, x1, y2, layer, width)
    line(x1, y2, x1, y1, layer, width)


def dashed_rect(x1, y1, x2, y2, layer, dash=1.5, gap=1.0, width=0.12):
    """Dashed outline: marks a module body that sits above/below the board."""
    for (ax, ay), (bx, by) in [((x1, y1), (x2, y1)), ((x2, y1), (x2, y2)),
                               ((x2, y2), (x1, y2)), ((x1, y2), (x1, y1))]:
        length = ((bx - ax) ** 2 + (by - ay) ** 2) ** 0.5
        ux, uy = (bx - ax) / length, (by - ay) / length
        s = 0.0
        while s < length:
            e = min(s + dash, length)
            line(ax + ux * s, ay + uy * s, ax + ux * e, ay + uy * e, layer, width)
            s += dash + gap


def text(s, x, y, size=0.8, layer=pcbnew.F_SilkS, rot=0, mirror=False):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(pt(x, y))
    t.SetLayer(layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.12, size * 0.15)))
    t.SetTextAngleDegrees(rot)
    if mirror:
        t.SetMirrored(True)
    board.Add(t)


def zone(layer, net, pts):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(mm(x), mm(y))
    z.SetNet(NETS[net])
    z.SetMinThickness(mm(0.25))
    z.SetLocalClearance(mm(0.3))
    z.SetThermalReliefGap(mm(0.4))
    z.SetThermalReliefSpokeWidth(mm(0.5))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    board.Add(z)
    return z


def custom_pad(fp, num, x, y, net, size=2.5, drill=1.1):
    p = pcbnew.PAD(fp)
    p.SetNumber(num)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetLayerSet(p.PTHMask())
    p.SetSize(pt(size, size))
    p.SetDrillSize(pt(drill, drill))
    c = fp.GetPosition()
    p.SetPos0(pcbnew.VECTOR2I(mm(x) - c.x, mm(y) - c.y))
    p.SetPosition(pt(x, y))
    fp.Add(p)
    if net:
        p.SetNet(NETS[net])
    return p


# ---------------------------------------------------------------------------
# Board outline
# ---------------------------------------------------------------------------
rect(0, 0, BOARD_W, BOARD_H, pcbnew.Edge_Cuts, 0.1)

PS = "Connector_PinSocket_2.54mm"
F, B = pcbnew.F_Cu, pcbnew.B_Cu
FS, BS = pcbnew.F_SilkS, pcbnew.B_SilkS
PWR, MID, SIG = 1.0, 0.8, 0.3

# ---------------------------------------------------------------------------
# ESP32-C3 Super Mini (front, component side up). Pin 1 = USB end (top). Both rows socketed.
# Seen from the top, the 5V/GND/3V3/GPIO4..0 row is on the RIGHT.
# ---------------------------------------------------------------------------
C3_L_X, C3_R_X, C3_Y0 = 35.5, 35.5 + 15.24, 4.0


def c3_y(pin):
    return C3_Y0 + (pin - 1) * 2.54


place(PS, "PinSocket_1x08_P2.54mm_Vertical", "J5", "C3_POWER_ROW", (C3_R_X, C3_Y0),
      nets={1: "+5V", 2: "GND", 4: "SIM_TXD", 5: "ESP_TX_SIM", 6: "SIM_RST", 7: "GPS_TX", 8: "GPS_RX"},
      ref_offset=(C3_R_X - 2.6, 24.3))
place(PS, "PinSocket_1x08_P2.54mm_Vertical", "J6", "C3_GPIO5_21_ROW", (C3_L_X, C3_Y0),
      ref_offset=(C3_L_X - 2.4, 18.6))

# ---------------------------------------------------------------------------
# SIM800L mini (BACK). Interface row: NET VCC RST RXD TXD GND (NET at the bottom).
# ---------------------------------------------------------------------------
SIM_X = 2.6
SIM_Y = {"GND": 7.0, "TXD": 9.54, "RXD": 12.08, "RST": 14.62, "VCC": 17.16, "NET": 19.70}
place(PS, "PinSocket_1x06_P2.54mm_Vertical", "J3", "SIM800L_IF", (SIM_X, SIM_Y["NET"]), rot=180, back=True,
      nets={2: "VBAT", 3: "SIM_RST", 4: "SIM_RXD", 5: "SIM_TXD", 6: "GND"}, ref_offset=(SIM_X + 0.2, 21.9))
# Audio row (RING DTR MIC+ MIC- SPK+ SPK-): mechanical only, two possible row spacings
place(PS, "PinSocket_1x06_P2.54mm_Vertical", "J8", "SIM800L_AUDIO_17.78", (SIM_X + 17.78, 19.70), rot=180,
      back=True, ref_offset=(SIM_X + 17.78, 21.9))
place(PS, "PinSocket_1x06_P2.54mm_Vertical", "J9", "SIM800L_AUDIO_20.32", (SIM_X + 20.32, 19.70), rot=180,
      back=True, ref_offset=(SIM_X + 20.32, 5.0))

# ---------------------------------------------------------------------------
# Power section (front, top-left)
# ---------------------------------------------------------------------------
place("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", "C1", "1000uF_10V", (9.5, 4.9), rot=180,
      nets={1: "VBAT", 2: "GND"}, ref_offset=(7.75, 10.0))
place("Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", "C2", "100nF", (5.6, SIM_Y["VCC"]), rot=-90,
      nets={1: "VBAT", 2: "GND"}, ref_offset=(7.6, 21.5))
sw1 = place("Button_Switch_THT", "SW_Slide_SPDT_Straight_CK_OS102011MS2Q", "SW1", "PWR",
            (16.0, 3.0), nets={2: "VBAT", 3: "VBAT_RAW"}, ref_offset=(16.0, 9.0))
for item in sw1.GraphicalItems():          # the library draws this front-side switch's
    if item.GetLayer() == pcbnew.B_CrtYd:  # courtyard on B.CrtYd; move it to the front
        item.SetLayer(pcbnew.F_CrtYd)
place("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "J1", "BATT_1S",
      (27.0, 3.6), nets={1: "VBAT_RAW", 2: "GND"}, ref_offset=(31.8, 0.9))
place("Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", "C3", "100uF_10V", (49.5, 29.5), rot=90,
      nets={1: "+5V", 2: "GND"}, ref_offset=(46.0, 28.5))

# SIM800L RXD level divider (low-profile horizontal resistors, front)
R_X1, R_X2 = 26.0, 26.0 + 5.08
R1_Y, R2_Y = 13.35, 8.6
place("Resistor_THT", "R_Axial_DIN0204_L3.6mm_D1.6mm_P5.08mm_Horizontal", "R1", "10k",
      (R_X1, R1_Y), nets={1: "SIM_RXD", 2: "ESP_TX_SIM"}, ref_offset=(26.6, 15.2))
place("Resistor_THT", "R_Axial_DIN0204_L3.6mm_D1.6mm_P5.08mm_Horizontal", "R2", "20k",
      (R_X1, R2_Y), nets={1: "SIM_RXD", 2: "GND"}, ref_offset=(26.6, 11.1))

# ---------------------------------------------------------------------------
# GPS (front). 1x4 socket at the left end; module body lies to the right.
# Pin order top -> bottom: GND, TX, RX, VCC
# ---------------------------------------------------------------------------
GPS_X = 12.0
GPS_Y = {"GND": 34.19, "TX": 36.73, "RX": 39.27, "VCC": 41.81}
place(PS, "PinSocket_1x04_P2.54mm_Vertical", "J4", "GPS", (GPS_X, GPS_Y["GND"]),
      nets={1: "GND", 2: "GPS_TX", 3: "GPS_RX", 4: "+5V"}, ref_offset=(GPS_X, 31.9))

# Mounting holes (M2)
place("MountingHole", "MountingHole_2.2mm_M2", "H1", "M2", (3.0, 36.0), ref_offset=(3.0, 33.0))
place("MountingHole", "MountingHole_2.2mm_M2", "H2", "M2", (3.0, 48.5), ref_offset=(3.0, 45.5))

# MT3608 boost module (BACK, lies flat): custom 4-pad footprint with large pads
BOOST_C = (34.5, 41.5)
boost = pcbnew.FOOTPRINT(board)
boost.SetReference("U3")
boost.SetValue("MT3608_5V")
boost.SetPosition(pt(*BOOST_C))
board.Add(boost)
boost.Reference().SetPosition(pt(34.5, 44.5))
boost.Reference().SetLayer(BS)
boost.Reference().SetMirrored(True)
boost.Value().SetVisible(False)
BOOST_PADS = {"1": (18.5, 36.0, "VBAT", "IN+"), "2": (18.5, 47.0, "GND", "IN-"),
              "3": (50.5, 36.0, "+5V", "OUT+"), "4": (50.5, 47.0, "GND", "OUT-")}
for num, (x, y, net, _lbl) in BOOST_PADS.items():
    custom_pad(boost, num, x, y, net)

# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------
# Battery -> switch (VBAT_RAW), switch -> VBAT
track([(27.0, 3.6), (25.2, 5.4), (20.0, 5.4), (20.0, 3.0)], "VBAT_RAW", MID)
track([(18.0, 3.0), (18.0, 6.0), (10.5, 6.0), (9.5, 5.0), (9.5, 4.9)], "VBAT", PWR)
# VBAT -> C2 -> SIM800L VCC (front)
track([(10.5, 6.0), (10.5, 15.0), (8.34, SIM_Y["VCC"]), (5.6, SIM_Y["VCC"])], "VBAT", PWR)
track([(5.6, SIM_Y["VCC"]), (SIM_X, SIM_Y["VCC"])], "VBAT", 1.2)
# VBAT -> MT3608 IN+ (drop to the back below the SIM signal lanes)
track([(10.5, 15.0), (10.5, 19.0)], "VBAT", PWR)
via(10.5, 19.0, "VBAT", 1.0, 0.5)
track([(10.5, 19.0), (10.5, 30.0), (12.5, 32.0), (15.5, 32.0), (18.5, 35.0), (18.5, 36.0)], "VBAT", PWR, B)

# MT3608 OUT+ -> C3 "5V" pin (back)
track([(50.5, 36.0), (43.12, 28.62)], "+5V", MID, B)
via(43.12, 28.62, "+5V")
track([(43.12, 28.62), (43.12, 6.0), (45.12, 4.0), (C3_R_X, 4.0)], "+5V", MID, F)   # under the C3, front
# MT3608 OUT+ -> 100 uF (back)
track([(50.5, 36.0), (50.5, 31.0), (49.5, 30.0), (49.5, 29.5)], "+5V", MID, B)
# MT3608 OUT+ -> GPS VCC (front)
track([(50.5, 36.0), (46.0, 40.5), (19.0, 40.5), (17.69, GPS_Y["VCC"]), (GPS_X, GPS_Y["VCC"])], "+5V", MID, F)

# SIM800L signals: back lanes run between the audio-row pads
# The lanes pass between the pads of the left C3 row (J6) to reach the right row (J5).
track([(SIM_X, SIM_Y["TXD"]), (3.87, 10.81), (29.0, 10.81), (29.46, 10.35), (40.5, 10.35),
       (41.77, c3_y(4)), (C3_R_X, c3_y(4))],
      "SIM_TXD", SIG, B)                                                   # TXD -> GPIO4
track([(SIM_X, SIM_Y["RXD"]), (3.87, R1_Y), (R_X1, R1_Y)], "SIM_RXD", SIG, B)   # RXD -> R1
track([(R_X1, R2_Y), (R_X1, R1_Y)], "SIM_RXD", SIG, F)                     # R2 -> divider node
track([(R_X2, R1_Y), (31.54, 12.89), (41.0, 12.89), (42.27, c3_y(5)), (C3_R_X, c3_y(5))],
      "ESP_TX_SIM", SIG, B)                                                # R1 -> GPIO3
track([(SIM_X, SIM_Y["RST"]), (3.87, 15.89), (30.0, 15.89), (30.46, 15.43), (41.5, 15.43),
       (42.77, c3_y(6)), (C3_R_X, c3_y(6))],
      "SIM_RST", SIG, B)                                                   # RST -> GPIO2

# GPS signals (front)
track([(C3_R_X, c3_y(7)), (49.47, 20.51), (34.0, 20.51)], "GPS_TX", SIG, B)  # back, between J6 pads
via(34.0, 20.51, "GPS_TX")
track([(34.0, 20.51), (32.77, 21.74), (20.0, 21.74), (15.0, 26.74), (15.0, 35.23),
       (13.5, GPS_Y["TX"]), (GPS_X, GPS_Y["TX"])], "GPS_TX", SIG, F)      # GPS TX -> GPIO1
track([(C3_R_X, c3_y(8)), (49.47, 23.05), (34.23, 23.05), (34.0, 23.28)], "GPS_RX", SIG, B)  # back, below J6
via(34.0, 23.28, "GPS_RX")
track([(34.0, 23.28), (21.0, 23.28), (16.5, 27.78), (16.5, 37.77),
       (15.0, GPS_Y["RX"]), (GPS_X, GPS_Y["RX"])], "GPS_RX", SIG, F)      # GPIO0 -> GPS RX

# GND stitching vias
for x, y in [(14.0, 8.5), (33.0, 6.5), (40.0, 6.5), (46.5, 18.5), (31.0, 19.0),
             (7.0, 24.0), (12.5, 28.0), (24.0, 30.0), (40.0, 30.5), (30.0, 37.0), (40.0, 44.0),
             (24.0, 49.5), (46.5, 49.5), (7.0, 42.0), (51.5, 26.0)]:
    via(x, y, "GND")

# ---------------------------------------------------------------------------
# Copper pours (GND both layers)
# ---------------------------------------------------------------------------
outline = [(0.3, 0.3), (BOARD_W - 0.3, 0.3), (BOARD_W - 0.3, BOARD_H - 0.3), (0.3, BOARD_H - 0.3)]
zone(F, "GND", outline)
zone(B, "GND", outline)

# ---------------------------------------------------------------------------
# Silkscreen - front
# ---------------------------------------------------------------------------
L_NAMES = ["5", "6", "7", "8", "9", "10", "20", "21"]     # top view, USB-C up
R_NAMES = ["5V", "G", "3V3", "4", "3", "2", "1", "0"]
for i, (l, r) in enumerate(zip(L_NAMES, R_NAMES)):
    text(l, C3_L_X + 2.4, c3_y(i + 1), 0.8)
    text(r, C3_R_X - 2.4, c3_y(i + 1), 0.8)
rect(C3_L_X - 1.6, 1.0, C3_R_X + 1.6, 23.4, FS, 0.12)
text("USB-C", 43.12, 1.3, 0.8)
text("ESP32-C3", 43.12, 10.0, 1.0)
text("Super", 43.12, 14.0, 0.8)
text("Mini", 43.12, 15.6, 0.8)

text("+", 26.2, 6.2, 0.8)
text("BAT", 28.25, 0.9, 0.8)
text("OFF     ON", 18.0, 5.5, 0.8)        # slider towards pad 3 = ON
text("10k", 30.4, 15.2, 0.8)
text("20k", 30.4, 11.1, 0.8)

# SIM800L marks on the front (module is on the back)
for n in ["TXD", "RXD", "RST"]:
    text(n, 5.4, SIM_Y[n], 0.8)
text("SIM800L on BACK", 8.0, 23.4, 0.8)

# GPS module body (elevated on J4)
dashed_rect(10.0, 25.5, 46.0, 51.3, FS)
text("G", 9.6, GPS_Y["GND"], 0.8)
text("TX", 9.6, GPS_Y["TX"], 0.8)
text("RX", 9.6, GPS_Y["RX"], 0.8)
text("5V", 9.6, GPS_Y["VCC"], 0.8)
text("NEO-M8N GPS board (lies here, header on J4)", 28.0, 49.6, 0.8)
text("foam pad under this end", 37.0, 27.3, 0.8)

text("GSM/GPS Tracker C3 v2.0", 28.0, 44.0, 1.0)

# ---------------------------------------------------------------------------
# Silkscreen - back
# ---------------------------------------------------------------------------
for n in ["NET", "VCC", "RST", "RXD", "TXD", "GND"]:
    text(n, SIM_X + 3.0, SIM_Y[n], 0.8, BS, mirror=True)
dashed_rect(1.0, 0.8, 24.4, 25.8, BS)
text("SIM800L, antenna end here", 13.0, 22.8, 0.8, BS, mirror=True)
text("(component side faces out)", 13.0, 24.4, 0.8, BS, mirror=True)
text("J8 or J9: fit the one", 11.5, 6.0, 0.8, BS, mirror=True)
text("that matches the module", 11.5, 7.5, 0.8, BS, mirror=True)

dashed_rect(16.0, 33.0, 52.6, 50.0, BS)
for num, (x, y, _net, lbl) in BOOST_PADS.items():
    text(lbl, x + (3.2 if x < 30 else -3.6), y, 0.8, BS, mirror=True)
text("MT3608 - set 5.0V first!", 34.5, 41.5, 1.0, BS, mirror=True)
text("A. Atif, BUET EEE", 34.5, 38.5, 0.8, BS, mirror=True)
text("C3 chip side up: 5V/G row on the RIGHT (front view)", 26.5, 51.0, 0.8, BS, mirror=True)

# ---------------------------------------------------------------------------
# Save, reload, fill zones, DRC
# ---------------------------------------------------------------------------
board.Save(PCB_FILE)
loaded = pcbnew.LoadBoard(PCB_FILE)
loaded.BuildConnectivity()
filler = pcbnew.ZONE_FILLER(loaded)
filler.Fill(loaded.Zones())
loaded.Save(PCB_FILE)
pcbnew.WriteDRCReport(loaded, os.path.join(OUT_DIR, "drc_report.txt"), pcbnew.EDA_UNITS_MILLIMETRES, True)
print("saved", PCB_FILE)
