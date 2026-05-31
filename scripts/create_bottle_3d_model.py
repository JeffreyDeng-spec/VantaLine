from __future__ import annotations

import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


ROOT = Path("/mnt/f/CodexWorkspace/assembly_line_optimize")
OUT_DIR = ROOT / "generated_3d_models" / "transparent_nozzle_bottle_v1"
OBJ_PATH = OUT_DIR / "transparent_nozzle_bottle_v1.obj"
MTL_PATH = OUT_DIR / "transparent_nozzle_bottle_v1.mtl"
PREVIEW_PATH = OUT_DIR / "transparent_nozzle_bottle_v1_preview.png"


class ObjWriter:
    def __init__(self) -> None:
        self.vertices: list[tuple[float, float, float]] = []
        self.faces: list[tuple[str, list[tuple[int, int, int]]]] = []

    def add_vertex(self, xyz: tuple[float, float, float]) -> int:
        self.vertices.append(xyz)
        return len(self.vertices)

    def add_face(self, material: str, face: list[int]) -> None:
        self.faces.append((material, [(idx, 0, 0) for idx in face]))

    def write(self, obj_path: Path, mtl_name: str) -> None:
        obj_path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"mtllib {mtl_name}", "o transparent_nozzle_bottle_v1"]
        for x, y, z in self.vertices:
            lines.append(f"v {x:.5f} {y:.5f} {z:.5f}")
        current_material = None
        for material, face in self.faces:
            if material != current_material:
                lines.append(f"usemtl {material}")
                current_material = material
            indices = " ".join(str(v) for v, _, _ in face)
            lines.append(f"f {indices}")
        obj_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def add_cylinder(
    obj: ObjWriter,
    radius: float,
    z0: float,
    z1: float,
    *,
    segments: int = 72,
    material: str,
    radius_fn=None,
    cap_top: bool = True,
    cap_bottom: bool = True,
) -> None:
    bottom = []
    top = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        rb = radius_fn(a, z0) if radius_fn else radius
        rt = radius_fn(a, z1) if radius_fn else radius
        bottom.append(obj.add_vertex((rb * math.cos(a), rb * math.sin(a), z0)))
        top.append(obj.add_vertex((rt * math.cos(a), rt * math.sin(a), z1)))
    for i in range(segments):
        j = (i + 1) % segments
        obj.add_face(material, [bottom[i], bottom[j], top[j], top[i]])
    if cap_bottom:
        center = obj.add_vertex((0, 0, z0))
        for i in range(segments):
            j = (i + 1) % segments
            obj.add_face(material, [center, bottom[i], bottom[j]])
    if cap_top:
        center = obj.add_vertex((0, 0, z1))
        for i in range(segments):
            j = (i + 1) % segments
            obj.add_face(material, [center, top[j], top[i]])


def add_cone(
    obj: ObjWriter,
    r0: float,
    r1: float,
    z0: float,
    z1: float,
    *,
    segments: int = 72,
    material: str,
) -> None:
    bottom = []
    top = []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        bottom.append(obj.add_vertex((r0 * math.cos(a), r0 * math.sin(a), z0)))
        top.append(obj.add_vertex((r1 * math.cos(a), r1 * math.sin(a), z1)))
    for i in range(segments):
        j = (i + 1) % segments
        obj.add_face(material, [bottom[i], bottom[j], top[j], top[i]])
    cap = obj.add_vertex((0, 0, z1))
    for i in range(segments):
        j = (i + 1) % segments
        obj.add_face(material, [cap, top[i], top[j]])


def add_box(obj: ObjWriter, center: tuple[float, float, float], size: tuple[float, float, float], material: str) -> None:
    cx, cy, cz = center
    sx, sy, sz = (v / 2 for v in size)
    pts = [
        (cx - sx, cy - sy, cz - sz),
        (cx + sx, cy - sy, cz - sz),
        (cx + sx, cy + sy, cz - sz),
        (cx - sx, cy + sy, cz - sz),
        (cx - sx, cy - sy, cz + sz),
        (cx + sx, cy - sy, cz + sz),
        (cx + sx, cy + sy, cz + sz),
        (cx - sx, cy + sy, cz + sz),
    ]
    ids = [obj.add_vertex(p) for p in pts]
    for face in ([0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]):
        obj.add_face(material, [ids[i] for i in face])


def add_vertical_ribs(obj: ObjWriter) -> None:
    for i in range(8):
        a = 2 * math.pi * i / 8
        x = 19.8 * math.cos(a)
        y = 19.8 * math.sin(a)
        rib_width = 2.0
        rib_depth = 1.7
        length = 86.0
        # Tangentially approximate each transparent raised rib as a slim rectangular prism.
        tangent = np.array([-math.sin(a), math.cos(a), 0.0])
        normal = np.array([math.cos(a), math.sin(a), 0.0])
        center = np.array([x, y, 58.0])
        corners = []
        for dz in (-length / 2, length / 2):
            for tw, nd in ((-rib_width / 2, -rib_depth / 2), (rib_width / 2, -rib_depth / 2), (rib_width / 2, rib_depth / 2), (-rib_width / 2, rib_depth / 2)):
                p = center + tangent * tw + normal * nd + np.array([0.0, 0.0, dz])
                corners.append(tuple(float(v) for v in p))
        ids = [obj.add_vertex(p) for p in corners]
        for face in ([0, 1, 2, 3], [4, 7, 6, 5], [0, 4, 5, 1], [1, 5, 6, 2], [2, 6, 7, 3], [3, 7, 4, 0]):
            obj.add_face("glass_highlight", [ids[j] for j in face])


