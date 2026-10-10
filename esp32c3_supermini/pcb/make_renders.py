"""
make_renders.py - exports Gerbers, drill files and PNG renders for the C3 carrier
board, plus an assembly image (module positions + side view).

Run after generate_pcb_c3.py:   python3 make_renders.py
Needs: kicad-cli (KiCad 7), cairosvg, Pillow.
"""

import os
import shutil
import subprocess
import zipfile

import cairosvg
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
PCB = os.path.join(HERE, "gsm_tracker_c3.kicad_pcb")
GERB = os.path.join(HERE, "gerbers")
REND = os.path.join(HERE, "renders")


def run(*args):
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


# --- Gerbers + drill -------------------------------------------------------
shutil.rmtree(GERB, ignore_errors=True)
os.makedirs(GERB)
run("kicad-cli", "pcb", "export", "gerbers", "--layers",
    "F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts", "-o", GERB + "/", PCB)
run("kicad-cli", "pcb", "export", "drill", "--generate-map", "--map-format", "pdf", "-o", GERB + "/", PCB)
with zipfile.ZipFile(os.path.join(HERE, "gsm_tracker_c3_gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(os.listdir(GERB)):
        z.write(os.path.join(GERB, f), f)

# --- Front / back renders ----------------------------------------------------
shutil.rmtree(REND, ignore_errors=True)
os.makedirs(REND)
for name, layers, extra in [("front", "F.Cu,F.Silkscreen,Edge.Cuts,F.Mask", []),
                            ("back", "B.Cu,B.Silkscreen,Edge.Cuts,B.Mask", ["--mirror"])]:
    svg = os.path.join(REND, name + ".svg")
    run("kicad-cli", "pcb", "export", "svg", "--layers", layers, *extra, "--exclude-drawing-sheet",
        "--page-size-mode", "2", "-o", svg, PCB)
    cairosvg.svg2png(url=svg, write_to=os.path.join(REND, name + ".png"), output_width=1100,
                     background_color="white")
    os.remove(svg)

# --- Assembly image ------------------------------------------------------------
S, OY = 20.72, 17                     # px per mm and y offset of the 1100 px front render


def P(x, y):
    return (x * S, y * S + OY)


FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans"
f = ImageFont.truetype(FONT + "-Bold.ttf", 26)
fs = ImageFont.truetype(FONT + ".ttf", 20)

base = Image.open(os.path.join(REND, "front.png")).convert("RGBA")
ov = Image.new("RGBA", base.size, (0, 0, 0, 0))
d = ImageDraw.Draw(ov)


def box(x1, y1, x2, y2, fill, outline, dashed=False):
    a, b = P(x1, y1), P(x2, y2)
    d.rectangle([*a, *b], fill=fill)
    if not dashed:
        d.rectangle([*a, *b], outline=outline, width=5)
        return
    for (ax, ay, bx, by) in [(a[0], a[1], b[0], a[1]), (b[0], a[1], b[0], b[1]),
                             (b[0], b[1], a[0], b[1]), (a[0], b[1], a[0], a[1])]:
        n = int(max(abs(bx - ax), abs(by - ay)) // 24) + 1
        for i in range(n):
            t0, t1 = i / n, i / n + 0.5 / n
            d.line([ax + (bx - ax) * t0, ay + (by - ay) * t0, ax + (bx - ax) * t1, ay + (by - ay) * t1],
                   fill=outline, width=5)


def label(x, y, t, c, font=f):
    px, py = P(x, y)
    w = d.textlength(t, font=font)
    d.rectangle([px - w / 2 - 6, py - 16, px + w / 2 + 6, py + 16], fill=(255, 255, 255, 225))
    d.text((px - w / 2, py - 14), t, fill=c, font=font)


box(1.0, 0.8, 24.4, 25.8, (255, 140, 0, 60), (255, 120, 0, 255), dashed=True)       # SIM800L (back)
box(16.0, 33.0, 52.6, 50.0, (160, 60, 220, 50), (150, 50, 220, 255), dashed=True)   # MT3608 (back)
box(34.1, 0.4, 52.1, 23.0, (30, 120, 255, 90), (20, 90, 230, 255))                  # C3 (front)
box(10.0, 25.5, 46.0, 51.5, (0, 170, 80, 80), (0, 140, 60, 255))                    # GPS (front)
label(43.1, 18.6, "ESP32-C3", (20, 80, 220, 255))
label(43.1, 20.6, "chip side UP", (20, 80, 220, 255), fs)
label(28.0, 31.0, "NEO-M8N GPS (top, on J4)", (0, 120, 50, 255))
label(12.7, 12.0, "SIM800L", (220, 100, 0, 255))
label(12.7, 13.6, "(bottom side)", (220, 100, 0, 255), fs)
label(34.0, 47.6, "MT3608 (bottom side)", (130, 40, 200, 255))
top = Image.alpha_composite(base, ov).convert("RGB")

W, H = top.size[0], 300
side = Image.new("RGB", (W, H), "white")
sd = ImageDraw.Draw(side)
sd.text((20, 10), "Side view (not to scale): front = up", fill="black", font=f)
y = 165
sd.rectangle([40, y, W - 40, y + 12], fill=(40, 140, 60))
sd.text((40, y - 30), "PCB", fill="black", font=fs)
sd.rectangle([700, y - 70, 730, y], fill=(30, 30, 30))
sd.rectangle([1020, y - 70, 1050, y], fill=(30, 30, 30))
sd.rectangle([690, y - 82, 1060, y - 70], fill=(30, 110, 230))
sd.text((740, y - 110), "ESP32-C3 on 2 x 1x8 sockets", fill=(20, 80, 220), font=fs)
sd.rectangle([230, y - 70, 260, y], fill=(30, 30, 30))
sd.rectangle([200, y - 82, 660, y - 70], fill=(0, 160, 70))
sd.rectangle([590, y - 70, 640, y], fill=(250, 200, 120))
sd.text((560, y - 40), "foam", fill="black", font=fs)
sd.text((210, y - 110), "GPS board on 1x4 socket J4", fill=(0, 120, 50), font=fs)
sd.rectangle([60, y + 12, 90, y + 82], fill=(30, 30, 30))
sd.rectangle([440, y + 12, 470, y + 82], fill=(30, 30, 30))
sd.rectangle([50, y + 82, 480, y + 94], fill=(200, 30, 30))
sd.text((60, y + 100), "SIM800L on 2 x 1x6 sockets (bottom)", fill=(200, 30, 30), font=fs)
sd.rectangle([600, y + 18, 1040, y + 30], fill=(60, 60, 200))
sd.text((620, y + 36), "MT3608 flat (bottom)", fill=(60, 60, 200), font=fs)
sd.text((560, y + 100), "Use >= 15 mm standoffs under the board", fill="black", font=fs)

out = Image.new("RGB", (W, top.size[1] + H), "white")
out.paste(top, (0, 0))
out.paste(side, (0, top.size[1]))
out.save(os.path.join(REND, "assembly.png"))
print("renders + gerbers written")
