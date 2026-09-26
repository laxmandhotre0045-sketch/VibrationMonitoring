"""Draw the loading previews for the 3D Digital Twin.

`previewUrlFor()` in src/lib/digital-twin/machine-type-map.ts asks for
`/models/previews/<family>.png` — the still shown on the stage while a model
loads, so the panel shows the right machine instead of an empty box. There are
seven families and this script draws one image for each.

Why a script and not seven hand-made files: the drawings share a frame, a stroke
weight and a palette, and they will be redrawn whenever those change or a family
is added. A generator keeps the set consistent and makes "add the remaining
images" a matter of adding one function.

Two details worth knowing:

**Everything is drawn at 4x and downscaled.** Pillow does not anti-alias lines
or ellipse outlines, so drawn at final size these come out visibly jagged.
Supersampling is the standard fix and costs nothing here.

**The palette is mid-tone on purpose.** The preview sits on a CSS radial
backdrop that is near-white in the light theme and near-black in the dark one,
and the img is rendered at 60% opacity. A navy line drawing would disappear
against dark; steel blue with an orange accent reads on both.

Run:  python frontend/scripts/generate_model_previews.py
"""
from __future__ import annotations

import os

from PIL import Image, ImageDraw

# Final size. 5:3 matches the viewBox the 2D schematics already use.
W, H = 640, 384
SS = 4  # supersample factor

STROKE = (143, 166, 196, 255)   # steel blue — the machine outline
FAINT = (143, 166, 196, 130)    # internals, hatching, centre lines
ACCENT = (255, 138, 61, 255)    # orange — sensor and bearing positions
GROUND = (143, 166, 196, 90)

LW = 3          # stroke width at final scale
BASELINE = 320  # where the machine stands
AXIS = 196      # shaft centre line

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "public",
    "models",
    "previews",
)


# ---------------------------------------------------------------------------
# Drawing helpers — all take final-scale coordinates and scale up internally
# ---------------------------------------------------------------------------


class Pen:
    def __init__(self, draw: ImageDraw.ImageDraw):
        self.d = draw

    def _s(self, box):
        return [v * SS for v in box]

    def line(self, x1, y1, x2, y2, color=STROKE, w=LW):
        self.d.line(self._s([x1, y1, x2, y2]), fill=color, width=w * SS)

    def rect(self, x1, y1, x2, y2, r=0, color=STROKE, w=LW, fill=None):
        box = self._s([x1, y1, x2, y2])
        if r:
            self.d.rounded_rectangle(box, radius=r * SS, outline=color, width=w * SS, fill=fill)
        else:
            self.d.rectangle(box, outline=color, width=w * SS, fill=fill)

    def circle(self, cx, cy, r, color=STROKE, w=LW, fill=None):
        self.d.ellipse(
            self._s([cx - r, cy - r, cx + r, cy + r]), outline=color, width=w * SS, fill=fill
        )

    def ellipse(self, x1, y1, x2, y2, color=STROKE, w=LW, fill=None):
        self.d.ellipse(self._s([x1, y1, x2, y2]), outline=color, width=w * SS, fill=fill)

    def dot(self, cx, cy, r=6, color=ACCENT):
        self.d.ellipse(self._s([cx - r, cy - r, cx + r, cy + r]), fill=color)

    def dashed(self, x1, y1, x2, y2, dash=12, gap=9, color=FAINT, w=LW):
        """Pillow has no dash support; step along the segment."""
        length = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if length == 0:
            return
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        pos = 0.0
        while pos < length:
            end = min(pos + dash, length)
            self.line(x1 + dx * pos, y1 + dy * pos, x1 + dx * end, y1 + dy * end, color, w)
            pos = end + gap

    def fins(self, x1, x2, y1, y2, step=18, color=FAINT):
        """Cooling fins: evenly spaced ticks across a body."""
        x = x1
        while x <= x2:
            self.line(x, y1, x, y2, color, 2)
            x += step

    def ground(self, x1, x2, y=BASELINE):
        self.line(x1, y, x2, y, GROUND, 3)
        # Hatching under the baseline reads as "bolted down" rather than floating.
        x = x1
        while x <= x2 - 10:
            self.line(x, y, x - 10, y + 12, GROUND, 2)
            x += 16

    def centreline(self, x1, x2, y=AXIS):
        self.dashed(x1, y, x2, y, dash=16, gap=10, color=(143, 166, 196, 70), w=2)


def feet(pen: Pen, x1, x2, top, height=16):
    pen.rect(x1, top, x1 + 46, top + height)
    pen.rect(x2 - 46, top, x2, top + height)


