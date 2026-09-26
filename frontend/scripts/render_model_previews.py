"""Render the Digital Twin previews as real 3D images.

These replace the flat side-elevation drawings. They are genuine 3D renders of
the *same geometry the viewer builds*: solid primitives, a perspective camera on
the viewer's own iso direction, a z-buffer for hidden-surface removal, and
diffuse shading from a key light with fill and ambient. Nothing here is a
drawing of a machine — it is the machine, photographed by a software camera.

Why a renderer rather than a headless browser: three.js needs WebGL, WebGL needs
a GPU context, and a headless Chromium is a 150 MB download that this machine
does not have the memory to drive. The models are boxes, cylinders and cones, so
a small software rasteriser covers them exactly.

Geometry comes from scripts/model-geometry.json, exported straight out of the
TypeScript registry by dump-model-geometry.ts, so a change to a machine shows up
in its preview on the next run instead of drifting.

    npx vite-node scripts/dump-model-geometry.ts
    python scripts/render_model_previews.py
"""
from __future__ import annotations

import json
import math
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
GEOMETRY = os.path.join(HERE, "model-geometry.json")
OUT_DIR = os.path.join(os.path.dirname(HERE), "public", "models", "previews")

W, H = 640, 384
SS = 2                      # supersample; downscaled at the end for edges
FOV_DEG = 42.0              # matches CAMERA_FOV in the viewer
FRAMING_MARGIN = 1.12

# Materials, keyed by the registry's tone. Values are linear-ish RGB that read
# as brushed metal and painted castings rather than plastic.
TONE_COLOR = {
    "body": (0.42, 0.50, 0.62),
    "casing": (0.52, 0.60, 0.71),
    "shaft": (0.74, 0.78, 0.84),
    "base": (0.30, 0.35, 0.44),
    "guard": (0.62, 0.55, 0.47),
}
BEARING_COLOR = (0.96, 0.65, 0.14)
SENSOR_COLOR = (1.00, 0.42, 0.00)
#: Neutral dark for the contact shadow — tinted shadows read as coloured haze
#: on the light backdrop and as nothing at all on the dark one.
SHADOW_RGB = np.array([0.16, 0.20, 0.27])

KEY_DIR = np.array([-0.45, 0.82, 0.62])     # over the left shoulder
FILL_DIR = np.array([0.70, 0.25, -0.35])
AMBIENT = 0.34
KEY = 0.78
FILL = 0.20


# ---------------------------------------------------------------------------
# Primitives — vertices + triangles, centred on the origin
# ---------------------------------------------------------------------------


def box_mesh(size):
    sx, sy, sz = (s / 2 for s in size)
    v = np.array(
        [
            [-sx, -sy, -sz], [sx, -sy, -sz], [sx, sy, -sz], [-sx, sy, -sz],
            [-sx, -sy, sz], [sx, -sy, sz], [sx, sy, sz], [-sx, sy, sz],
        ]
    )
    f = [
        (0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
        (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
        (1, 2, 6), (1, 6, 5), (0, 4, 7), (0, 7, 3),
    ]
    return v, f


def tube_mesh(r_top, length, r_bottom, axis="x", segments=26):
    """A cylinder or cone. `length` runs along `axis`; radii cap each end."""
    half = length / 2
    v, f = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        c, s = math.cos(a), math.sin(a)
        v.append([-half, r_bottom * c, r_bottom * s])
        v.append([half, r_top * c, r_top * s])
    base_c, top_c = len(v), len(v) + 1
    v.append([-half, 0, 0])
    v.append([half, 0, 0])

    for i in range(segments):
        b0, t0 = 2 * i, 2 * i + 1
        b1, t1 = 2 * ((i + 1) % segments), 2 * ((i + 1) % segments) + 1
        f += [(b0, b1, t1), (b0, t1, t0)]        # side
        f += [(base_c, b1, b0), (top_c, t0, t1)]  # caps

    v = np.array(v, dtype=float)
    # Built along local X; swing it onto the requested axis.
    if axis == "y":
        v = v[:, [1, 0, 2]]
        v[:, 1] *= -1
    elif axis == "z":
        v = v[:, [1, 2, 0]]
    return v, f


def euler_matrix(rx, ry, rz):
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)
    return (
        np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
        @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
        @ np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    )


def component_mesh(spec):
    shape, size = spec["shape"], spec["size"]
    if shape == "box":
        v, f = box_mesh(size)
    elif shape == "cone":
        v, f = tube_mesh(size[0], size[1], size[2], spec["axis"])
    else:
        v, f = tube_mesh(size[0], size[1], size[0], spec["axis"])

    if spec.get("rotation"):
        v = v @ euler_matrix(*spec["rotation"]).T
    return v + np.array(spec["position"]), f


def ring_mesh(centre, radius, thickness, segments=22, tube=8):
    """A torus around the shaft — how a bearing reads on the model."""
    v, f = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        cy, cz = math.cos(a) * radius, math.sin(a) * radius
        for j in range(tube):
            b = 2 * math.pi * j / tube
            v.append(
                [
                    math.sin(b) * thickness,
                    cy + math.cos(b) * math.cos(a) * thickness,
                    cz + math.cos(b) * math.sin(a) * thickness,
                ]
            )
    for i in range(segments):
        for j in range(tube):
            a0 = i * tube + j
            a1 = i * tube + (j + 1) % tube
            b0 = ((i + 1) % segments) * tube + j
            b1 = ((i + 1) % segments) * tube + (j + 1) % tube
            f += [(a0, b0, b1), (a0, b1, a1)]
    return np.array(v) + np.array(centre), f


def sphere_mesh(centre, r, rings=8, segs=12):
    v, f = [], []
    for i in range(rings + 1):
        phi = math.pi * i / rings
        for j in range(segs):
            th = 2 * math.pi * j / segs
            v.append(
                [r * math.sin(phi) * math.cos(th), r * math.cos(phi), r * math.sin(phi) * math.sin(th)]
            )
    for i in range(rings):
        for j in range(segs):
            a = i * segs + j
            b = i * segs + (j + 1) % segs
            c = (i + 1) * segs + j
            d = (i + 1) * segs + (j + 1) % segs
            f += [(a, c, d), (a, d, b)]
    return np.array(v) + np.array(centre), f


# ---------------------------------------------------------------------------
# Camera and rasteriser
# ---------------------------------------------------------------------------


def look_at(eye, target, up=np.array([0.0, 1.0, 0.0])):
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s)
    u = np.cross(s, f)
    return np.stack([s, u, -f]), eye


