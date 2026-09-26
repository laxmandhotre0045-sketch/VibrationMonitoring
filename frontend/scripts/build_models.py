"""Generate parametric machine GLBs for the Sensovibe digital-twin viewer.

Conventions (see docs/digital-twin-models.md):
  * metres, Y up, X = shaft axis (drive end toward +X), Z = horizontal cross-axis
  * origin at floor level, centred on the machine
  * SNS_<LOCATION>_<H|V|A>  sensor anchor, local +Y along the measurement axis
  * BRG_<LOCATION>          bearing anchor at the bearing centre
  * CASING_*                meshes that fade in x-ray mode
  * ROTOR                   parent node for everything that rotates
"""
from __future__ import annotations

import os
import numpy as np
import trimesh
from trimesh.creation import box as _box, cylinder as _cyl, annulus as _ann, icosphere
from trimesh.visual.material import PBRMaterial
from trimesh.visual import TextureVisuals

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "public", "models")

# ---------------------------------------------------------------- materials
def M(color, metal=0.2, rough=0.5):
    return PBRMaterial(baseColorFactor=list(color) + [1.0],
                       metallicFactor=float(metal), roughnessFactor=float(rough))

MOTOR_BLUE = M((0.17, 0.30, 0.49), 0.15, 0.40)
DARK       = M((0.12, 0.17, 0.25), 0.20, 0.48)
CAST       = M((0.37, 0.43, 0.51), 0.25, 0.52)
PAINT_GRN  = M((0.16, 0.36, 0.30), 0.15, 0.45)
PAINT_RED  = M((0.45, 0.16, 0.13), 0.15, 0.45)
LIGHT      = M((0.70, 0.74, 0.79), 0.35, 0.38)
STEEL      = M((0.78, 0.80, 0.83), 0.92, 0.22)
IRON       = M((0.19, 0.21, 0.24), 0.60, 0.60)
COPPER     = M((0.75, 0.45, 0.22), 0.90, 0.32)
RUBBER     = M((0.09, 0.10, 0.11), 0.00, 0.85)
BASE       = M((0.27, 0.30, 0.37), 0.30, 0.62)
PLINTH     = M((0.35, 0.39, 0.46), 0.25, 0.58)
SENSOR     = M((0.85, 0.87, 0.89), 0.90, 0.22)
BRG_MAT    = M((0.82, 0.84, 0.87), 0.90, 0.25)

# ---------------------------------------------------------------- transforms
def T(x=0.0, y=0.0, z=0.0):
    m = np.eye(4); m[:3, 3] = (x, y, z); return m

def R(axis, deg):
    return trimesh.transformations.rotation_matrix(np.radians(deg), axis)

def aim(direction):
    """Rotation taking local +Y onto `direction`."""
    d = np.asarray(direction, dtype=float)
    return trimesh.geometry.align_vectors([0, 1, 0], d / np.linalg.norm(d))

# ---------------------------------------------------------------- primitives
def cylx(r, length, sections=48):
    """Cylinder along X."""
    return _cyl(radius=r, height=length, sections=sections, transform=R([0, 1, 0], 90))

def cyly(r, length, sections=32):
    return _cyl(radius=r, height=length, sections=sections)

def cylz(r, length, sections=32):
    return _cyl(radius=r, height=length, sections=sections, transform=R([1, 0, 0], 90))

def tubex(r_out, r_in, length, sections=48):
    return _ann(r_min=r_in, r_max=r_out, height=length, sections=sections,
                transform=R([0, 1, 0], 90))

def bx(w, h, d):
    return _box((w, h, d))


class Builder:
    """Collects named meshes into one scene, then exports a GLB."""

    def __init__(self, name, rotor_xf=None):
        """`rotor_xf` orients the ROTOR node for a machine whose shaft is not
        along X — a top-entry mixer, say.

        The viewer spins ROTOR on its local X. Rotating the node so that local X
        points up is what makes a vertical shaft turn about its own axis instead
        of swinging around the model. Meshes are baked in world coordinates, so
        anything parented to a rotated ROTOR is pre-multiplied by the inverse
        below — otherwise the node's own rotation would move it twice.
        """
        self.name = name
        self.scene = trimesh.Scene()
        self.rotor_xf = np.eye(4) if rotor_xf is None else rotor_xf
        self.rotor_inv = np.linalg.inv(self.rotor_xf)
        self.scene.graph.update(frame_to="ROTOR", frame_from="world",
                                matrix=self.rotor_xf)
        self._n = 0
        self.sensors, self.bearings = [], []

    def add(self, mesh, mat, name=None, xf=None, casing=False, rotor=False, node_xf=None):
        """node_xf keeps the placement on the scene-graph node instead of baking it
        into the vertices, so a consumer can read the anchor's world transform."""
        self._n += 1
        mesh = mesh.copy()
        if xf is not None:
            mesh.apply_transform(xf)
        mesh.visual = TextureVisuals(material=mat)
        node = name or ("CASING_%03d" % self._n if casing else "PART_%03d" % self._n)
        self.scene.add_geometry(mesh, node_name=node, geom_name=node.lower(),
                                transform=node_xf,
                                parent_node_name="ROTOR" if rotor else "world")
        return node

    def casing(self, mesh, mat, xf=None, tag="SHELL"):
        return self.add(mesh, mat, name="CASING_%s_%03d" % (tag, self._n + 1), xf=xf, casing=True)

    def rot(self, mesh, mat, xf=None):
        placed = np.eye(4) if xf is None else xf
        return self.add(mesh, mat, xf=self.rotor_inv @ placed, rotor=True)

    # -- anchors ---------------------------------------------------------
    def sensor(self, loc, axis, point, direction):
        node = "SNS_%s_%s" % (loc, axis)
        stud = cyly(0.020, 0.012).apply_translation([0, 0.006, 0])
        body = cyly(0.016, 0.042).apply_translation([0, 0.033, 0])
        cap = cyly(0.011, 0.016).apply_translation([0, 0.062, 0])
        mesh = trimesh.util.concatenate([stud, body, cap])
        xf = aim(direction); xf[:3, 3] = point
        self.add(mesh, SENSOR, name=node, node_xf=xf)
        self.sensors.append((node, tuple(np.round(point, 4)), axis))
        return node

    def bearing(self, loc, x, r_out=0.085, r_in=0.035, w=0.05, y=None, z=0.0, axis="x"):
        node = "BRG_%s" % loc
        ring = tubex(r_out, r_in, w) if axis == "x" else _ann(
            r_min=r_in, r_max=r_out, height=w, sections=48)
        y = self.shaft_y if y is None else y
        self.add(ring, BRG_MAT, name=node, node_xf=T(x, y, z))
        self.bearings.append((node, (round(x, 4), round(y, 4), round(z, 4))))
        return node

    def triad(self, loc, x, y, z=0.0, r=0.085, axial_dir=1, axial_x=None):
        """Three standard mounting points on one bearing housing."""
        self.sensor(loc, "H", (x, y, z + r), (0, 0, 1))
        self.sensor(loc, "V", (x, y + r, z), (0, 1, 0))
        ax = x + axial_dir * r if axial_x is None else axial_x
        self.sensor(loc, "A", (ax, y + r * 0.55, z + r * 0.5), (axial_dir, 0, 0))

    def export(self):
        os.makedirs(OUT, exist_ok=True)
        path = os.path.join(OUT, self.name + ".glb")
        with open(path, "wb") as fh:
            fh.write(self.scene.export(file_type="glb"))
        return path