def rotation_mark(pen: Pen, cx, cy, r=26):
    """A curved arrow over a shaft: this is the part that turns.

    The viewer can actually spin the shaft; a still cannot, so the drawing says
    so instead. Every family that has a shaft gets one, in the same place
    relative to it, so the previews read as one set.
    """
    import math

    # Three-quarter arc, drawn as short chords.
    start, sweep = -0.35 * math.pi, 1.25 * math.pi
    steps = 26
    pts = [
        (cx + math.cos(start + sweep * i / steps) * r,
         cy + math.sin(start + sweep * i / steps) * r)
        for i in range(steps + 1)
    ]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        pen.line(x1, y1, x2, y2, ACCENT, 2)

    # Arrow head on the leading end, along the tangent.
    ex, ey = pts[-1]
    ang = start + sweep + math.pi / 2
    for off in (2.5, 3.8):
        pen.line(
            ex, ey,
            ex - math.cos(ang - off) * 11, ey - math.sin(ang - off) * 11,
            ACCENT, 2,
        )


# ---------------------------------------------------------------------------
# One function per model family
# ---------------------------------------------------------------------------


def draw_motor(pen: Pen) -> None:
    """Finned TEFC motor: endbells, terminal box, shaft out the drive end."""
    pen.centreline(90, 560)
    pen.ground(120, 470)

    pen.rect(168, 132, 412, 260, r=14)          # frame
    pen.fins(186, 396, 138, 254)
    pen.ellipse(140, 140, 196, 252)             # NDE endbell
    pen.ellipse(386, 140, 442, 252)             # DE endbell
    pen.rect(252, 100, 336, 132, r=6)           # terminal box
    pen.line(442, AXIS, 524, AXIS, STROKE, 7)   # shaft
    feet(pen, 160, 420, 260)
    rotation_mark(pen, 480, AXIS)

    pen.dot(168, 150)   # NDE bearing
    pen.dot(414, 150)   # DE bearing


def draw_pump(pen: Pen) -> None:
    """Motor, coupling guard and an end-suction volute on a common baseplate."""
    pen.centreline(70, 580)
    pen.ground(80, 560)

    pen.rect(80, 296, 560, 314, r=3)            # baseplate
    pen.rect(104, 146, 268, 248, r=12)          # motor
    pen.fins(120, 254, 152, 242)
    pen.rect(96, 262, 138, 296)
    pen.rect(234, 262, 276, 296)
    pen.rect(276, 160, 330, 234, r=6)           # coupling guard
    pen.line(268, AXIS, 338, AXIS, STROKE, 6)   # drive shaft, in the open
    pen.line(338, AXIS, 412, AXIS, FAINT, 5)    # pump shaft, inside the volute

    pen.circle(408, 196, 74)                    # volute
    pen.circle(408, 196, 40, color=FAINT)       # impeller
    pen.dot(408, 196, r=5, color=FAINT)
    pen.rect(386, 92, 430, 124, r=4)            # discharge flange
    pen.line(392, 124, 392, 132, STROKE, LW)
    pen.line(424, 124, 424, 132, STROKE, LW)
    pen.rect(482, 172, 520, 220, r=4)           # suction flange
    pen.line(474, 178, 482, 178, STROKE, LW)
    pen.rect(378, 262, 438, 296)                # pedestal

    rotation_mark(pen, 303, AXIS)

    pen.dot(300, 158)   # coupling-end bearing
    pen.dot(352, 152)   # pump DE


def _scroll(pen: Pen, cx, cy, r, outlet_up=True) -> None:
    """A scroll casing with its impeller and an outlet duct."""
    pen.circle(cx, cy, r)
    pen.circle(cx, cy, int(r * 0.44), color=FAINT)
    for i in range(8):  # blades
        import math

        a = i * math.pi / 4
        inner, outer = r * 0.44, r * 0.78
        pen.line(
            cx + math.cos(a) * inner, cy + math.sin(a) * inner,
            cx + math.cos(a) * outer, cy + math.sin(a) * outer,
            FAINT, 2,
        )
    if outlet_up:
        pen.rect(cx - 30, cy - r - 62, cx + 30, cy - r + 8, r=4)
        pen.rect(cx - 38, cy - r - 76, cx + 38, cy - r - 62, r=3)


def draw_fan(pen: Pen) -> None:
    """Belt-driven centrifugal fan: motor, guard, two pedestals, scroll."""
    pen.centreline(60, 580)
    pen.ground(70, 570)

    pen.rect(72, 158, 196, 246, r=12)           # motor
    pen.fins(86, 182, 164, 240)
    pen.rect(64, 250, 106, 282)
    pen.rect(162, 250, 204, 282)
    pen.rect(204, 150, 250, 254, r=6)           # belt guard
    pen.circle(227, 202, 16, color=FAINT, w=2)

    pen.rect(268, 226, 316, 282, r=4)           # pedestal bearings
    pen.rect(330, 226, 378, 282, r=4)
    pen.line(250, 202, 400, 202, STROKE, 6)     # shaft

    rotation_mark(pen, 322, 202)

    _scroll(pen, 452, 196, 84)
    pen.ellipse(524, 156, 556, 238, color=FAINT)  # inlet bell

    pen.dot(292, 222)
    pen.dot(354, 222)