def render(parts, bounds, iso_dir, width, height):
    """parts: list of (verts, faces, rgb). Returns an RGBA float image."""
    centre = np.array(bounds["centre"], dtype=float)
    size = np.array(bounds["size"], dtype=float)
    radius = float(np.linalg.norm(size)) / 2

    fov = math.radians(FOV_DEG)
    aspect = width / height
    direction = np.array(iso_dir, dtype=float)
    direction /= np.linalg.norm(direction)
    f_scale_fit = 1.0 / math.tan(fov / 2)

    # Start from the bounding sphere, then close in on what the camera actually
    # sees. A machine is long and low, so its bounding sphere is far larger than
    # its silhouette — fitting the sphere leaves the model swimming in space.
    # Three passes over the real projected extent converge tightly.
    dist = radius * 2.4 / math.tan(fov / 2)
    all_verts = np.vstack([p[0] for p in parts])
    for _ in range(3):
        eye = centre + direction * dist
        R, _ = look_at(eye, centre)
        cam = (all_verts - eye) @ R.T
        z = -cam[:, 2]
        visible = z > 0.01
        if not visible.any():
            break
        sx = np.abs((cam[visible, 0] * f_scale_fit / aspect) / z[visible]).max()
        sy = np.abs((cam[visible, 1] * f_scale_fit) / z[visible]).max()
        extent = max(sx, sy)
        if extent <= 0:
            break
        # Scaling the distance by the overshoot lands the silhouette on the
        # frame edge; the margin backs it off to leave a little air.
        dist *= extent * FRAMING_MARGIN

    eye = centre + direction * dist
    R, _ = look_at(eye, centre)

    depth = np.full((height, width), np.inf)
    color = np.zeros((height, width, 3))
    alpha = np.zeros((height, width))

    f_scale = 1.0 / math.tan(fov / 2)
    key = KEY_DIR / np.linalg.norm(KEY_DIR)
    fill = FILL_DIR / np.linalg.norm(FILL_DIR)

    for verts, faces, rgb in parts:
        cam = (verts - eye) @ R.T                      # world -> camera
        z = -cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            sx = (cam[:, 0] * f_scale / aspect) / z
            sy = (cam[:, 1] * f_scale) / z
        px = (sx * 0.5 + 0.5) * width
        py = (0.5 - sy * 0.5) * height

        for i, j, k in faces:
            if z[i] <= 0.01 or z[j] <= 0.01 or z[k] <= 0.01:
                continue
            normal = np.cross(verts[j] - verts[i], verts[k] - verts[i])
            n = np.linalg.norm(normal)
            if n == 0:
                continue
            normal /= n
            # Backfaces never show on closed primitives; skipping them halves
            # the work and removes z-fighting on coincident surfaces.
            if np.dot(normal, eye - verts[i]) <= 0:
                continue

            shade = AMBIENT + KEY * max(0.0, float(np.dot(normal, key)))
            shade += FILL * max(0.0, float(np.dot(normal, fill)))
            face_rgb = np.clip(np.array(rgb) * shade, 0, 1)

            xs = np.array([px[i], px[j], px[k]])
            ys = np.array([py[i], py[j], py[k]])
            x0, x1 = int(max(0, math.floor(xs.min()))), int(min(width - 1, math.ceil(xs.max())))
            y0, y1 = int(max(0, math.floor(ys.min()))), int(min(height - 1, math.ceil(ys.max())))
            if x1 < x0 or y1 < y0:
                continue

            gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            gx = gx + 0.5
            gy = gy + 0.5
            d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(d) < 1e-9:
                continue
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
            w2 = 1.0 - w0 - w1
            inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if not inside.any():
                continue

            zs = w0 * z[i] + w1 * z[j] + w2 * z[k]
            sub_depth = depth[y0:y1 + 1, x0:x1 + 1]
            nearer = inside & (zs < sub_depth)
            if not nearer.any():
                continue
            sub_depth[nearer] = zs[nearer]
            color[y0:y1 + 1, x0:x1 + 1][nearer] = face_rgb
            alpha[y0:y1 + 1, x0:x1 + 1][nearer] = 1.0

    # Contact shadow: the same geometry flattened onto the floor and blurred.
    # Without it the machine floats, and the live viewer does cast one, so the
    # still would not match what replaces it.
    ground = centre[1] - size[1] / 2
    shadow = np.zeros((height, width))
    for verts, faces, _rgb in parts:
        flat = verts.copy()
        flat[:, 1] = ground
        cam = (flat - eye) @ R.T
        z = -cam[:, 2]
        with np.errstate(divide="ignore", invalid="ignore"):
            px = ((cam[:, 0] * f_scale / aspect) / z * 0.5 + 0.5) * width
            py = (0.5 - (cam[:, 1] * f_scale) / z * 0.5) * height

        for i, j, k in faces:
            if z[i] <= 0.01 or z[j] <= 0.01 or z[k] <= 0.01:
                continue
            xs, ys = np.array([px[i], px[j], px[k]]), np.array([py[i], py[j], py[k]])
            x0, x1 = int(max(0, math.floor(xs.min()))), int(min(width - 1, math.ceil(xs.max())))
            y0, y1 = int(max(0, math.floor(ys.min()))), int(min(height - 1, math.ceil(ys.max())))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
            if abs(d) < 1e-9:
                continue
            w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
            w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
            w2 = 1.0 - w0 - w1
            hit = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
            if hit.any():
                shadow[y0:y1 + 1, x0:x1 + 1][hit] = 1.0

    blurred = np.asarray(
        Image.fromarray((shadow * 255).astype(np.uint8)).filter(
            ImageFilter.GaussianBlur(radius=SS * 7)
        ),
        dtype=float,
    ) / 255.0
    shadow_a = np.clip(blurred * 0.42, 0, 1) * (1 - alpha)

    # Shadow first, model over it.
    out_a = np.clip(alpha + shadow_a, 0, 1)
    with np.errstate(divide="ignore", invalid="ignore"):
        out_rgb = np.where(
            out_a[..., None] > 0,
            (color * alpha[..., None] + SHADOW_RGB * shadow_a[..., None]) / np.maximum(out_a, 1e-6)[..., None],
            0.0,
        )

    return out_rgb, out_a