# ---------------------------------------------------------------- sub-assemblies
def baseplate(b, x0, x1, width=1.45, thick=0.075):
    # Remembered so add_standard_anchors() can put FOUNDATION on the plate
    # without every builder having to place it by hand.
    b.floor_y, b.base_span = thick, (x0, x1)
    L = x1 - x0
    b.add(bx(L, thick, width), BASE, xf=T((x0 + x1) / 2, thick / 2, 0))
    for x in (x0 + 0.12, x1 - 0.12):
        for z in (-width / 2 + 0.1, width / 2 - 0.1):
            b.add(_cyl(radius=0.028, height=0.026, sections=6), IRON, xf=T(x, thick + 0.012, z))
    return thick


def plinth(b, x, top_y, length, width=0.62, floor=0.075):
    h = top_y - floor
    if h <= 0.01:
        return
    b.add(bx(length, h, width), PLINTH, xf=T(x, floor + h / 2, 0))


def induction_motor(b, x_de, y, size=1.0, loc="MOTOR", floor=0.075, plinth_on=True):
    """Motor with its DE face at x_de, shaft pointing +X. Returns the shaft stub end x."""
    r = 0.28 * size
    L = 0.90 * size
    cx = x_de - L / 2
    sr = 0.040 * size

    b.casing(cylx(r, L, 64), MOTOR_BLUE, T(cx, y, 0), "MOTORBODY")
    b.casing(_cyl(radius=r, height=0.075, sections=64, transform=R([0, 1, 0], 90)),
             MOTOR_BLUE, T(x_de - 0.03, y, 0), "ENDBELL")
    b.casing(cylx(0.16 * size, 0.07, 48), MOTOR_BLUE, T(x_de + 0.04, y, 0), "ENDBELL")

    fins = []
    for i in range(36):
        a = i / 36 * 2 * np.pi
        deg = np.degrees(a) % 360
        if 238 < deg < 302 or 72 < deg < 108:
            continue
        f = bx(L * 0.92, 0.038 * size, 0.011)
        xf = R([1, 0, 0], np.degrees(a))
        f.apply_transform(xf)
        f.apply_translation([cx, y + np.cos(a) * r * 1.03, np.sin(a) * r * 1.03])
        fins.append(f)
    b.casing(trimesh.util.concatenate(fins), MOTOR_BLUE, None, "FINS")

    # cooling cowl, grille, terminal box, eyebolt, nameplate
    nde = cx - L / 2
    b.casing(cylx(r * 1.07, 0.32 * size, 64), DARK, T(nde - 0.16 * size, y, 0), "COWL")
    b.casing(tubex(r * 1.07, r * 0.85, 0.05, 48), DARK, T(nde - 0.33 * size, y, 0), "COWL")
    b.add(_ann(r_min=0.05, r_max=0.20 * size, height=0.008, sections=48,
               transform=R([0, 1, 0], 90)), IRON, xf=T(nde - 0.335 * size, y, 0))
    b.casing(bx(0.30 * size, 0.15 * size, 0.24 * size), MOTOR_BLUE,
             T(cx - 0.02, y + r + 0.075 * size, 0), "TERMBOX")
    b.add(bx(0.32 * size, 0.022, 0.26 * size), DARK, xf=T(cx - 0.02, y + r + 0.155 * size, 0))
    b.add(cylz(0.026, 0.07), IRON, xf=T(cx - 0.02, y + r + 0.07 * size, 0.14 * size))
    b.add(_cyl(radius=0.04, height=0.014, sections=24,
               transform=R([1, 0, 0], 90)), IRON, xf=T(cx + 0.30 * size, y + r + 0.02, 0))
    b.add(bx(0.19, 0.095, 0.005), LIGHT, xf=T(cx - 0.15, y, r + 0.004))

    # feet
    for z in (-0.235 * size, 0.235 * size):
        b.add(bx(L * 0.82, 0.05, 0.155), MOTOR_BLUE, xf=T(cx, y - r - 0.055 * size, z))
        b.add(bx(L * 0.78, 0.14 * size, 0.05), MOTOR_BLUE, xf=T(cx, y - r - 0.005, z * 0.86))
    if plinth_on:
        plinth(b, cx, y - r - 0.08 * size, L * 0.95, 0.60 * size, floor)

    # internals
    b.rot(cylx(sr, L * 1.75), STEEL, T(cx, y, 0))
    b.rot(cylx(0.155 * size, L * 0.66, 48), IRON, T(cx, y, 0))
    b.add(tubex(0.255 * size, 0.175 * size, L * 0.68, 48), IRON, xf=T(cx, y, 0))
    for dx in (-L * 0.36, L * 0.36):
        tor = trimesh.creation.torus(0.215 * size, 0.042 * size, major_sections=40, minor_sections=12)
        b.add(tor, COPPER, xf=T(cx + dx, y, 0) @ R([0, 1, 0], 90))
    blades = []
    for i in range(8):
        a = i / 8 * 2 * np.pi
        bl = bx(0.05, 0.16 * size, 0.008)
        bl.apply_transform(R([1, 0, 0], np.degrees(a)) @ R([0, 1, 0], 26))
        bl.apply_translation([0, np.cos(a) * 0.14 * size, np.sin(a) * 0.14 * size])
        blades.append(bl)
    b.rot(trimesh.util.concatenate(blades), RUBBER, T(nde - 0.18 * size, y, 0))
    b.rot(cylx(0.065 * size, 0.06), RUBBER, T(nde - 0.18 * size, y, 0))

    # shaft stub
    stub_end = x_de + 0.16 * size
    b.rot(cylx(sr, 0.20 * size), STEEL, T(x_de + 0.07 * size, y, 0))

    b.bearing(loc + "_DE", x_de - 0.02, 0.10 * size, sr, 0.05)
    b.bearing(loc + "_NDE", nde + 0.06, 0.10 * size, sr, 0.05)
    b.triad(loc + "_DE", x_de - 0.02, y, r=0.10 * size, axial_dir=1)
    b.triad(loc + "_NDE", nde + 0.06, y, r=0.10 * size, axial_dir=-1)
    return stub_end


def coupling(b, x, y, r=0.115, guard=True):
    b.rot(cylx(0.070, 0.10), DARK, T(x - 0.10, y, 0))
    b.rot(cylx(r, 0.036, 48), DARK, T(x - 0.032, y, 0))
    b.rot(cylx(r * 0.90, 0.030, 48), M((0.95, 0.42, 0.10), 0.3, 0.45), T(x, y, 0))
    b.rot(cylx(r, 0.036, 48), DARK, T(x + 0.032, y, 0))
    b.rot(cylx(0.070, 0.10), DARK, T(x + 0.10, y, 0))
    for i in range(6):
        a = i / 6 * 2 * np.pi
        b.rot(cylx(0.011, 0.125, 8), STEEL, T(x, y + np.cos(a) * r * 0.78, np.sin(a) * r * 0.78))
    if guard:
        b.casing(tubex(r * 1.5, r * 1.42, 0.30, 32), LIGHT, T(x, y, 0), "GUARD")


def pillow_block(b, x, y, loc, shaft_r=0.045, r=0.125, floor=0.075, axial_dir=1, plinth_on=True):
    s = trimesh.creation.cylinder(radius=r, height=0.20, sections=48, transform=R([1, 0, 0], 90))
    b.casing(s, CAST, T(x, y, 0), "PILLOW")
    b.casing(bx(0.20, 0.30, 0.22), CAST, T(x, y - 0.15, 0), "PILLOW")
    b.casing(bx(0.54, 0.07, 0.22), CAST, T(x, y - 0.295, 0), "PILLOW")
    for z in (-0.20, 0.20):
        b.add(_cyl(radius=0.022, height=0.03, sections=6), IRON, xf=T(x, y - 0.32, z))
    b.add(cyly(0.011, 0.035), COPPER, xf=T(x + 0.06, y + r + 0.015, 0))
    if plinth_on:
        plinth(b, x, y - 0.33, 0.34, 0.60, floor)
    b.bearing(loc, x, r * 0.98, shaft_r, 0.075)
    b.triad(loc, x, y, r=r, axial_dir=axial_dir)