def draw_blower(pen: Pen) -> None:
    """Boxier casing than a fan, side inlet, top discharge."""
    pen.centreline(70, 570)
    pen.ground(90, 540)

    pen.rect(96, 160, 210, 248, r=12)           # motor
    pen.fins(110, 196, 166, 242)
    pen.rect(88, 250, 130, 282)
    pen.rect(176, 250, 218, 282)
    pen.line(210, 202, 252, 202, STROKE, 6)   # shaft into the casing
    rotation_mark(pen, 231, 202, r=22)

    pen.rect(252, 118, 470, 284, r=18)          # casing
    pen.circle(362, 200, 66, color=FAINT)       # impeller
    pen.circle(362, 200, 26, color=FAINT, w=2)
    pen.rect(326, 60, 398, 122, r=4)            # discharge
    pen.rect(318, 46, 406, 60, r=3)
    pen.rect(470, 168, 524, 232, r=4)           # side inlet
    pen.ellipse(516, 160, 540, 240, color=FAINT)

    pen.dot(272, 140)
    pen.dot(450, 140)


def draw_compressor(pen: Pen) -> None:
    """Reciprocating compressor: crankcase, two cylinders, flywheel."""
    pen.centreline(80, 560)
    pen.ground(100, 530)

    pen.rect(132, 186, 404, 288, r=12)          # crankcase
    for x in (196, 300):                        # cylinders
        pen.rect(x - 34, 108, x + 34, 186, r=6)
        pen.rect(x - 42, 92, x + 42, 108, r=4)
        pen.line(x, 120, x, 176, FAINT, 2)
    pen.rect(348, 150, 396, 186, r=4)           # unloader
    pen.circle(452, 232, 58)                    # flywheel
    pen.circle(452, 232, 16, color=FAINT)
    for i in range(6):
        import math

        a = i * math.pi / 3
        pen.line(
            452 + math.cos(a) * 18, 232 + math.sin(a) * 18,
            452 + math.cos(a) * 52, 232 + math.sin(a) * 52,
            FAINT, 2,
        )
    pen.line(152, 232, 404, 232, FAINT, 5)     # crankshaft, inside the case
    pen.line(404, 232, 452, 232, STROKE, 6)    # stub out to the flywheel
    feet(pen, 128, 408, 288)
    rotation_mark(pen, 452, 232, r=40)

    pen.dot(152, 200)
    pen.dot(386, 200)


def draw_gearbox(pen: Pen) -> None:
    """Split-case gearbox: input high, output low, bolted joint between."""
    pen.ground(130, 500)

    pen.rect(160, 122, 472, 286, r=14)          # casing
    pen.line(160, 204, 472, 204, FAINT, 2)      # split line
    for x in range(180, 465, 32):               # joint bolts
        pen.dot(x, 204, r=4, color=FAINT)
    pen.rect(258, 100, 374, 122, r=5)           # inspection cover

    # Both gears stay inside the casing: a gear crossing the housing outline
    # reads as a drawing error rather than as a cutaway.
    pen.circle(248, 164, 32, color=FAINT)       # input gear
    pen.circle(386, 238, 44, color=FAINT)       # output gear
    pen.line(96, 164, 160, 164, STROKE, 7)      # input shaft
    pen.line(472, 238, 540, 238, STROKE, 7)     # output shaft

    rotation_mark(pen, 128, 164, r=20)
    rotation_mark(pen, 506, 238, r=20)

    feet(pen, 152, 480, 286)
    pen.dot(176, 164)
    pen.dot(456, 238)


def draw_generic(pen: Pen) -> None:
    """The stand-in for machine types with no model of their own.

    Deliberately drawn dashed and featureless: it must not read as a drawing of
    the operator's actual asset.
    """
    pen.centreline(90, 550)
    pen.ground(150, 490)

    x1, y1, x2, y2 = 186, 132, 454, 276
    for a, b, c, d in ((x1, y1, x2, y1), (x2, y1, x2, y2), (x2, y2, x1, y2), (x1, y2, x1, y1)):
        pen.dashed(a, b, c, d, dash=16, gap=11, color=STROKE, w=LW)

    pen.circle(320, 204, 50, color=FAINT)
    pen.circle(320, 204, 16, color=FAINT, w=2)
    pen.line(120, 204, 186, 204, STROKE, 6)
    pen.line(454, 204, 520, 204, STROKE, 6)

    rotation_mark(pen, 152, 204, r=20)

    pen.dot(212, 152)
    pen.dot(428, 152)


FAMILIES = {
    "motor": draw_motor,
    "pump": draw_pump,
    "fan": draw_fan,
    "blower": draw_blower,
    "compressor": draw_compressor,
    "gearbox": draw_gearbox,
    "generic": draw_generic,
}


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    for name, drawer in FAMILIES.items():
        # Transparent, so the stage's own themed backdrop shows through.
        canvas = Image.new("RGBA", (W * SS, H * SS), (0, 0, 0, 0))
        drawer(Pen(ImageDraw.Draw(canvas)))
        canvas.resize((W, H), Image.LANCZOS).save(
            os.path.join(OUT_DIR, f"{name}.png"), optimize=True
        )
        print(f"  {name}.png")

    print(f"\n{len(FAMILIES)} previews written to {OUT_DIR}")


if __name__ == "__main__":
    main()
