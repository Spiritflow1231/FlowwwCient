"""Software 3D renderer for Minecraft skins (hero pose preview).

The renderer builds the player model from boxes, rotates them with a simple rig and
paints every visible face with nearest-neighbour texture sampling.  Under an
orthographic camera every face is a parallelogram, so each face is drawn with one
PIL affine transform.  The scene is rendered supersampled and scaled down for
clean edges while texels stay crisp.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

SUPERSAMPLE = 4


@dataclass(frozen=True)
class Pose:
    """Angles in degrees.  ``yaw``/``pitch`` rotate the whole figure for the camera."""

    yaw: float = 25.0
    pitch: float = -6.0
    head_yaw: float = -12.0
    head_pitch: float = -8.0
    right_arm: tuple[float, float] = (-35.0, -6.0)   # (forward swing, roll out)
    left_arm: tuple[float, float] = (6.0, 10.0)
    right_leg: tuple[float, float] = (-10.0, -4.0)
    left_leg: tuple[float, float] = (6.0, 4.0)
    cape_angle: float = 9.0


HERO_POSE = Pose()
FRONT_POSE = Pose(yaw=0.0, pitch=0.0, head_yaw=0.0, head_pitch=0.0,
                  right_arm=(0.0, 0.0), left_arm=(0.0, 0.0),
                  right_leg=(0.0, 0.0), left_leg=(0.0, 0.0), cape_angle=4.0)


@dataclass
class RenderResult:
    image: Image.Image
    head_top: tuple[int, int]      # centre of the top of the head (pixels)
    feet: tuple[int, int]          # centre between the feet (pixels)
    scale: float
    info: dict = field(default_factory=dict)


# ── skin preparation ───────────────────────────────────────────────────────────

def normalize_skin(skin: Image.Image) -> tuple[Image.Image, bool]:
    """Return a 64x64-based RGBA skin (scaled-up HD skins stay HD) and legacy flag."""
    image = skin.convert("RGBA")
    factor = image.width // 64
    if factor < 1 or image.width % 64 or image.height not in (32 * factor, 64 * factor):
        raise ValueError("Expected a standard 64x64 or 64x32 Minecraft skin texture.")
    legacy = image.height == 32 * factor
    if not legacy:
        return image, False
    full = Image.new("RGBA", (64 * factor, 64 * factor), (0, 0, 0, 0))
    full.paste(image, (0, 0))

    def mirror(box, target):
        part = image.crop(tuple(v * factor for v in box)).transpose(Image.FLIP_LEFT_RIGHT)
        full.paste(part, (target[0] * factor, target[1] * factor))

    # Legacy skins only have the right limbs: mirror them for the left side.
    leg = (0, 16, 16, 32)
    arm = (40, 16, 56, 32)
    for source, target in ((leg, (16, 48)), (arm, (32, 48))):
        face_parts = (
            ((source[0] + 4, source[1], source[0] + 8, source[1] + 4), (target[0] + 4, target[1])),
            ((source[0] + 8, source[1], source[0] + 12, source[1] + 4), (target[0] + 8, target[1])),
            ((source[0], source[1] + 4, source[0] + 4, source[1] + 16), (target[0] + 8, target[1] + 4)),
            ((source[0] + 4, source[1] + 4, source[0] + 8, source[1] + 16), (target[0] + 4, target[1] + 4)),
            ((source[0] + 8, source[1] + 4, source[0] + 12, source[1] + 16), (target[0], target[1] + 4)),
            ((source[0] + 12, source[1] + 4, source[0] + 16, source[1] + 16), (target[0] + 12, target[1] + 4)),
        )
        for box, destination in face_parts:
            mirror(box, destination)
    # The game draws the base layer of legacy skins fully opaque.
    pixels = full.load()
    for box in ((0, 0, 32, 16), (0, 16, 64, 32), (16, 48, 48, 64)):
        for y in range(box[1] * factor, box[3] * factor):
            for x in range(box[0] * factor, box[2] * factor):
                r, g, b, a = pixels[x, y]
                if a != 255:
                    pixels[x, y] = (r, g, b, 255)
    return full, True


def guess_slim(skin: Image.Image) -> bool:
    """Heuristic: slim skins leave the 4th arm column transparent."""
    try:
        image = skin.convert("RGBA")
        factor = image.width // 64
        if factor < 1 or image.height < 64 * factor:
            return False
        column = image.crop((54 * factor, 20 * factor, 55 * factor, 32 * factor))
        return all(pixel[3] == 0 for pixel in column.getdata())
    except Exception:
        return False


# ── geometry helpers ───────────────────────────────────────────────────────────

def _rx(a: float) -> np.ndarray:
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def _ry(a: float) -> np.ndarray:
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def _rz(a: float) -> np.ndarray:
    c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


# face name -> (outward normal, origin selector, U selector, V selector)
def _face_vectors(face: str, lo, hi):
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    w, h, d = x1 - x0, y1 - y0, z1 - z0
    if face == "front":
        return (0, 0, 1), (x0, y1, z1), (w, 0, 0), (0, -h, 0)
    if face == "back":
        return (0, 0, -1), (x1, y1, z0), (-w, 0, 0), (0, -h, 0)
    if face == "right":
        return (-1, 0, 0), (x0, y1, z0), (0, 0, d), (0, -h, 0)
    if face == "left":
        return (1, 0, 0), (x1, y1, z1), (0, 0, -d), (0, -h, 0)
    if face == "top":
        return (0, 1, 0), (x0, y1, z0), (w, 0, 0), (0, 0, d)
    return (0, -1, 0), (x0, y0, z1), (w, 0, 0), (0, 0, -d)  # bottom


def _uv_rects(u: int, v: int, w: int, h: int, d: int) -> dict[str, tuple[int, int, int, int]]:
    return {
        "top": (u + d, v, w, d),
        "bottom": (u + d + w, v, w, d),
        "right": (u, v + d, d, h),
        "front": (u + d, v + d, w, h),
        "left": (u + d + w, v + d, d, h),
        "back": (u + d + w + d, v + d, w, h),
    }


@dataclass
class _Part:
    name: str
    lo: tuple[float, float, float]
    hi: tuple[float, float, float]
    rects: dict
    pivot: tuple[float, float, float]
    rotation: np.ndarray
    layer: int = 0          # 0 = base, 1 = overlay (drawn after the base)
    texture: str = "skin"   # or "cape"


def _build_parts(slim: bool, pose: Pose, has_cape: bool) -> list[_Part]:
    arm_w = 3 if slim else 4
    parts: list[_Part] = []

    def add(name, u, v, size, centre_x, y_low, pivot, rotation, inflate=0.0, layer=0,
            texture="skin", depth_offset=0.0):
        w, h, d = size
        lo = (centre_x - w / 2 - inflate, y_low - inflate, -d / 2 - inflate + depth_offset)
        hi = (centre_x + w / 2 + inflate, y_low + h + inflate, d / 2 + inflate + depth_offset)
        parts.append(_Part(name, lo, hi, _uv_rects(u, v, w, h, d), pivot, rotation,
                           layer, texture))

    head_rot = _ry(pose.head_yaw) @ _rx(pose.head_pitch)
    neck = (0.0, 24.0, 0.0)
    add("head", 0, 0, (8, 8, 8), 0, 24, neck, head_rot)
    add("hat", 32, 0, (8, 8, 8), 0, 24, neck, head_rot, inflate=0.5, layer=1)
    body_rot = np.eye(3)
    add("body", 16, 16, (8, 12, 4), 0, 12, (0, 12, 0), body_rot)
    add("jacket", 16, 32, (8, 12, 4), 0, 12, (0, 12, 0), body_rot, inflate=0.25, layer=1)

    def limb(name, base_uv, over_uv, centre_x, width, y_low, pivot_y, angles):
        pivot = (centre_x, pivot_y, 0.0)
        rotation = _rz(angles[1]) @ _rx(angles[0])
        add(name, base_uv[0], base_uv[1], (width, 12, 4), centre_x, y_low, pivot, rotation)
        add(name + "_over", over_uv[0], over_uv[1], (width, 12, 4), centre_x, y_low,
            pivot, rotation, inflate=0.25, layer=1)

    # player's right arm = viewer's left (negative x)
    right_x = -(4 + arm_w / 2)
    left_x = 4 + arm_w / 2
    limb("right_arm", (40, 16), (40, 32), right_x, arm_w, 12, 22, pose.right_arm)
    limb("left_arm", (32, 48), (48, 48), left_x, arm_w, 12, 22, pose.left_arm)
    limb("right_leg", (0, 16), (0, 32), -2, 4, 0, 12, pose.right_leg)
    limb("left_leg", (16, 48), (0, 48), 2, 4, 0, 12, pose.left_leg)
    if has_cape:
        # The cape's pattern (texture "front" rectangle) is its OUTER side, which faces
        # backwards on the model; the inner rectangle faces the body.
        rects = _uv_rects(0, 0, 10, 16, 1)
        cape_rects = {
            "top": rects["top"], "bottom": rects["bottom"],
            "front": rects["back"], "back": rects["front"],
            "left": rects["right"], "right": rects["left"],
        }
        parts.insert(0, _Part(
            "cape", (-5, 8, -3.0), (5, 24, -2.0), cape_rects,
            (0, 24, -2.0), _rx(pose.cape_angle), 0, "cape"))
    return parts


# ── rendering ──────────────────────────────────────────────────────────────────

_LIGHT_DIR = np.array([-0.35, 0.75, 0.55])
_LIGHT_DIR = _LIGHT_DIR / np.linalg.norm(_LIGHT_DIR)


def _pad_edge(texture: np.ndarray) -> np.ndarray:
    return np.pad(texture, ((1, 1), (1, 1), (0, 0)), mode="edge")


def render_player(
    skin: Image.Image,
    slim: bool | None = None,
    cape: Image.Image | None = None,
    pose: Pose = HERO_POSE,
    size: tuple[int, int] = (360, 480),
    margin: float = 0.06,
) -> RenderResult:
    """Render ``skin`` (and optional ``cape``) into an RGBA image of ``size``."""
    full_skin, legacy = normalize_skin(skin)
    if slim is None:
        slim = guess_slim(skin)
    skin_array = np.asarray(full_skin, dtype=np.uint8)
    factor = full_skin.width // 64
    cape_array = None
    cape_factor = 1
    if cape is not None:
        cape_image = cape.convert("RGBA")
        cape_factor = max(1, cape_image.width // 64)
        cape_array = np.asarray(cape_image, dtype=np.uint8)

    parts = _build_parts(bool(slim), pose, cape_array is not None)
    view = _rx(pose.pitch) @ _ry(pose.yaw)

    width, height = size
    ss = SUPERSAMPLE
    canvas_w, canvas_h = width * ss, height * ss
    unit = (height * (1 - 2 * margin)) / 33.0 * ss  # model is about 32 units tall
    centre_x = canvas_w / 2
    floor_y = canvas_h * (1 - margin)

    def project(point) -> tuple[float, float]:
        return centre_x + point[0] * unit, floor_y - point[1] * unit

    faces = []
    for part in parts:
        texture_array = cape_array if part.texture == "cape" else skin_array
        if texture_array is None:
            continue
        tex_factor = cape_factor if part.texture == "cape" else factor
        pivot = np.array(part.pivot, dtype=float)
        for face, rect in part.rects.items():
            normal, origin, vec_u, vec_v = _face_vectors(face, part.lo, part.hi)
            rotation = view @ part.rotation
            n_cam = rotation @ np.array(normal, dtype=float)
            if n_cam[2] <= 0.02:
                continue
            o_cam = view @ (part.rotation @ (np.array(origin, dtype=float) - pivot) + pivot)
            u_cam = rotation @ np.array(vec_u, dtype=float)
            v_cam = rotation @ np.array(vec_v, dtype=float)
            centre = o_cam + (u_cam + v_cam) / 2
            u0, v0, tw, th = rect
            crop = texture_array[
                v0 * tex_factor:(v0 + th) * tex_factor,
                u0 * tex_factor:(u0 + tw) * tex_factor,
            ]
            if crop.size == 0:
                continue
            faces.append((centre[2], part.layer, part.name, face, n_cam, o_cam, u_cam,
                          v_cam, crop))

    faces.sort(key=lambda item: (round(item[0], 3), item[1]))
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
    for _depth, _layer, _name, _face, n_cam, o_cam, u_cam, v_cam, crop in faces:
        shade = 0.60 + 0.40 * max(0.0, float(np.dot(n_cam, _LIGHT_DIR)))
        shaded = crop.astype(np.float32)
        shaded[..., :3] *= shade
        padded = _pad_edge(np.clip(shaded, 0, 255).astype(np.uint8))
        th, tw = crop.shape[0], crop.shape[1]
        s0 = np.array(project(o_cam))
        su = np.array([u_cam[0] * unit, -u_cam[1] * unit])
        sv = np.array([v_cam[0] * unit, -v_cam[1] * unit])
        matrix = np.array([[su[0], sv[0]], [su[1], sv[1]]])
        det = np.linalg.det(matrix)
        if abs(det) < 1e-3:
            continue
        inverse = np.linalg.inv(matrix)
        scale = np.array([[tw, 0], [0, th]], dtype=float)
        linear = scale @ inverse
        corners = [s0, s0 + su, s0 + su + sv, s0 + sv]
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        bx0, by0 = max(0, int(math.floor(min(xs))) - 2), max(0, int(math.floor(min(ys))) - 2)
        bx1 = min(canvas_w, int(math.ceil(max(xs))) + 2)
        by1 = min(canvas_h, int(math.ceil(max(ys))) + 2)
        if bx1 <= bx0 or by1 <= by0:
            continue
        # input = linear @ ([x + bx0, y + by0] - s0) + 1 (edge padding)
        offset = linear @ (np.array([bx0, by0]) - s0) + 1.0
        coeffs = (linear[0, 0], linear[0, 1], offset[0], linear[1, 0], linear[1, 1], offset[1])
        source = Image.fromarray(padded)
        face_image = source.transform(
            (bx1 - bx0, by1 - by0), Image.AFFINE, coeffs,
            resample=Image.NEAREST, fillcolor=(0, 0, 0, 0),
        )
        mask = Image.new("L", face_image.size, 0)
        centre = sum(corners) / 4
        grown = []
        for corner in corners:
            direction = corner - centre
            length = np.linalg.norm(direction) or 1.0
            grown_corner = corner + direction / length * 0.8
            grown.append((grown_corner[0] - bx0, grown_corner[1] - by0))
        ImageDraw.Draw(mask).polygon(grown, fill=255)
        alpha = Image.composite(face_image.getchannel("A"), Image.new("L", face_image.size, 0), mask)
        face_image.putalpha(alpha)
        canvas.alpha_composite(face_image, (bx0, by0))

    image = canvas.resize((width, height), Image.LANCZOS)
    head_top = view @ np.array([0.0, 32.6, 0.0])
    feet = view @ np.array([0.0, 0.0, 0.0])
    head_px = project(head_top)
    feet_px = project(feet)
    return RenderResult(
        image=image,
        head_top=(round(head_px[0] / ss), round(head_px[1] / ss)),
        feet=(round(feet_px[0] / ss), round(feet_px[1] / ss)),
        scale=unit / ss,
        info={"legacy": legacy, "slim": bool(slim), "faces": len(faces)},
    )


# ── stage decorations ──────────────────────────────────────────────────────────

def make_nametag(text: str, bg: str = "#1B1830", fg: str = "#FFFFFF",
                 height: int = 34, scale: int = 2) -> Image.Image:
    """Render an in-game style nametag pill (semi-transparent) as RGBA."""
    from PIL import ImageFont

    size = 15 * scale
    font = None
    for name in ("segoeuib.ttf", "DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            font = ImageFont.truetype(name, size)
            break
        except OSError:
            continue
    if font is None:
        try:
            font = ImageFont.load_default(size=size)
        except TypeError:
            font = ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    box = probe.textbbox((0, 0), text or " ", font=font)
    text_w, text_h = box[2] - box[0], box[3] - box[1]
    pad_x, pad_y = 14 * scale, 6 * scale
    width, h = text_w + pad_x * 2, max(height * scale, text_h + pad_y * 2)
    image = Image.new("RGBA", (width, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    r, g, b = (int(bg[i:i + 2], 16) for i in (1, 3, 5))
    draw.rounded_rectangle((0, 0, width - 1, h - 1), radius=h // 2, fill=(r, g, b, 150))
    draw.text(((width - text_w) / 2 - box[0], (h - text_h) / 2 - box[1]), text or " ",
              font=font, fill=fg)
    return image


def make_floor_shadow(width: int, accent: str = "#6C5CE7", strength: float = 1.0) -> Image.Image:
    """A soft elliptical shadow with a faint accent glow, as RGBA."""
    height = max(16, width // 5)
    pad = width // 6
    image = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
    glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    r, g, b = (int(accent[i:i + 2], 16) for i in (1, 3, 5))
    ImageDraw.Draw(glow).ellipse(
        (pad // 2, pad // 2, image.width - pad // 2, image.height - pad // 2),
        fill=(r, g, b, int(70 * strength)),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(pad / 1.6))
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse(
        (pad, pad, image.width - pad, image.height - pad), fill=(10, 8, 25, int(120 * strength))
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(pad / 3.2))
    image.alpha_composite(glow)
    image.alpha_composite(shadow)
    return image
