# GSM/GPS Tracker carrier board v1.0

A compact 2-layer carrier PCB (**60 x 52 mm**) for the working tracker. The ESP32 DevKit, SIM800L module and NEO-M8N GPS plug into headers, so there is no loose wiring and no SMD soldering.

![front](renders/front.png)

## Files

| File | Purpose |
|---|---|
| `gsm_tracker.kicad_pcb` / `.kicad_pro` | KiCad 7 board (open in KiCad, or import into Altium) |
| `gsm_tracker_gerbers.zip` | Gerber + drill files, ready to upload to JLCPCB / PCBWay |
| `BOM.csv` | Parts list |
| `generate_pcb.py` | Script that generates the board (re-run after changing positions) |
| `drc_report.txt` | KiCad design-rule check report |
| `renders/front.png`, `renders/back.png` | Copper + silkscreen views (back view is mirrored) |

## Opening in Altium Designer

1. Go to **File → Import Wizard → KiCad Design Files**.
2. Select `gsm_tracker.kicad_pcb`.
3. The board imports with its footprints, tracks, nets and copper pours.
4. After importing, run **Tools → Polygon Pours → Repour All**.

## Circuit

```
Li-ion 1S (J1) --SW1--> VBAT --+--> SIM800L VCC   (C1 1000 uF + C2 100 nF at the module)
                               +--> MT3608 IN+ --> 5.0 V --+--> ESP32 VIN  (C3 100 uF)
                                                           +--> GPS 5V (J4)
```

| Signal | ESP32 pin | Module pin | Notes |
|---|---|---|---|
| SIM_TXD | D26 (GPIO26) | SIM800L TXD | direct |
| SIM_RXD | D27 (GPIO27) | SIM800L RXD | 10k / 20k divider (R1, R2) |
| SIM_RST | D5 (GPIO5) | SIM800L RST | direct |
| GPS_TX | RX2 (GPIO16) | GPS TX | |
| GPS_RX | TX2 (GPIO17) | GPS RX | |

These are the same pins the firmware already uses, so no firmware change is needed.

## Before ordering and assembling: please check

1. **ESP32 row spacing.** Measure the distance between the two pin rows of your DevKit.
   - **22.86 mm (0.9 in):** fit header **J6**.
   - **25.40 mm (1.0 in):** fit header **J7** instead.

   Both footprints are on the board. The J6/J7 courtyard overlap in the DRC report is intentional.
2. **SIM800L pin order.** The module must sit so that its pins match the silkscreen labels: NET, VCC, RST, RXD, TXD, GND, from top to bottom.
3. **MT3608 boost module.** This needs extra care:
   - It mounts on the **back**, under the ESP32. Its four pads (IN+, IN−, OUT+, OUT−) are large, so you can fit the module directly with pins or with short wires.
   - Adjust it to **5.0 V with a multimeter before connecting it.** These modules often ship set to 12 V or more, which would destroy the ESP32.
4. **Battery.** Use a protected 18650 cell and charge it outside the board (for example with a TP4056 module that has protection).
   - SIM800L needs at least about 3.4 V, so it may reset when the cell is nearly empty.
   - Pin 1 of J1 is **+**.
5. **GPS.** Connect it through J4 with a short cable and place the GPS antenna facing the sky. Keep it away from the SIM800L antenna.

## Design notes

- The board is 2 layers with GND pours on both sides and stitching vias.
- Track widths:
  - VBAT: 1.0–1.2 mm (SIM800L draws 2 A peaks)
  - 5 V: 0.8 mm
  - signals: 0.3 mm
- Minimum clearance is 0.2 mm, and vias are 0.8/0.4 mm. Both are inside standard JLCPCB/PCBWay capabilities.
- There is a copper keep-out under the ESP32 PCB antenna.
- DRC result:
  - **0 unconnected items.**
  - The only reported error is the intentional J6/J7 courtyard overlap.
  - The remaining warnings are cosmetic: silkscreen overlaps and library-link notices.