def volute(b, x0, x1, y, r_in, r_out, mat, tag="VOLUTE", outlet="up", eye_r=None):
    """Logarithmic scroll casing between x0 and x1, cut-water at the top."""
    eye_r = eye_r or r_in * 0.55
    top = r_out * 1.28
    a0 = np.arccos(min(1.0, eye_r * 0.9 / r_in))
    pts = [(eye_r * 0.9, top)]
    n = 90
    for i in range(n + 1):
        t = i / n
        a = a0 + t * (2 * np.pi - a0)
        r = r_in + (r_out - r_in) * t
        pts.append((r * np.cos(a), r * np.sin(a)))
    pts.append((r_out, top))
    P = np.array(pts)

    v, f = [], []
    for k, (px, py) in enumerate(P):
        v.append([x0, py + y, -px]); v.append([x1, py + y, -px])
    for k in range(len(P) - 1):
        q = 2 * k
        f += [[q, q + 1, q + 2], [q + 1, q + 3, q + 2]]
    wall = trimesh.Trimesh(vertices=np.array(v), faces=np.array(f))
    b.casing(wall, mat, None, tag)

    # side plates as extruded polygons.
    # Polygon lives in (px, py); map px -> -Z, py -> +Y, extrusion -> +X.
    from shapely.geometry import Polygon
    PLATE = np.array([[0, 0, 1, 0], [0, 1, 0, 0], [-1, 0, 0, 0], [0, 0, 0, 1]], dtype=float)
    ring = Polygon(P)
    if not ring.is_valid:
        ring = ring.buffer(0)
    for xx, hole in ((x0 - 0.014, eye_r * 0.32), (x1, eye_r)):
        cut = Polygon([(np.cos(t) * hole, np.sin(t) * hole)
                       for t in np.linspace(0, 2 * np.pi, 56, endpoint=False)])
        poly = ring.difference(cut)
        plate = trimesh.creation.extrude_polygon(poly, 0.014)
        plate.apply_transform(PLATE)
        plate.apply_translation([xx, y, 0])
        b.casing(plate, mat, None, tag)
    if outlet == "up":
        # Discharge duct: a short rectangular shell above the cut-water.
        z_lo, z_hi = -r_out, -eye_r * 0.9
        w = z_hi - z_lo
        cz = (z_lo + z_hi) / 2
        span = x1 - x0
        for dz in (z_lo - 0.012, z_hi + 0.012):
            b.casing(bx(span + 0.05, 0.16, 0.024), mat, T((x0 + x1) / 2, y + top + 0.08, dz), tag)
        for dx in (x0 - 0.025, x1 + 0.025):
            b.casing(bx(0.024, 0.16, w + 0.05), mat, T(dx, y + top + 0.08, cz), tag)
        b.casing(bx(span + 0.13, 0.026, w + 0.13), mat, T((x0 + x1) / 2, y + top + 0.17, cz), tag)
        top = top + 0.19
    return top


def impeller(b, x, y, r_hub, r_tip, width, blades=10, back_curved=True, mat=None):
    mat = mat or LIGHT
    b.rot(cylx(r_tip * 0.96, 0.014, 64), mat, T(x - width / 2, y, 0))
    b.rot(cylx(r_hub * 0.55, 0.16), DARK, T(x - width / 2 + 0.08, y, 0))
    from shapely.geometry import Polygon
    for i in range(blades):
        outer, inner, m = [], [], 14
        for e in range(m + 1):
            s = e / m
            rr = r_hub + (r_tip - r_hub) * s
            aa = -s * (0.95 if back_curved else 0.25)
            d = 0.008 / rr
            outer.append((rr * np.cos(aa + d), rr * np.sin(aa + d)))
            inner.append((rr * np.cos(aa - d), rr * np.sin(aa - d)))
        poly = Polygon(outer + inner[::-1])
        if not poly.is_valid:
            poly = poly.buffer(0)
        bl = trimesh.creation.extrude_polygon(poly, width * 0.9)
        bl.apply_transform(R([0, 1, 0], 90) @ R([0, 0, 1], -90))
        bl.apply_transform(R([1, 0, 0], i / blades * 360))
        bl.apply_translation([x - width / 2, y, 0])
        b.rot(bl, mat)
    b.rot(_ann(r_min=r_tip * 0.58, r_max=r_tip * 0.96, height=0.012, sections=64,
               transform=R([0, 1, 0], 90)), mat, T(x + width / 2, y, 0))



# ---------------------------------------------------------------- standard anchors
#: Casing mounting points, per model: (x, y_offset_from_shaft, radius).
#: These are the Step 5 locations that sit on a housing rather than a bearing —
#: "Pump Casing", "Fan Housing", "Compressor Housing" — and without them a
#: sensor mounted there has nowhere to land on the model.
CASING_ANCHORS = {
    "pump": ("PUMP_CASING", 0.57, 0.0, 0.40),
    "fan": ("FAN_HOUSING", 0.80, 0.0, 0.70),
    "blower": ("BLOWER_HOUSING", 0.85, 0.0, 0.48),
    "compressor": ("COMP_HOUSING", 0.05, 0.0, 0.30),
    "gearbox": ("GB_HOUSING", 0.0, -0.24, 0.42),
    "machine-train": ("DRIVEN_HOUSING", 1.72, 0.0, 0.42),
    "turbine": ("TURB_CASING", -1.05, 0.0, 0.54),
    "dg-set": ("ENGINE_BLOCK", -1.10, -0.06, 0.40),
    "spindle": ("SPINDLE_HOUSING", 0.10, 0.0, 0.14),
    "wind-turbine-drivetrain": ("GB_HOUSING", 0.20, -0.02, 0.56),
    "motor": ("MOTOR_HOUSING", None, 0.0, 0.32),
    "generator": ("GEN_HOUSING", -0.35, 0.0, 0.48),
    "conveyor": ("CONV_FRAME", 0.0, -0.20, 0.62),
    "crusher": ("CRSH_HOUSING", 0.0, -0.30, 0.76),
    "mixer": ("MIX_HOUSING", 0.0, -1.05, 0.94),
    "agitator": ("MIX_HOUSING", 0.0, -1.00, 0.80),
}


def add_standard_anchors(b):
    """FOUNDATION, and the casing point this machine type offers in Step 5.

    Foundation is a static mounting point — there is no rotating axis under it,
    so H/V/A are read off the world axes rather than a shaft. It goes on the
    baseplate at the machine's centre, which is where an operator would put a
    magnet-mounted probe to check whether the whole skid is moving.
    """
    floor_y = getattr(b, "floor_y", 0.06)
    x0, x1 = getattr(b, "base_span", (-0.5, 0.5))
    cx = (x0 + x1) / 2

    b.sensor("FOUNDATION", "V", (cx, floor_y, 0.0), (0, 1, 0))
    b.sensor("FOUNDATION", "H", (cx, floor_y + 0.03, 0.22), (0, 0, 1))
    b.sensor("FOUNDATION", "A", (cx + 0.22, floor_y + 0.03, 0.0), (1, 0, 0))

    spec = CASING_ANCHORS.get(b.name)
    if spec:
        loc, x, dy, r = spec
        x = cx if x is None else x
        b.triad(loc, x, b.shaft_y + dy, r=r, axial_dir=1)


# ---------------------------------------------------------------- machines
def build_motor():
    b = Builder("motor"); b.shaft_y = 0.62
    floor = baseplate(b, -1.35, 0.75, 1.05)
    induction_motor(b, 0.30, b.shaft_y, 1.15, "MOTOR", floor)
    return b


