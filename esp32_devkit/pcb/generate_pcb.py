"""
generate_pcb.py
================
Generates the KiCad 7 PCB for the compact GSM/GPS tracker carrier board.

Board concept (module carrier, 2 layers, 60 x 52 mm):
  * ESP32 DOIT DevKit V1 (30-pin) plugs into two 1x15 female headers.
    The right header has a second (alternate) row so both common board
    widths fit: 22.86 mm (0.9") and 25.40 mm (1.0") row spacing.
  * SIM800L mini module plugs into a 1x06 female header (NET VCC RST RXD TXD GND).
  * NEO-M8N GPS connects with a 1x04 pin header (5V, RX, TX, GND) - on a cable,
    so the GPS antenna can face the sky.
  * One Li-ion cell (JST-XH) -> slide switch -> VBAT.
    VBAT feeds the SIM800L directly (3.4-4.2 V, 2 A peaks, 1000 uF buffer)
    and an MT3608 boost module (mounted on the BACK, under the ESP32)
    that makes 5 V for the ESP32 VIN pin and the GPS module.

Signal mapping (same as the firmware - nothing to change):
  SIM800L TXD -> GPIO26 (direct)
  SIM800L RXD <- GPIO27 through 10k/20k divider
  SIM800L RST <- GPIO5
  GPS TX      -> GPIO16 (RX2)
  GPS RX      <- GPIO17 (TX2)

Run with KiCad 7's Python:   python3 generate_pcb.py
Outputs: gsm_tracker.kicad_pcb (+ DRC report) in the same folder.
"""

import os
import pcbnew

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
PCB_FILE = os.path.join(OUT_DIR, "gsm_tracker.kicad_pcb")
FP_ROOT = "/usr/share/kicad/footprints"