def build_model() -> ObjWriter:
    obj = ObjWriter()
    add_cylinder(obj, 19.0, 7.0, 108.0, material="clear_glass", cap_top=False, cap_bottom=True)
    add_cylinder(obj, 20.3, 0.0, 8.0, material="thick_glass_edge", cap_top=False, cap_bottom=True)
    add_cylinder(obj, 16.0, 108.0, 121.0, material="clear_glass", cap_top=False, cap_bottom=False)
    add_cylinder(obj, 13.8, 121.0, 137.0, material="black_ribbed_cap", radius_fn=lambda a, z: 13.8 + (1.0 if int(a / (math.pi / 18)) % 2 == 0 else 0.0))
    add_cone(obj, 10.0, 3.6, 137.0, 166.0, material="red_nozzle")
    add_cone(obj, 3.6, 2.0, 166.0, 171.0, material="red_nozzle_tip")
    add_vertical_ribs(obj)
    add_cylinder(obj, 21.0, 3.0, 5.2, segments=72, material="white_glass_edge", cap_top=False, cap_bottom=False)
    add_cylinder(obj, 17.0, 104.0, 106.0, segments=72, material="white_glass_edge", cap_top=False, cap_bottom=False)
    return obj


def write_materials(path: Path) -> None:
    path.write_text(
        """newmtl clear_glass
Kd 0.72 0.95 0.90
Ka 0.05 0.08 0.08
Ks 1.00 1.00 1.00
Ns 900
d 0.28
illum 4

newmtl thick_glass_edge
Kd 0.78 1.00 0.95
Ka 0.06 0.08 0.08
Ks 1.00 1.00 1.00
Ns 1000
d 0.42
illum 4

newmtl glass_highlight
Kd 0.93 1.00 0.98
Ka 0.05 0.05 0.05
Ks 1.00 1.00 1.00
Ns 1000
d 0.55
illum 4

newmtl white_glass_edge
Kd 0.96 1.00 1.00
Ka 0.08 0.08 0.08
Ks 1.00 1.00 1.00
Ns 1000
d 0.70
illum 4

newmtl black_ribbed_cap
Kd 0.015 0.014 0.013
Ka 0.02 0.02 0.02
Ks 0.30 0.30 0.30
Ns 240
d 1.0
illum 2

newmtl red_nozzle
Kd 1.00 0.16 0.07
Ka 0.10 0.02 0.01
Ks 0.48 0.18 0.12
Ns 320
d 1.0
illum 2

newmtl red_nozzle_tip
Kd 1.00 0.30 0.13
Ka 0.10 0.03 0.01
Ks 0.60 0.25 0.16
Ns 360
d 1.0
illum 2
""",
        encoding="utf-8",
    )


def face_vertices(obj: ObjWriter) -> list[tuple[str, list[tuple[float, float, float]]]]:
    out = []
    for mat, face in obj.faces:
        out.append((mat, [obj.vertices[v - 1] for v, _, _ in face]))
    return out


def render_preview(obj: ObjWriter, path: Path) -> None:
    colors = {
        "clear_glass": (0.62, 0.95, 0.90, 0.22),
        "thick_glass_edge": (0.75, 1.0, 0.95, 0.38),
        "glass_highlight": (0.95, 1.0, 1.0, 0.60),
        "white_glass_edge": (1.0, 1.0, 1.0, 0.72),
        "black_ribbed_cap": (0.015, 0.014, 0.013, 1.0),
        "red_nozzle": (1.0, 0.15, 0.05, 1.0),
        "red_nozzle_tip": (1.0, 0.30, 0.10, 1.0),
    }
    views = [
        ("upright isometric", 22, -48),
        ("upright top", 90, -90),
        ("lying isometric", 18, -38),
        ("lying top", 90, -90),
    ]
    fig = plt.figure(figsize=(13, 9), dpi=150)
    polys = face_vertices(obj)
    for idx, (title, elev, azim) in enumerate(views, start=1):
        ax = fig.add_subplot(2, 2, idx, projection="3d")
        ax.set_title(title, fontsize=10)
        transform = np.eye(3)
        if title.startswith("lying"):
            # Rotate upright model onto its side for preview only.
            a = math.radians(90)
            transform = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
        collections: dict[str, list[list[tuple[float, float, float]]]] = {}
        for mat, verts in polys:
            tv = [tuple(transform @ np.array(v)) for v in verts]
            collections.setdefault(mat, []).append(tv)
        for mat, faces in collections.items():
            col = Poly3DCollection(faces, facecolors=colors[mat], edgecolors=(0.8, 0.9, 0.9, 0.18), linewidths=0.25)
            ax.add_collection3d(col)
        pts = np.array([transform @ np.array(v) for v in obj.vertices])
        max_range = np.ptp(pts, axis=0).max() / 2
        center = pts.mean(axis=0)
        ax.set_xlim(center[0] - max_range, center[0] + max_range)
        ax.set_ylim(center[1] - max_range, center[1] + max_range)
        ax.set_zlim(center[2] - max_range, center[2] + max_range)
        ax.view_init(elev=elev, azim=azim)
        ax.set_axis_off()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, transparent=False, facecolor="white")
    plt.close(fig)


def main() -> None:
    obj = build_model()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_materials(MTL_PATH)
    obj.write(OBJ_PATH, MTL_PATH.name)
    render_preview(obj, PREVIEW_PATH)
    print(OBJ_PATH)
    print(MTL_PATH)
    print(PREVIEW_PATH)


if __name__ == "__main__":
    main()