def build_pump():
    b = Builder("pump"); y = b.shaft_y = 0.66
    floor = baseplate(b, -2.15, 1.45, 1.40)
    induction_motor(b, -0.75, y, 1.05, "MOTOR", floor)
    coupling(b, -0.50, y)
    # pump: bearing frame + volute casing, end-suction
    b.rot(cylx(0.042, 1.30), STEEL, T(0.25, y, 0))
    b.casing(bx(0.62, 0.30, 0.30), CAST, T(-0.05, y, 0), "FRAME")
    pillow_block(b, -0.20, y, "PUMP_NDE", 0.042, 0.115, floor, -1, False)
    pillow_block(b, 0.16, y, "PUMP_DE", 0.042, 0.115, floor, 1, False)
    plinth(b, -0.02, y - 0.33, 0.78, 0.60, floor)
    top = volute(b, 0.42, 0.72, y, 0.26, 0.40, CAST, "VOLUTE", "up", 0.15)
    impeller(b, 0.57, y, 0.11, 0.245, 0.24, 7, True, LIGHT)
    b.casing(trimesh.creation.cylinder(radius=0.165, height=0.16, sections=48,
             transform=R([0, 1, 0], 90)), CAST, T(0.80, y, 0), "SUCTION")
    b.casing(cylx(0.20, 0.03, 48), CAST, T(0.885, y, 0), "SUCTION")
    b.casing(cyly(0.115, 0.14), CAST, T(0.57, y + top + 0.07, -0.33), "DISCHARGE")
    b.casing(cyly(0.15, 0.028), CAST, T(0.57, y + top + 0.15, -0.33), "DISCHARGE")
    return b


def build_fan():
    b = Builder("fan"); y = b.shaft_y = 0.80
    floor = baseplate(b, -2.35, 1.85, 1.50)
    induction_motor(b, -1.05, y, 1.15, "MOTOR", floor)
    coupling(b, -0.78, y)
    b.rot(cylx(0.045, 1.75), STEEL, T(0.30, y, 0))
    pillow_block(b, -0.42, y, "FAN_NDE", 0.045, 0.125, floor, -1)
    pillow_block(b, 0.18, y, "FAN_DE", 0.045, 0.125, floor, 1)
    volute(b, 0.55, 1.05, y, 0.42, 0.70, LIGHT, "FANHOUSING", "up", 0.30)
    impeller(b, 0.80, y, 0.16, 0.37, 0.42, 10, True, LIGHT)
    b.casing(trimesh.creation.cylinder(radius=0.32, height=0.14, sections=64,
             transform=R([0, 1, 0], 90)), LIGHT, T(1.12, y, 0), "INLET")
    return b


def build_blower():
    b = Builder("blower"); y = b.shaft_y = 0.74
    floor = baseplate(b, -2.20, 1.55, 1.40)
    induction_motor(b, -0.95, y, 1.05, "MOTOR", floor)
    # belt drive, the usual blower arrangement
    b.rot(cylx(0.145, 0.06, 48), IRON, T(-0.72, y, 0))
    b.rot(cylx(0.225, 0.06, 48), IRON, T(0.62, y, 0))
    for zz in (-0.022, 0.022):
        belt = trimesh.creation.box((1.38, 0.055, 0.016))
        b.casing(belt, RUBBER, T(-0.05, y + 0.19, zz), "BELT")
        b.casing(trimesh.creation.box((1.38, 0.055, 0.016)), RUBBER,
                 T(-0.05, y - 0.19, zz), "BELT")
    b.casing(bx(1.52, 0.54, 0.035), LIGHT, T(-0.05, y, 0.145), "BELTGUARD")
    for dy in (-0.27, 0.27):
        b.casing(bx(1.52, 0.035, 0.26), LIGHT, T(-0.05, y + dy, 0.03), "BELTGUARD")
    b.rot(cylx(0.045, 1.15), STEEL, T(0.30, y, 0))
    pillow_block(b, 0.10, y, "BLOWER_NDE", 0.045, 0.118, floor, -1)
    pillow_block(b, 0.42, y, "BLOWER_DE", 0.045, 0.118, floor, 1)
    volute(b, 0.70, 1.00, y, 0.30, 0.48, PAINT_GRN, "BLOWERHOUSING", "up", 0.20)
    impeller(b, 0.85, y, 0.11, 0.26, 0.24, 12, False, LIGHT)
    b.casing(trimesh.creation.cylinder(radius=0.21, height=0.12, sections=48,
             transform=R([0, 1, 0], 90)), PAINT_GRN, T(1.06, y, 0), "INLET")
    return b


def build_compressor():
    b = Builder("compressor"); y = b.shaft_y = 0.70
    floor = baseplate(b, -2.20, 1.60, 1.45)
    induction_motor(b, -0.80, y, 1.10, "MOTOR", floor)
    coupling(b, -0.55, y)
    # twin-screw airend
    b.casing(bx(0.86, 0.52, 0.52), CAST, T(0.05, y, 0), "AIREND")
    b.casing(cylx(0.20, 0.88, 48), CAST, T(0.05, y + 0.10, 0), "AIREND")
    b.casing(cylx(0.20, 0.88, 48), CAST, T(0.05, y - 0.10, 0), "AIREND")
    b.casing(cylx(0.27, 0.06, 48), CAST, T(0.50, y + 0.10, 0), "AIREND")
    plinth(b, 0.05, y - 0.32, 0.90, 0.62, floor)
    for dy, tag in ((0.10, "MALE"), (-0.10, "FEMALE")):
        b.rot(cylx(0.040, 1.05), STEEL, T(0.05, y + dy, 0))
        lobes = []
        for i in range(4 if dy > 0 else 6):
            a = i / (4 if dy > 0 else 6) * 2 * np.pi
            lb = cylx(0.055, 0.72, 16)
            lb.apply_translation([0.05, y + dy + np.cos(a) * 0.115, np.sin(a) * 0.115])
            lobes.append(lb)
        b.rot(trimesh.util.concatenate(lobes), STEEL)
        b.rot(cylx(0.09, 0.72, 32), IRON, T(0.05, y + dy, 0))
    b.bearing("COMP_DE", 0.44, 0.10, 0.04, 0.05, y + 0.10)
    b.bearing("COMP_NDE", -0.34, 0.10, 0.04, 0.05, y + 0.10)
    b.triad("COMP_DE", 0.44, y + 0.10, r=0.26, axial_dir=1)
    b.triad("COMP_NDE", -0.34, y + 0.10, r=0.26, axial_dir=-1)
    # air-end discharge and separator
    b.casing(cyly(0.20, 0.80), PAINT_RED, T(0.95, y + 0.10, 0), "SEPARATOR")
    b.casing(cyly(0.235, 0.05), PAINT_RED, T(0.95, y + 0.52, 0), "SEPARATOR")
    b.casing(cylz(0.055, 0.44), CAST, T(0.62, y + 0.22, 0), "PIPE")
    return b