BOARD_W, BOARD_H = 60.0, 52.0


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
for name in ["GND", "VBAT_RAW", "VBAT", "+5V", "SIM_TXD", "SIM_RXD", "ESP_IO27",
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


def place(lib, name, ref, value, pad1_xy, rot=0.0, nets=None, ref_offset=None, hide_value=True):
    """Place a library footprint so that its pad '1' lands on pad1_xy."""
    fp = load_fp(lib, name)
    fp.SetOrientationDegrees(rot)
    fp.SetPosition(pt(0, 0))
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


def zone(layer, net, pts, rule_area=False):
    z = pcbnew.ZONE(board)
    if layer is not None:
        z.SetLayer(layer)
    o = z.Outline()
    o.NewOutline()
    for x, y in pts:
        o.Append(mm(x), mm(y))
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        ls = pcbnew.LSET()
        ls.AddLayer(pcbnew.F_Cu)
        ls.AddLayer(pcbnew.B_Cu)
        z.SetLayerSet(ls)
    else:
        z.SetNet(NETS[net])
        z.SetMinThickness(mm(0.25))
        z.SetLocalClearance(mm(0.3))
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    board.Add(z)
    return z


# ---------------------------------------------------------------------------
# Board outline
# ---------------------------------------------------------------------------
rect(0, 0, BOARD_W, BOARD_H, pcbnew.Edge_Cuts, 0.1)

# ---------------------------------------------------------------------------
# Components
# ---------------------------------------------------------------------------
PS = "Connector_PinSocket_2.54mm"
PH = "Connector_PinHeader_2.54mm"

ESP_L_X, ESP_R_X, ESP_R2_X, ESP_Y0 = 31.0, 31.0 + 22.86, 31.0 + 25.40, 10.0
def esp_y(pin):
    return ESP_Y0 + (pin - 1) * 2.54

# ESP32 DOIT DevKit V1 (30-pin) - left / right / alternate-right headers
place(PS, "PinSocket_1x15_P2.54mm_Vertical", "J5", "ESP32_L", (ESP_L_X, ESP_Y0),
      nets={9: "SIM_TXD", 10: "ESP_IO27", 14: "GND", 15: "+5V"}, ref_offset=(ESP_L_X, 7.6))
place(PS, "PinSocket_1x15_P2.54mm_Vertical", "J6", "ESP32_R_0.9in", (ESP_R_X, ESP_Y0),
      nets={8: "SIM_RST", 9: "GPS_RX", 10: "GPS_TX", 14: "GND"}, ref_offset=(ESP_R_X, 7.6))
place(PS, "PinSocket_1x15_P2.54mm_Vertical", "J7", "ESP32_R_1.0in_ALT", (ESP_R2_X, ESP_Y0),
      nets={8: "SIM_RST", 9: "GPS_RX", 10: "GPS_TX", 14: "GND"}, ref_offset=(ESP_R2_X + 0.6, 7.6))

# SIM800L mini module: NET VCC RST RXD TXD GND
place(PS, "PinSocket_1x06_P2.54mm_Vertical", "J3", "SIM800L", (3.5, 8.0),
      nets={2: "VBAT", 3: "SIM_RST", 4: "SIM_RXD", 5: "SIM_TXD", 6: "GND"}, ref_offset=(3.5, 5.6))

# Battery connector + power switch
place("Connector_JST", "JST_XH_B2B-XH-A_1x02_P2.50mm_Vertical", "J1", "BATT_1S",
      (9.5, 45.5), nets={1: "VBAT_RAW", 2: "GND"}, ref_offset=(10.75, 50.6))
sw = place("Button_Switch_THT", "SW_Slide_SPDT_Straight_CK_OS102011MS2Q", "SW1", "PWR",
           (13.5, 36.0), rot=-90, nets={2: "VBAT", 3: "VBAT_RAW"}, ref_offset=(16.6, 34.0))

# Bulk + decoupling capacitors
place("Capacitor_THT", "CP_Radial_D8.0mm_P3.50mm", "C1", "1000uF_10V", (3.5, 31.5),
      nets={1: "VBAT", 2: "GND"}, ref_offset=(5.25, 26.9))
place("Capacitor_THT", "C_Disc_D3.0mm_W1.6mm_P2.50mm", "C2", "100nF", (7.2, 10.54), rot=90,
      nets={1: "VBAT", 2: "GND"}, ref_offset=(9.6, 7.0))
place("Capacitor_THT", "CP_Radial_D5.0mm_P2.00mm", "C3", "100uF_10V", (26.0, 41.0), rot=180,
      nets={1: "+5V", 2: "GND"}, ref_offset=(25.0, 37.6))

# Level divider for SIM800L RXD (2.8 V logic)
place("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical", "R1", "10k",
      (23.46, 32.86), nets={1: "SIM_RXD", 2: "ESP_IO27"}, ref_offset=(24.7, 31.2))
place("Resistor_THT", "R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical", "R2", "20k",
      (23.46, 36.20), nets={1: "SIM_RXD", 2: "GND"}, ref_offset=(28.0, 37.4))

# GPS connector: 5V, RX (module RX), TX (module TX), GND
place(PH, "PinHeader_1x04_P2.54mm_Vertical", "J4", "GPS", (19.5, 38.0),
      nets={1: "+5V", 2: "GPS_RX", 3: "GPS_TX", 4: "GND"}, ref_offset=(19.5, 35.9))

# Mounting holes (M2)
place("MountingHole", "MountingHole_2.2mm_M2", "H1", "M2", (58.3, 50.0), ref_offset=(58.3, 50.0))
place("MountingHole", "MountingHole_2.2mm_M2", "H2", "M2", (2.6, 49.4), ref_offset=(2.6, 49.4))

# MT3608 boost module - custom footprint, mounted on the BACK under the ESP32
boost = pcbnew.FOOTPRINT(board)
boost.SetReference("U3")
boost.SetValue("MT3608_5V")
boost.SetPosition(pt(42.43, 30.0))
board.Add(boost)
boost.Reference().SetPosition(pt(42.43, 30.0))
boost.Reference().SetLayer(pcbnew.B_SilkS)
boost.Reference().SetMirrored(True)
boost.Value().SetVisible(False)
BOOST_PADS = {"1": (37.0, 46.5, "VBAT", "IN+"), "2": (47.86, 46.5, "GND", "IN-"),
              "3": (37.0, 13.5, "+5V", "OUT+"), "4": (47.86, 13.5, "GND", "OUT-")}
for num, (x, y, net, _lbl) in BOOST_PADS.items():
    p = pcbnew.PAD(boost)
    p.SetNumber(num)
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    p.SetLayerSet(p.PTHMask())
    p.SetSize(pt(2.5, 2.5))
    p.SetDrillSize(pt(1.1, 1.1))
    p.SetPos0(pt(x - 42.43, y - 30.0))      # position relative to the footprint
    p.SetPosition(pt(x, y))
    boost.Add(p)
    p.SetNet(NETS[net])

# ---------------------------------------------------------------------------
# Tracks
# ---------------------------------------------------------------------------
PWR, MID, SIG = 1.0, 0.8, 0.3

# Battery -> switch -> VBAT
track([(9.5, 45.5), (9.5, 41.5), (11.0, 40.0), (13.5, 40.0)], "VBAT_RAW", PWR)
track([(13.5, 38.0), (5.0, 38.0), (3.5, 36.5), (3.5, 31.5)], "VBAT", PWR)
# VBAT up the left edge to SIM800L VCC (and C2)
track([(3.5, 31.5), (1.5, 29.5), (1.5, 12.54), (3.5, 10.54)], "VBAT", 1.2)
track([(3.5, 10.54), (7.2, 10.54)], "VBAT", PWR)
# VBAT to boost input (back layer, along the bottom edge)
track([(13.5, 38.0), (16.0, 38.0), (16.0, 50.0), (35.0, 50.0), (37.0, 48.0), (37.0, 46.5)],
      "VBAT", PWR, pcbnew.B_Cu)

# Boost output -> ESP32 VIN (back), VIN -> C3 -> GPS 5V (front)
track([(37.0, 13.5), (34.5, 16.0), (34.5, 43.1), (32.04, 45.56), (31.0, 45.56)], "+5V", MID, pcbnew.B_Cu)
track([(31.0, 45.56), (29.0, 45.56), (26.0, 42.56), (26.0, 41.0)], "+5V", MID)
track([(26.0, 41.0), (26.0, 38.0), (19.5, 38.0)], "+5V", MID)

# SIM800L TXD -> GPIO26 (front)
track([(31.0, 30.32), (28.0, 27.32), (28.0, 19.5), (26.66, 18.16), (3.5, 18.16)], "SIM_TXD", SIG)
# GPIO27 -> R1 ; R1/R2 node -> SIM800L RXD (back)
track([(31.0, 32.86), (26.0, 32.86)], "ESP_IO27", SIG)
track([(23.46, 32.86), (23.46, 36.20)], "SIM_RXD", SIG)
track([(23.46, 32.86), (23.46, 17.0), (22.08, 15.62), (3.5, 15.62)], "SIM_RXD", SIG, pcbnew.B_Cu)

# Right header -> alternate right header (same nets)
for pin, net in ((8, "SIM_RST"), (9, "GPS_RX"), (10, "GPS_TX")):
    track([(ESP_R_X, esp_y(pin)), (ESP_R2_X, esp_y(pin))], net, SIG)

# Right-side signals run down under the ESP32 (front) to a corridor along the bottom
X_IO5, X_RX, X_TX = 50.7, 51.5, 52.3
Y_IO5, Y_RX, Y_TX = 48.6, 49.4, 50.2
track([(ESP_R_X, esp_y(8)), (X_IO5, esp_y(8)), (X_IO5, Y_IO5), (29.5, Y_IO5)], "SIM_RST", SIG)
track([(ESP_R_X, esp_y(9)), (X_RX, esp_y(9)), (X_RX, Y_RX), (22.0, Y_RX), (22.0, 40.54), (19.5, 40.54)], "GPS_RX", SIG)
track([(ESP_R_X, esp_y(10)), (X_TX, esp_y(10)), (X_TX, Y_TX), (21.0, Y_TX), (21.0, 43.08), (19.5, 43.08)], "GPS_TX", SIG)
# GPIO5 -> SIM800L RST (back)
via(29.5, Y_IO5, "SIM_RST")
track([(29.5, Y_IO5), (29.5, 14.46), (28.12, 13.08), (3.5, 13.08)], "SIM_RST", SIG, pcbnew.B_Cu)

# GND stitching vias
for x, y in [(10.0, 22.0), (14.0, 26.0), (18.0, 22.0), (12.0, 16.5), (10.0, 34.5), (15.5, 30.5),
             (20.0, 30.0), (24.5, 46.0), (13.0, 48.5), (41.0, 22.0), (44.0, 38.0), (58.5, 20.0),
             (58.5, 36.0), (6.0, 23.5), (18.0, 45.0)]:
    via(x, y, "GND")

# ---------------------------------------------------------------------------
# Copper pours (GND both layers) + ESP32 antenna keep-out
# ---------------------------------------------------------------------------
outline = [(0.3, 0.3), (BOARD_W - 0.3, 0.3), (BOARD_W - 0.3, BOARD_H - 0.3), (0.3, BOARD_H - 0.3)]
zone(pcbnew.F_Cu, "GND", outline)
zone(pcbnew.B_Cu, "GND", outline)
zone(None, None, [(29.0, 0.0), (BOARD_W, 0.0), (BOARD_W, 8.2), (29.0, 8.2)], rule_area=True)

# ---------------------------------------------------------------------------
# Silkscreen
# ---------------------------------------------------------------------------
FS, BS = pcbnew.F_SilkS, pcbnew.B_SilkS
L_NAMES = ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27", "D14", "D12", "D13", "GND", "VIN"]
R_NAMES = ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "TX2", "RX2", "D4", "D2", "D15", "GND", "3V3"]
for i, (l, r) in enumerate(zip(L_NAMES, R_NAMES)):
    text(l, ESP_L_X + 2.6, esp_y(i + 1), 0.8)
    text(r, ESP_R_X - 2.6, esp_y(i + 1), 0.8)