# ---------------------------------------------------------------------------


def parts_for(model):
    parts = []
    for spec in model["components"]:
        verts, faces = component_mesh(spec)
        parts.append((verts, faces, TONE_COLOR.get(spec["tone"], TONE_COLOR["body"])))

    # Bearings and sensors, so the preview carries the same information the
    # live twin does rather than being a bare shell.
    for anchor in model["bearingAnchors"]:
        verts, faces = ring_mesh(anchor["position"], anchor["radius"], anchor["radius"] * 0.17)
        parts.append((verts, faces, BEARING_COLOR))

    for anchor in model["sensorAnchors"][:4]:
        x, y, z = anchor["axisPoint"]
        r = anchor["radius"]
        verts, faces = sphere_mesh((x, y + r + 0.12, z), 0.15)
        parts.append((verts, faces, SENSOR_COLOR))

    return parts


def main() -> None:
    with open(GEOMETRY, encoding="utf8") as fh:
        payload = json.load(fh)

    os.makedirs(OUT_DIR, exist_ok=True)
    width, height = W * SS, H * SS

    rendered = {}
    for model in payload["models"]:
        color, alpha = render(
            parts_for(model), model["bounds"], payload["isoDirection"], width, height
        )
        rgba = np.dstack([np.clip(color, 0, 1) * 255, alpha * 255]).astype(np.uint8)
        image = Image.fromarray(rgba, "RGBA").resize((W, H), Image.LANCZOS)
        image.save(os.path.join(OUT_DIR, f"{model['id']}.png"), optimize=True)
        rendered[model["id"]] = image
        print(f"  {model['id']}.png  ({len(model['components'])} parts)")

    # A blower shares the fan's geometry in the viewer, so it shares the render.
    if "fan" in rendered:
        rendered["fan"].save(os.path.join(OUT_DIR, "blower.png"), optimize=True)
        print("  blower.png  (shares the fan model, as the viewer does)")

    print(f"\n{len(rendered) + 1} previews written to {OUT_DIR}")


if __name__ == "__main__":
    main()