def build_gearbox():
    b = Builder("gearbox"); y = b.shaft_y = 0.72
    floor = baseplate(b, -1.25, 1.25, 1.30)
    hy = y - 0.24
    b.casing(bx(0.92, 0.80, 0.66), PAINT_GRN, T(0.0, hy + 0.10, 0), "HOUSING")
    b.casing(bx(0.98, 0.05, 0.72), PAINT_GRN, T(0.0, hy + 0.52, 0), "SPLITLINE")
    b.casing(bx(1.10, 0.09, 0.80), PAINT_GRN, T(0.0, floor + 0.045, 0), "FOOT")
    for x in (-0.46, 0.46):
        b.casing(bx(0.06, 0.60, 0.70), PAINT_GRN, T(x, hy + 0.12, 0), "HOUSING")
    for i, x in enumerate((-0.30, 0.30)):
        for z in (-0.30, 0.30):
            b.add(_cyl(radius=0.018, height=0.026, sections=6), IRON, xf=T(x, hy + 0.545, z))
    b.add(cyly(0.032, 0.09), COPPER, xf=T(0.0, hy + 0.60, 0.22))          # breather
    b.add(cyly(0.028, 0.07), LIGHT, xf=T(-0.40, hy + 0.05, 0.34))          # sight glass
    # input (high speed) and output (low speed) shafts
    b.rot(cylx(0.038, 1.55), STEEL, T(-0.10, y, 0))
    b.rot(cylx(0.060, 1.30), STEEL, T(0.10, hy - 0.18, 0))
    b.rot(cylx(0.085, 0.16, 40), IRON, T(0.0, y, 0))                       # pinion
    b.rot(cylx(0.300, 0.18, 64), IRON, T(0.0, hy - 0.18, 0))               # wheel
    teeth = []
    for i in range(46):
        a = i / 46 * 2 * np.pi
        t = bx(0.16, 0.030, 0.022)
        t.apply_transform(R([1, 0, 0], np.degrees(a)))
        t.apply_translation([0, hy - 0.18 + np.cos(a) * 0.312, np.sin(a) * 0.312])
        teeth.append(t)
    b.rot(trimesh.util.concatenate(teeth), IRON)
    b.bearing("GB_HSS_DE", 0.42, 0.095, 0.038, 0.05, y)
    b.bearing("GB_HSS_NDE", -0.42, 0.095, 0.038, 0.05, y)
    b.bearing("GB_LSS_DE", 0.42, 0.125, 0.060, 0.06, hy - 0.18)
    b.bearing("GB_LSS_NDE", -0.42, 0.125, 0.060, 0.06, hy - 0.18)
    b.triad("GB_HSS_DE", 0.44, y, r=0.10, axial_dir=1)
    b.triad("GB_HSS_NDE", -0.44, y, r=0.10, axial_dir=-1)
    b.triad("GB_LSS_DE", 0.44, hy - 0.18, r=0.13, axial_dir=1)
    b.triad("GB_LSS_NDE", -0.44, hy - 0.18, r=0.13, axial_dir=-1)
    return b


def build_spindle():
    b = Builder("spindle"); y = b.shaft_y = 0.42
    b.add(bx(1.10, 0.06, 0.60), BASE, xf=T(0.0, 0.03, 0))
    b.casing(bx(0.34, 0.50, 0.46), CAST, T(-0.38, y, 0), "HEADSTOCK")
    b.casing(cylx(0.105, 0.78, 64), LIGHT, T(0.10, y, 0), "CARTRIDGE")
    b.casing(cylx(0.125, 0.07, 64), LIGHT, T(-0.26, y, 0), "CARTRIDGE")
    b.casing(cylx(0.135, 0.05, 64), LIGHT, T(0.46, y, 0), "NOSE")
    for i in range(8):
        a = i / 8 * 2 * np.pi
        b.add(_cyl(radius=0.008, height=0.014, sections=6),
              IRON, xf=T(0.485, y + np.cos(a) * 0.10, np.sin(a) * 0.10))
    b.add(bx(0.20, 0.06, 0.05), DARK, xf=T(-0.30, y + 0.26, 0))            # coolant union
    b.add(cylz(0.016, 0.12), RUBBER, xf=T(-0.42, y + 0.20, 0.20))
    # rotor, tool taper, angular-contact pairs
    b.rot(cylx(0.038, 0.92), STEEL, T(0.10, y, 0))
    b.rot(cylx(0.085, 0.22, 48), IRON, T(-0.20, y, 0))                     # motor rotor
    b.add(tubex(0.125, 0.095, 0.24, 48), IRON, xf=T(-0.20, y, 0))          # stator
    taper = trimesh.creation.cone(radius=0.055, height=0.11, sections=40,
                                  transform=R([0, 1, 0], -90))
    b.rot(taper, STEEL, T(0.50, y, 0))
    b.bearing("SPINDLE_FRONT", 0.40, 0.075, 0.038, 0.048)
    b.bearing("SPINDLE_FRONT2", 0.32, 0.075, 0.038, 0.048)
    b.bearing("SPINDLE_REAR", -0.14, 0.070, 0.035, 0.042)
    b.triad("SPINDLE_FRONT", 0.40, y, r=0.105, axial_dir=1)
    b.triad("SPINDLE_REAR", -0.14, y, r=0.105, axial_dir=-1)
    return b


def build_turbine():
    b = Builder("turbine"); y = b.shaft_y = 0.95
    floor = baseplate(b, -2.60, 2.60, 1.80)
    # steam turbine casing: barrel with a split line and inlet/exhaust
    b.casing(cylx(0.52, 1.30, 64), PAINT_GRN, T(-1.05, y, 0), "TURBCASE")
    b.casing(cylx(0.40, 0.20, 64), PAINT_GRN, T(-1.80, y, 0), "TURBCASE")
    b.casing(bx(1.36, 0.05, 1.10), PAINT_GRN, T(-1.05, y, 0), "SPLITLINE")
    for i in range(10):
        b.add(_cyl(radius=0.022, height=0.05, sections=6), IRON,
              xf=T(-1.62 + i * 0.13, y + 0.02, 0.52))
    b.casing(cyly(0.24, 0.42), PAINT_GRN, T(-1.35, y + 0.62, 0), "INLET")
    b.casing(cyly(0.28, 0.04), PAINT_GRN, T(-1.35, y + 0.84, 0), "INLET")
    b.casing(cyly(0.36, 0.40), PAINT_GRN, T(-0.70, y - 0.68, 0), "EXHAUST")
    b.casing(bx(0.70, 0.12, 0.90), CAST, T(-1.05, floor + 0.06, 0), "PEDESTAL")
    # rotor with staged discs and blading
    b.rot(cylx(0.075, 3.40), STEEL, T(-0.60, y, 0))
    for i, (dx, rr) in enumerate(((-1.52, 0.28), (-1.26, 0.31), (-1.00, 0.35),
                                  (-0.74, 0.39), (-0.48, 0.43))):
        b.rot(cylx(rr, 0.045, 64), IRON, T(dx, y, 0))
        bl = []
        for k in range(44):
            a = k / 44 * 2 * np.pi
            v = bx(0.038, 0.085, 0.012)
            v.apply_transform(R([1, 0, 0], np.degrees(a)) @ R([0, 1, 0], 32))
            v.apply_translation([dx, np.cos(a) * (rr + 0.045) + y, np.sin(a) * (rr + 0.045)])
            bl.append(v)
        b.rot(trimesh.util.concatenate(bl), LIGHT)
    coupling(b, 0.25, y, 0.145)
    # driven generator
    b.casing(cylx(0.46, 1.30, 64), MOTOR_BLUE, T(1.30, y, 0), "GENCASE")
    b.casing(bx(1.40, 0.10, 1.00), MOTOR_BLUE, T(1.30, y - 0.50, 0), "GENFOOT")
    b.casing(bx(0.40, 0.26, 0.34), MOTOR_BLUE, T(1.30, y + 0.55, 0), "TERMBOX")
    b.rot(cylx(0.26, 1.00, 48), IRON, T(1.30, y, 0))
    plinth(b, 1.30, y - 0.55, 1.45, 1.00, floor)
    for loc, x, d in (("TURB_NDE", -1.86, -1), ("TURB_DE", -0.24, 1),
                      ("GEN_DE", 0.62, -1), ("GEN_NDE", 1.98, 1)):
        rr = 0.42 if "TURB" in loc else 0.46
        b.bearing(loc, x, 0.16, 0.075, 0.09)
        b.triad(loc, x, y, r=rr, axial_dir=d)
    return b