rect(ESP_L_X - 2.4, 2.4, ESP_R2_X + 1.6, BOARD_H - 0.2, FS, 0.12)
text("ESP32 DevKit V1 (30-pin)", 42.43, 4.2, 0.9)
text("ANTENNA - no copper", 42.43, 6.2, 0.8)
text("USB", 42.43, 50.6, 0.9)
text("0.9in:J6  1.0in:J7", 43.0, 41.6, 0.8)

for i, n in enumerate(["NET", "VCC", "RST", "RXD", "TXD", "GND"]):
    text(n, 10.6 if i in (0, 1) else 6.2, 8.0 + i * 2.54, 0.8)
text("SIM800L", 14.5, 4.0, 1.0)
rect(1.8, 1.6, 27.2, 25.6, FS, 0.12)

for i, n in enumerate(["5V", "RX", "TX", "GND"]):
    text(n, 17.4, 38.0 + i * 2.54, 0.8)
text("+", 8.3, 45.5, 1.0)
text("BAT", 4.6, 45.5, 0.8)
text("ON", 16.1, 40.0, 0.8)

# Back side: boost module outline and labels (mirrored text)
rect(33.93, 11.5, 50.93, 48.5, BS, 0.15)
text("MT3608 boost (BACK)", 42.43, 27.0, 0.9, BS, mirror=True)
text("set to 5.0 V first!", 42.43, 29.0, 0.8, BS, mirror=True)
for num, (x, y, _net, lbl) in BOOST_PADS.items():
    text(lbl, x + (2.6 if x < 42 else -2.6), y + (2.2 if y < 30 else -2.2), 0.8, BS, mirror=True)
text("GSM/GPS Tracker v1.0 - A. Atif, BUET EEE", 30.0, 51.0, 0.8, BS, mirror=True)

# ---------------------------------------------------------------------------
# Fill zones, save, DRC
# ---------------------------------------------------------------------------
# Save, then reload: a board loaded from disk has its connectivity/rule engine
# initialised, which the zone filler and DRC need.
board.Save(PCB_FILE)
loaded = pcbnew.LoadBoard(PCB_FILE)
loaded.BuildConnectivity()
filler = pcbnew.ZONE_FILLER(loaded)
filler.Fill(loaded.Zones())
loaded.Save(PCB_FILE)
pcbnew.WriteDRCReport(loaded, os.path.join(OUT_DIR, "drc_report.txt"), pcbnew.EDA_UNITS_MILLIMETRES, True)
print("saved", PCB_FILE)