def build_wind_drivetrain():
    b = Builder("wind-turbine-drivetrain"); y = b.shaft_y = 0.95
    # bedplate inside the nacelle
    b.add(bx(4.40, 0.14, 1.70), BASE, xf=T(0.30, 0.07, 0))
    for x in (-1.40, 1.60):
        b.add(bx(0.20, 0.34, 1.50), BASE, xf=T(x, 0.31, 0))
    # rotor hub and main shaft
    b.rot(cylx(0.075, 0.30, 48), IRON, T(-1.95, y, 0))
    hub = icosphere(subdivisions=2, radius=0.42)
    b.rot(hub, LIGHT, T(-2.30, y, 0))
    for i in range(3):
        a = i / 3 * 2 * np.pi
        root = cylx(0.16, 0.34, 32)
        root.apply_transform(R([1, 0, 0], np.degrees(a)))
        root.apply_translation([-2.42, y + np.cos(a) * 0.42, np.sin(a) * 0.42])
        b.rot(root, LIGHT)
    b.rot(cylx(0.145, 1.35), STEEL, T(-1.35, y, 0))
    # main bearing
    b.casing(trimesh.creation.cylinder(radius=0.34, height=0.34, sections=48,
             transform=R([1, 0, 0], 90)), CAST, T(-1.80, y, 0), "MAINBRG")
    b.casing(bx(0.36, 0.52, 0.40), CAST, T(-1.80, y - 0.42, 0), "MAINBRG")
    b.bearing("MAIN_BRG", -1.80, 0.30, 0.145, 0.22)
    b.triad("MAIN_BRG", -1.80, y, r=0.34, axial_dir=-1)
    # three-stage gearbox: planetary can + helical housing
    b.casing(cylx(0.62, 0.52, 64), PAINT_GRN, T(-0.62, y, 0), "PLANETARY")
    b.casing(cylx(0.66, 0.06, 64), PAINT_GRN, T(-0.36, y, 0), "PLANETARY")
    b.casing(bx(1.10, 1.05, 1.05), PAINT_GRN, T(0.20, y - 0.02, 0), "GBHOUSING")
    b.casing(bx(1.16, 0.05, 1.12), PAINT_GRN, T(0.20, y + 0.30, 0), "SPLITLINE")
    for z in (-0.62, 0.62):                                   # torque arms
        b.casing(bx(0.42, 0.22, 0.20), CAST, T(0.20, y - 0.30, z), "TORQUEARM")
        b.add(cyly(0.10, 0.16), RUBBER, xf=T(0.20, y - 0.50, z))
    b.rot(cylx(0.085, 1.60), STEEL, T(0.55, y + 0.18, 0))     # high-speed shaft
    b.rot(cylx(0.26, 0.20, 48), IRON, T(0.30, y + 0.18, 0))
    b.rot(cylx(0.46, 0.22, 64), IRON, T(-0.10, y - 0.05, 0))
    b.bearing("GB_HSS_NDE", 0.62, 0.16, 0.085, 0.10, y + 0.18)
    b.bearing("GB_HSS_DE", 0.92, 0.16, 0.085, 0.10, y + 0.18)
    b.triad("GB_HSS_DE", 0.92, y + 0.18, r=0.30, axial_dir=1)
    b.triad("GB_HSS_NDE", 0.62, y + 0.18, r=0.30, axial_dir=-1)
    # brake disc and generator
    b.rot(cylx(0.34, 0.03, 64), STEEL, T(1.12, y + 0.18, 0))
    b.casing(bx(0.16, 0.30, 0.22), CAST, T(1.12, y + 0.48, 0), "BRAKE")
    coupling(b, 1.42, y + 0.18, 0.15)
    b.casing(cylx(0.46, 1.30, 64), MOTOR_BLUE, T(2.30, y + 0.18, 0), "GENCASE")
    b.casing(bx(1.40, 0.10, 0.98), MOTOR_BLUE, T(2.30, y - 0.32, 0), "GENFOOT")
    b.casing(cylx(0.40, 0.22, 48), DARK, T(3.06, y + 0.18, 0), "GENCOWL")
    b.rot(cylx(0.26, 1.00, 48), IRON, T(2.30, y + 0.18, 0))
    b.bearing("GEN_DE", 1.68, 0.14, 0.07, 0.08, y + 0.18)
    b.bearing("GEN_NDE", 2.94, 0.14, 0.07, 0.08, y + 0.18)
    b.triad("GEN_DE", 1.68, y + 0.18, r=0.46, axial_dir=-1)
    b.triad("GEN_NDE", 2.94, y + 0.18, r=0.46, axial_dir=1)
    return b


def build_dg_set():
    b = Builder("dg-set"); y = b.shaft_y = 0.72
    floor = baseplate(b, -2.70, 2.10, 1.60)
    # diesel engine block
    b.casing(bx(1.70, 0.62, 0.78), PAINT_RED, T(-1.10, y - 0.06, 0), "ENGINEBLOCK")
    b.casing(bx(1.55, 0.26, 0.60), PAINT_RED, T(-1.10, y + 0.38, 0), "HEAD")
    b.casing(bx(1.60, 0.10, 0.66), DARK, T(-1.10, y + 0.55, 0), "ROCKERCOVER")
    b.casing(bx(1.45, 0.24, 0.56), PAINT_RED, T(-1.10, y - 0.48, 0), "SUMP")
    for i in range(6):                                         # injectors + exhaust manifold
        b.add(cyly(0.028, 0.10), STEEL, xf=T(-1.78 + i * 0.27, y + 0.63, 0))
        b.add(cylz(0.045, 0.22), IRON, xf=T(-1.78 + i * 0.27, y + 0.34, 0.40))
    b.casing(cylx(0.075, 1.60, 32), IRON, T(-1.10, y + 0.34, 0.50), "MANIFOLD")
    b.casing(cylx(0.115, 0.34, 40), IRON, T(-0.20, y + 0.34, 0.46), "TURBO")
    b.casing(icosphere(subdivisions=2, radius=0.17), IRON, T(-0.02, y + 0.34, 0.46), "TURBO")
    b.casing(cyly(0.085, 0.70), IRON, T(-0.02, y + 0.78, 0.46), "EXHAUST")
    # radiator and fan
    b.casing(bx(0.16, 0.95, 0.95), DARK, T(-2.28, y + 0.10, 0), "RADIATOR")
    b.casing(bx(0.06, 1.05, 1.05), LIGHT, T(-2.37, y + 0.10, 0), "RADIATOR")
    b.rot(cylx(0.075, 0.10), DARK, T(-2.10, y + 0.10, 0))
    fb = []
    for i in range(6):
        a = i / 6 * 2 * np.pi
        v = bx(0.04, 0.34, 0.014)
        v.apply_transform(R([1, 0, 0], np.degrees(a)) @ R([0, 1, 0], 25))
        v.apply_translation([-2.10, y + 0.10 + np.cos(a) * 0.26, np.sin(a) * 0.26])
        fb.append(v)
    b.rot(trimesh.util.concatenate(fb), DARK)
    # flywheel housing, alternator
    b.casing(cylx(0.42, 0.28, 64), PAINT_RED, T(-0.10, y, 0), "FLYWHEELHSG")
    b.rot(cylx(0.34, 0.12, 64), IRON, T(-0.12, y, 0))
    b.rot(cylx(0.055, 2.20), STEEL, T(-0.60, y, 0))
    b.casing(cylx(0.44, 1.25, 64), MOTOR_BLUE, T(0.75, y, 0), "ALTCASE")
    b.casing(bx(1.35, 0.09, 0.95), MOTOR_BLUE, T(0.75, y - 0.47, 0), "ALTFOOT")
    b.casing(bx(0.42, 0.34, 0.40), MOTOR_BLUE, T(0.75, y + 0.58, 0), "TERMBOX")
    b.casing(cylx(0.38, 0.20, 48), DARK, T(1.48, y, 0), "ALTCOWL")
    b.rot(cylx(0.25, 0.95, 48), IRON, T(0.75, y, 0))
    plinth(b, 0.75, y - 0.50, 1.40, 0.95, floor)
    plinth(b, -1.10, y - 0.62, 1.70, 0.80, floor)
    for loc, x, d, r in (("ENGINE_DE", -0.26, -1, 0.42), ("ALT_DE", 0.16, -1, 0.44),
                         ("ALT_NDE", 1.34, 1, 0.44)):
        b.bearing(loc, x, 0.13, 0.055, 0.07)
        b.triad(loc, x, y, r=r, axial_dir=d)
    return b


def build_machine_train():
    """Generic critical machine: motor, gearbox, driven equipment on one base."""
    b = Builder("machine-train"); y = b.shaft_y = 0.78
    floor = baseplate(b, -2.70, 2.40, 1.55)
    induction_motor(b, -1.30, y, 1.10, "MOTOR", floor)
    coupling(b, -1.05, y)
    hy = y
    b.casing(bx(0.86, 0.74, 0.62), PAINT_GRN, T(-0.45, hy - 0.04, 0), "GBHOUSING")
    b.casing(bx(0.92, 0.05, 0.68), PAINT_GRN, T(-0.45, hy + 0.34, 0), "SPLITLINE")
    b.casing(bx(1.02, 0.09, 0.76), PAINT_GRN, T(-0.45, floor + 0.045, 0), "GBFOOT")
    b.add(cyly(0.030, 0.085), COPPER, xf=T(-0.45, hy + 0.40, 0.20))
    b.rot(cylx(0.042, 1.45), STEEL, T(-0.55, y, 0))
    b.rot(cylx(0.085, 0.14, 40), IRON, T(-0.55, y, 0))
    b.rot(cylx(0.235, 0.16, 64), IRON, T(-0.30, y - 0.02, 0))
    b.bearing("GB_IN_DE", -0.06, 0.10, 0.042, 0.05)
    b.bearing("GB_IN_NDE", -0.86, 0.10, 0.042, 0.05)
    b.triad("GB_IN_DE", -0.06, y, r=0.34, axial_dir=1)
    b.triad("GB_IN_NDE", -0.86, y, r=0.34, axial_dir=-1)
    coupling(b, 0.22, y, 0.13)
    b.rot(cylx(0.050, 1.90), STEEL, T(1.05, y, 0))
    pillow_block(b, 0.62, y, "DRIVEN_NDE", 0.050, 0.130, floor, -1)
    pillow_block(b, 1.20, y, "DRIVEN_DE", 0.050, 0.130, floor, 1)
    # driven body: a drum, which reads as conveyor / mixer / crusher rotor
    b.casing(cylx(0.40, 0.80, 64), LIGHT, T(1.72, y, 0), "DRUM")
    b.casing(cylx(0.44, 0.05, 64), LIGHT, T(1.34, y, 0), "DRUM")
    b.casing(cylx(0.44, 0.05, 64), LIGHT, T(2.10, y, 0), "DRUM")
    b.rot(cylx(0.34, 0.76, 48), IRON, T(1.72, y, 0))
    return b



def build_generator():
    """Standalone alternator: a machine on two bearings with an exciter at the
    non-drive end. Distinct from a motor — no cooling fins, a much bigger
    terminal box, and the cowl is the exciter rather than a fan shroud."""
    b = Builder("generator"); y = b.shaft_y = 0.74
    floor = baseplate(b, -1.85, 1.25, 1.35)
    b.casing(cylx(0.46, 1.35, 64), MOTOR_BLUE, T(-0.35, y, 0), "GENCASE")
    b.casing(bx(1.45, 0.10, 1.00), MOTOR_BLUE, T(-0.35, y - 0.51, 0), "GENFOOT")
    b.casing(bx(0.52, 0.38, 0.46), MOTOR_BLUE, T(-0.35, y + 0.58, 0), "TERMBOX")
    b.add(bx(0.54, 0.024, 0.48), DARK, xf=T(-0.35, y + 0.77, 0))
    b.casing(cylx(0.30, 0.34, 48), DARK, T(-1.18, y, 0), "EXCITER")
    b.casing(tubex(0.30, 0.22, 0.05, 48), DARK, T(-1.36, y, 0), "EXCITER")
    b.casing(cylx(0.32, 0.10, 48), MOTOR_BLUE, T(0.36, y, 0), "ENDBELL")
    for i in range(12):
        b.add(bx(0.03, 0.16, 0.012), DARK, xf=T(-0.90 + i * 0.09, y + 0.40, 0.22))
    b.add(bx(0.22, 0.10, 0.006), LIGHT, xf=T(-0.20, y + 0.20, 0.46))
    b.rot(cylx(0.28, 1.05, 48), IRON, T(-0.35, y, 0))
    b.rot(cylx(0.058, 2.20), STEEL, T(-0.35, y, 0))
    plinth(b, -0.35, y - 0.54, 1.50, 1.05, floor)
    b.bearing("GEN_DE", 0.34, 0.135, 0.058, 0.07)
    b.bearing("GEN_NDE", -1.02, 0.135, 0.058, 0.07)
    b.triad("GEN_DE", 0.34, y, r=0.46, axial_dir=1)
    b.triad("GEN_NDE", -1.02, y, r=0.46, axial_dir=-1)
    return b


def build_conveyor():
    """Belt conveyor. The belt runs along Z so the pulley shafts stay on X,
    which is where the convention puts a shaft axis."""
    b = Builder("conveyor"); y = b.shaft_y = 0.88
    b.floor_y, b.base_span = 0.0, (-0.9, 0.9)
    half, wide = 2.15, 0.52

    for x in (-wide - 0.06, wide + 0.06):
        b.add(bx(0.09, 0.11, 2 * half), BASE, xf=T(x, y + 0.30, 0))
        b.add(bx(0.09, 0.11, 2 * half), BASE, xf=T(x, y - 0.34, 0))
    for z in (-1.75, -0.6, 0.6, 1.75):
        for x in (-wide - 0.06, wide + 0.06):
            b.add(bx(0.08, y + 0.24, 0.08), BASE, xf=T(x, (y + 0.24) / 2, z))
    for z in np.arange(-1.55, 1.6, 0.52):
        b.rot(cylx(0.055, 2 * wide, 20), IRON, T(0.0, y + 0.30, float(z)))

    b.casing(bx(2 * wide, 0.022, 2 * half), RUBBER, T(0.0, y + 0.39, 0), "BELT")
    b.casing(bx(2 * wide, 0.022, 2 * half), RUBBER, T(0.0, y - 0.26, 0), "BELT")
    for zz in (half, -half):
        b.rot(cylx(0.30, 2 * wide + 0.06, 48), IRON, T(0.0, y + 0.07, zz))
        b.casing(bx(2 * wide + 0.34, 0.03, 0.34), LIGHT, T(0.0, y + 0.44, zz), "SKIRT")
        b.rot(cylx(0.055, 2 * wide + 0.70), STEEL, T(0.0, y + 0.07, zz))

    b.casing(bx(0.46, 0.46, 0.40), PAINT_GRN, T(wide + 0.46, y + 0.07, half), "GEARMOTOR")
    b.casing(cylx(0.20, 0.46, 48), MOTOR_BLUE, T(wide + 0.92, y + 0.07, half), "GEARMOTOR")
    b.casing(bx(0.26, 0.20, 0.22), CAST, T(wide + 0.30, y + 0.44, half), "TORQUEARM")

    b.bearing("PULLEY_DE", wide + 0.16, 0.10, 0.055, 0.06, y + 0.07, half)
    b.bearing("PULLEY_NDE", -wide - 0.16, 0.10, 0.055, 0.06, y + 0.07, half)
    b.bearing("TAIL_BRG", wide + 0.16, 0.10, 0.055, 0.06, y + 0.07, -half)
    b.triad("PULLEY_DE", wide + 0.16, y + 0.07, half, r=0.14, axial_dir=1)
    b.triad("PULLEY_NDE", -wide - 0.16, y + 0.07, half, r=0.14, axial_dir=-1)
    b.triad("TAIL_BRG", wide + 0.16, y + 0.07, -half, r=0.14, axial_dir=1)
    return b


def build_crusher():
    """Jaw crusher: the eccentric shaft carries a flywheel each side, and the
    frame is the heaviest thing on the skid."""
    b = Builder("crusher"); y = b.shaft_y = 1.05
    floor = baseplate(b, -1.85, 1.85, 1.90)
    b.casing(bx(1.55, 1.45, 1.35), CAST, T(0.0, y - 0.30, 0), "FRAME")
    b.casing(bx(1.70, 0.16, 1.50), CAST, T(0.0, floor + 0.08, 0), "FRAME")
    b.casing(bx(1.30, 0.34, 1.20), IRON, T(0.0, y + 0.52, 0), "FEEDHOPPER")
    for dz in (-0.73, 0.73):
        b.casing(bx(1.40, 0.44, 0.04), IRON, T(0.0, y + 0.74, dz), "FEEDHOPPER")
    b.add(bx(0.95, 0.90, 0.05), STEEL, xf=T(-0.22, y - 0.42, 0))
    b.rot(bx(0.10, 0.90, 1.05), STEEL, T(0.30, y - 0.42, 0))
    b.rot(cylx(0.095, 2.60), STEEL, T(0.0, y + 0.18, 0))
    b.rot(cylx(0.165, 0.34, 40), IRON, T(0.0, y + 0.18, 0))
    for dx in (-1.12, 1.12):
        b.rot(cylx(0.56, 0.11, 64), IRON, T(dx, y + 0.18, 0))
        b.rot(cylx(0.16, 0.16, 32), IRON, T(dx, y + 0.18, 0))
    b.casing(tubex(0.66, 0.60, 0.16, 48), LIGHT, T(1.12, y + 0.18, 0), "FLYGUARD")
    induction_motor(b, -1.15, y - 0.62, 0.88, "DRIVE", floor, False)
    plinth(b, -1.45, y - 1.02, 0.95, 0.60, floor)
    b.bearing("CRSH_DE", 0.86, 0.16, 0.095, 0.10, y + 0.18)
    b.bearing("CRSH_NDE", -0.86, 0.16, 0.095, 0.10, y + 0.18)
    b.triad("CRSH_DE", 0.86, y + 0.18, r=0.20, axial_dir=1)
    b.triad("CRSH_NDE", -0.86, y + 0.18, r=0.20, axial_dir=-1)
    return b


def _vertical_agitator(name, tank_r, tank_h, blades, pitched):
    """Top-entry agitator: motor and right-angle gearbox over a vessel, shaft
    straight down. ROTOR is turned so its local X points up, which is what makes
    the shaft spin about itself rather than swing around the model."""
    b = Builder(name, rotor_xf=R([0, 0, 1], 90))
    y_top = tank_h + 0.46
    b.shaft_y = y_top
    b.floor_y, b.base_span = 0.0, (-tank_r, tank_r)

    b.casing(cyly(tank_r, tank_h), LIGHT, T(0, tank_h / 2 + 0.16, 0), "TANK")
    b.casing(cyly(tank_r + 0.04, 0.05), LIGHT, T(0, tank_h + 0.16, 0), "TANK")
    for i in range(4):
        a = i / 4 * 2 * np.pi
        b.add(bx(0.09, 0.32, 0.09), BASE,
              xf=T(np.cos(a) * tank_r * 0.8, 0.16, np.sin(a) * tank_r * 0.8))
    for i in range(4):
        a = i / 4 * 2 * np.pi + np.pi / 8
        b.casing(bx(0.11, tank_h * 0.86, 0.02), LIGHT,
                 T(np.cos(a) * (tank_r - 0.09), tank_h / 2 + 0.16,
                   np.sin(a) * (tank_r - 0.09)), "BAFFLE")

    b.casing(bx(0.70, 0.07, 0.70), CAST, T(0, tank_h + 0.24, 0), "MOUNTPLATE")
    b.casing(bx(0.46, 0.42, 0.44), PAINT_GRN, T(0, y_top, 0), "GEARBOX")
    b.casing(cyly(0.16, 0.14), PAINT_GRN, T(0, y_top - 0.27, 0), "GEARBOX")
    b.add(cyly(0.028, 0.08), COPPER, xf=T(0.17, y_top + 0.24, 0))
    b.casing(cylx(0.20, 0.62, 48), MOTOR_BLUE, T(0.52, y_top + 0.10, 0), "MOTORBODY")
    b.casing(cylx(0.145, 0.10, 48), DARK, T(0.86, y_top + 0.10, 0), "COWL")
    b.casing(bx(0.20, 0.12, 0.16), MOTOR_BLUE, T(0.52, y_top + 0.34, 0), "TERMBOX")

    shaft_len = tank_h * 0.94
    b.rot(cyly(0.045, shaft_len), STEEL, T(0, y_top - 0.30 - shaft_len / 2, 0))
    for level, ratio in ((0.30, 1.0), (0.62, 0.78)):
        cy = 0.22 + tank_h * level
        r_imp = tank_r * 0.38 * ratio
        b.rot(cyly(0.085, 0.10), IRON, T(0, cy, 0))
        for i in range(blades):
            a = i / blades * 2 * np.pi
            bl = bx(r_imp, 0.02, r_imp * 0.42)
            bl.apply_transform(R([1, 0, 0], 38 if pitched else 0))
            bl.apply_transform(R([0, 1, 0], np.degrees(a)))
            bl.apply_translation([np.cos(a) * r_imp * 0.62, cy, np.sin(a) * r_imp * 0.62])
            b.rot(bl, STEEL)

    b.bearing("MIX_DE", 0.0, 0.11, 0.045, 0.06, y_top - 0.36, 0.0, axis="y")
    b.bearing("MIX_NDE", 0.0, 0.10, 0.045, 0.06, 0.30, 0.0, axis="y")
    # A vertical machine still owes three axes. H and A are across the shaft,
    # V is along it — the opposite of the horizontal case, and the reason these
    # are placed by hand rather than through triad().
    b.sensor("MIX_DE", "H", (0.20, y_top - 0.36, 0.0), (1, 0, 0))
    b.sensor("MIX_DE", "V", (0.0, y_top - 0.10, 0.0), (0, 1, 0))
    b.sensor("MIX_DE", "A", (0.0, y_top - 0.36, 0.20), (0, 0, 1))
    b.sensor("MIX_NDE", "H", (0.14, 0.30, 0.0), (1, 0, 0))
    b.sensor("MIX_NDE", "V", (0.0, 0.46, 0.0), (0, 1, 0))
    b.sensor("MIX_NDE", "A", (0.0, 0.30, 0.14), (0, 0, 1))
    return b


def build_mixer():
    return _vertical_agitator("mixer", 0.92, 1.45, 4, pitched=False)


def build_agitator():
    return _vertical_agitator("agitator", 0.78, 1.30, 3, pitched=True)


BUILDERS = [build_motor, build_pump, build_fan, build_blower, build_compressor,
            build_gearbox, build_spindle, build_turbine, build_wind_drivetrain,
            build_dg_set, build_machine_train, build_generator, build_conveyor,
            build_crusher, build_mixer, build_agitator]

if __name__ == "__main__":
    rows = []
    for fn in BUILDERS:
        b = fn()
        add_standard_anchors(b)
        path = b.export()
        kb = os.path.getsize(path) / 1024
        rows.append((b.name, len(b.sensors), len(b.bearings), round(kb, 1)))
        print("%-26s %2d sensors  %2d bearings  %6.1f kB" % rows[-1])
