#!/usr/bin/env python3
"""
迎曦門（新竹東門城）Blender 程序化重建 — 第二件成品

以 Blender（bpy 5.0）從零建出整座城門，不限制步數：每放上一塊石、一片瓦、
一根椽、一盞燈籠，都記錄成一個建造步驟，最後輸出：

  out/east_gate.blend        Blender 場景（含材質、燈光、相機）
  out/steps.csv              全部建造步驟
  out/renders/*.jpg          照片視角、鳥瞰、翹角特寫、各施工階段
  out/east_gate.glb          （--glb）網頁用模型

用法（bpy 以 pip 安裝於 Python 3.11）：
  python build_gate.py --out out --render all --samples 128

座標：Z 向上，X 為城門長軸，城門正面朝 -Y（拱道沿 Y 穿越）。單位：公尺。
尺寸依參考照片量測：以石造台座高 7.04 m（16 層 × 0.44 m）為比例尺推算其餘部位。
"""
import argparse
import csv
import math
import os
import random
import sys
import time

import bpy
import addon_utils
from mathutils import Vector, Matrix

# ---------------------------------------------------------------------------
# 參數
# ---------------------------------------------------------------------------
ap = argparse.ArgumentParser()
ap.add_argument('--out', default='out')
ap.add_argument('--render', default='hero', help='none | test | hero | phases | all')
ap.add_argument('--samples', type=int, default=128)
ap.add_argument('--res', type=int, default=1800, help='hero render width in px')
ap.add_argument('--glb', action='store_true')
ap.add_argument('--no-blend', action='store_true')
args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:])

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(args.out)
os.makedirs(os.path.join(OUT, 'renders'), exist_ok=True)
rng = random.Random(1829)  # 道光九年（1829）竣工

# 台座
PL, PW = 19.6, 10.6          # 長、寬
BH, NC = 0.44, 16            # 石層高、層數
PH = BH * NC                 # 7.04
SHELL = 0.5                  # 外牆石厚
AW, SP, AR = 2.8, 2.2, 2.8   # 拱道半寬、起拱高、拱半徑（拱頂 5.0）
VR = 0.62                    # 拱券石厚
FY = PH + 0.15               # 台頂鋪石完成面
# 下層木構
CL, CW = 16.6, 8.0           # 下層柱列外框
COL_H = 2.2
CT = FY + 0.2 + COL_H        # 柱頂 9.59
# 下層屋頂（腰簷）
UL, UW = 10.6, 5.0           # 上層樓身
LTX, LTY = UL / 2 + 0.1, UW / 2 + 0.1
LEX, LEY = 10.4, 6.3
LZ0, LD, LLIFT = 12.8, 2.6, 0.95
# 上層
UY = 12.55
UCT = 13.85
# 上層屋頂（歇山）
URX, UEX, UEY = 4.2, 7.6, 4.9
UZ0, UD, ULIFT, UV0 = 16.8, 3.0, 1.0, 0.45

PHASES = [
    ('城台核心', '整地放樣，以三合土與碎石夯築城台核心，預留拱道。'),
    ('砂岩外牆', '外牆以砂岩條石逐層錯縫砌築，轉角石左右交替咬合。'),
    ('拱券與穹窿', '砌拱腳側牆，再以楔形拱券石合攏，拱道內以錯縫石環砌成筒形穹窿。'),
    ('台頂與腰線', '台頂鋪石板，沿頂緣安裝線腳腰線。'),
    ('女牆', '砌築女牆、粉刷白灰並安裝壓頂。'),
    ('下層木構', '安柱礎、立朱紅木柱與通柱，砌內牆隔扇，裝欄杆。'),
    ('下層樑枋斗栱', '架額枋、大額枋、平板枋，安裝出跳斗栱、挑簷枋，懸掛燈籠。'),
    ('下層屋頂', '釘椽、鋪望板，自簷口往上鋪板瓦與筒瓦，安瓦當滴水、封簷板與垂脊。'),
    ('上層樓身', '砌白牆、開小方窗，懸「迎曦門」匾額。'),
    ('上層樑枋斗栱', '架上層樑枋與斗栱，懸掛燈籠。'),
    ('上層屋頂', '鋪歇山屋面，立山花博風，安垂脊、正脊與燕尾。'),
    ('廣場與街景', '鋪設廣場、石柱鏈欄、石椅、植栽、道路標線與周邊街屋。'),
]

STEPS = []


def step(phase, desc):
    STEPS.append((len(STEPS) + 1, phase + 1, PHASES[phase][0], desc))


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(x, a, b):
    return a if x < a else b if x > b else x


# ---------------------------------------------------------------------------
# 網格累積器：同一階段、同一材質的構件合併成一個物件
# ---------------------------------------------------------------------------
class MB:
    def __init__(self, name, mat, phase, bevel=0.0, solidify=0.0, smooth_angle=None):
        self.name, self.mat, self.phase = name, mat, phase
        self.bevel, self.solidify = bevel, solidify
        self.v, self.f, self.var, self.smooth = [], [], [], []

    def add(self, verts, faces, var=None, smooth=False):
        base = len(self.v)
        self.v.extend(tuple(p) for p in verts)
        if var is None:
            var = rng.random()
        for fc in faces:
            self.f.append(tuple(base + i for i in fc))
            self.var.append(var)
            self.smooth.append(smooth)


BUILDERS = {}


def mb(phase, mat, bevel=0.0, solidify=0.0):
    key = (phase, mat, bevel, solidify)
    if key not in BUILDERS:
        BUILDERS[key] = MB('%02d_%s' % (phase + 1, mat), mat, phase, bevel, solidify)
    return BUILDERS[key]


BOX_F = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (3, 0, 4, 7), (1, 2, 6, 5)]


def box(m, c, s, rot=None, var=None):
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    out = []
    for p in ((-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
              (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)):
        v = Vector(p)
        if rot is not None:
            v = rot @ v
        out.append((c[0] + v.x, c[1] + v.y, c[2] + v.z))
    m.add(out, BOX_F, var)


def axis_frame(d, up=Vector((0, 0, 1))):
    d = Vector(d).normalized()
    if abs(d.dot(up)) > 0.98:
        up = Vector((0, 1, 0))
    side = d.cross(up).normalized()
    upv = side.cross(d).normalized()
    y = upv.cross(d)
    return Matrix((d, y, upv)).transposed()


def bar(m, a, b, h, w, var=None):
    a, b = Vector(a), Vector(b)
    d = b - a
    L = d.length
    if L < 1e-6:
        return
    box(m, (a + b) / 2, (L, w, h), axis_frame(d), var)


def prism_xz(m, poly, y0, y1, var=None):
    """多邊形（XZ 平面，從 -Y 看為逆時針）沿 Y 擠出。"""
    n = len(poly)
    verts = [(x, y0, z) for x, z in poly] + [(x, y1, z) for x, z in poly]
    faces = [tuple(range(n)), tuple(n + i for i in reversed(range(n)))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, n + i, n + j, j))
    m.add(verts, faces, var)


def prism_yz(m, poly, x0, x1, var=None):
    n = len(poly)
    verts = [(x0, y, z) for y, z in poly] + [(x1, y, z) for y, z in poly]
    faces = [tuple(reversed(range(n))), tuple(n + i for i in range(n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))
    m.add(verts, faces, var)


def circle(r, n, start=0.0, end=2 * math.pi, closed=True):
    k = n if closed else n + 1
    return [(r * math.cos(start + (end - start) * i / n), r * math.sin(start + (end - start) * i / n)) for i in range(k)]


def sweep(m, pts, prof, scales=None, up=Vector((0, 0, 1)), side_hint=None, cap=True,
          smooth=True, var=None, closed_prof=True):
    """沿折線掃掠剖面。prof 為 (側向, 上向) 座標。"""
    pts = [Vector(p) for p in pts]
    n, k = len(pts), len(prof)
    if n < 2:
        return
    verts, faces = [], []
    for i, p in enumerate(pts):
        if i == 0:
            t = pts[1] - pts[0]
        elif i == n - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        t.normalize()
        if side_hint is not None:
            s = Vector(side_hint)
            s = (s - t * s.dot(t)).normalized()
        else:
            u = up if abs(t.dot(up)) < 0.97 else Vector((1, 0, 0))
            s = t.cross(u).normalized()
        upv = s.cross(t).normalized()
        sc = scales[i] if scales else 1.0
        for a, b in prof:
            verts.append(p + s * a * sc + upv * b * sc)
    span = k if closed_prof else k - 1
    for i in range(n - 1):
        for j in range(span):
            j2 = (j + 1) % k
            faces.append((i * k + j, i * k + j2, (i + 1) * k + j2, (i + 1) * k + j))
    if cap and closed_prof:
        faces.append(tuple(reversed(range(k))))
        faces.append(tuple((n - 1) * k + j for j in range(k)))
    m.add(verts, faces, var, smooth)


def lathe(m, c, prof, seg=18, var=None, smooth=True):
    verts, faces = [], []
    k = len(prof)
    for s in range(seg):
        a = 2 * math.pi * s / seg
        ca, sa = math.cos(a), math.sin(a)
        for r, z in prof:
            verts.append((c[0] + r * ca, c[1] + r * sa, c[2] + z))
    for s in range(seg):
        s2 = (s + 1) % seg
        for j in range(k - 1):
            faces.append((s * k + j, s2 * k + j, s2 * k + j + 1, s * k + j + 1))
    m.add(verts, faces, var, smooth)


def ring_sweep(m, hx, hy, z0, prof, var=None):
    """沿矩形外框掃掠封閉剖面 (向外偏移, 高度)，轉角自動斜接。"""
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    k = len(prof)
    verts = []
    for o, dz in prof:
        for sx, sy in corners:
            verts.append((sx * (hx + o), sy * (hy + o), z0 + dz))
    faces = []
    for j in range(k):
        j2 = (j + 1) % k
        for c in range(4):
            c2 = (c + 1) % 4
            faces.append((j * 4 + c, j * 4 + c2, j2 * 4 + c2, j2 * 4 + c))
    m.add(verts, faces, var)


def rect_ring(hx, hy, step_len):
    """矩形周邊上等距點（含四角），逆時針自前左角起。"""
    pts = []
    for (ax, ay), (bx, by) in [((-hx, -hy), (hx, -hy)), ((hx, -hy), (hx, hy)), ((hx, hy), (-hx, hy)), ((-hx, hy), (-hx, -hy))]:
        L = math.hypot(bx - ax, by - ay)
        n = max(1, round(L / step_len))
        for i in range(n):
            pts.append((lerp(ax, bx, i / n), lerp(ay, by, i / n)))
    return pts


# ---------------------------------------------------------------------------
# 1. 城台核心
# ---------------------------------------------------------------------------
def arch_outline(aw, sp, ar, n=28):
    pts = [(-aw, 0.0), (-aw, sp)]
    for i in range(1, n):
        a = math.pi - math.pi * i / n
        pts.append((ar * math.cos(a), sp + ar * math.sin(a)))
    pts += [(aw, sp), (aw, 0.0)]
    return pts


def build_core():
    P = 0
    ins = 0.04
    hx = PL / 2 - ins
    aw, ar = AW + ins, AR + ins
    top = SP + ar

    def xo(z):
        return aw if z <= SP else math.sqrt(max(ar * ar - (z - SP) ** 2, 0.0))

    lifts = 8
    for k in range(lifts):
        z0, z1 = PH * k / lifts, PH * (k + 1) / lifts
        m = mb(P, 'mortar')
        y0, y1 = -PW / 2 + ins, PW / 2 - ins
        if z0 >= top:
            prism_xz(m, [(-hx, z0), (hx, z0), (hx, z1), (-hx, z1)], y0, y1)
        else:
            zt = min(z1, top)
            zs = [z0 + (zt - z0) * i / 12 for i in range(13)]
            if z1 <= top:
                left = [(-hx, z0)] + [(-xo(z), z) for z in zs] + [(-hx, z1)]
                right = [(xo(z0), z0), (hx, z0), (hx, z1)] + [(xo(z), z) for z in reversed(zs[1:])]
                prism_xz(m, left, y0, y1)
                prism_xz(m, right, y0, y1)
            else:
                curve_l = [(-xo(z), z) for z in zs]
                curve_r = [(xo(z), z) for z in reversed(zs[:-1])]
                poly = [(-hx, z0)] + curve_l + curve_r + [(hx, z0), (hx, z1), (-hx, z1)]
                prism_xz(m, poly, y0, y1)
        step(P, '夯築城台核心第 %d 層（%.2f–%.2f m）' % (k + 1, z0, z1))


# ---------------------------------------------------------------------------
# 2. 砂岩外牆
# ---------------------------------------------------------------------------
def opening_clip(zmid):
    """台座正背面在高度 zmid 處需讓出的半寬（拱道 + 拱券石帶）。"""
    if zmid < SP:
        return AW
    R = AR + VR
    d = zmid - SP
    if d >= R:
        return 0.0
    return math.sqrt(R * R - d * d)


def course_blocks(length, c, start_off):
    """沿長度隨機切分石塊，回傳 [(a, b)]。"""
    out = []
    a = -length / 2
    first = True
    while a < length / 2 - 1e-6:
        L = rng.uniform(0.75, 1.35)
        if first:
            L = start_off if start_off > 0.2 else L
            first = False
        b = min(a + L, length / 2)
        if length / 2 - b < 0.35:
            b = length / 2
        out.append((a, b))
        a = b
    return out


def stone(m, c, s, var=None):
    jx = rng.uniform(-0.004, 0.004)
    rot = Matrix.Rotation(rng.uniform(-0.004, 0.004), 3, 'Z') @ Matrix.Rotation(rng.uniform(-0.003, 0.003), 3, 'X')
    box(m, (c[0] + jx, c[1], c[2]), s, rot, var)


def build_walls():
    P = 1
    gap = 0.025
    m = mb(P, 'sandstone', bevel=0.03)
    face_names = {-1: '正面', 1: '背面'}
    for c in range(NC):
        z0 = c * BH
        zc = z0 + BH / 2
        clip = opening_clip(zc)
        long_full = (c % 2 == 0)
        # 正面與背面
        for side in (-1, 1):
            y = side * (PW / 2 - SHELL / 2)
            length = PL if long_full else PL - 2 * SHELL
            for i, (a, b) in enumerate(course_blocks(length, c, rng.uniform(0.4, 1.2))):
                segs = [(a, b)]
                if clip > 0 and a < clip and b > -clip:
                    segs = []
                    if -clip - a > 0.18:
                        segs.append((a, -clip))
                    if b - clip > 0.18:
                        segs.append((clip, b))
                for (sa, sb) in segs:
                    out = rng.uniform(0.0, 0.018)
                    stone(m, ((sa + sb) / 2, y + side * out, zc), (sb - sa - gap, SHELL, BH - gap))
                    step(P, '砌%s第 %d 層砂岩條石（長 %.2f m）' % (face_names[side], c + 1, sb - sa))
        # 左右側面
        for side in (-1, 1):
            x = side * (PL / 2 - SHELL / 2)
            length = PW - 2 * SHELL if long_full else PW
            for (a, b) in course_blocks(length, c, rng.uniform(0.4, 1.2)):
                out = rng.uniform(0.0, 0.018)
                stone(m, (x + side * out, (a + b) / 2, zc), (SHELL, b - a - gap, BH - gap))
                step(P, '砌%s第 %d 層砂岩條石（長 %.2f m）' % ('右側' if side > 0 else '左側', c + 1, b - a))


# ---------------------------------------------------------------------------
# 3. 拱券與穹窿
# ---------------------------------------------------------------------------
def wedge(m, r0, r1, a0, a1, y0, y1, var=None):
    pts = [(r0 * math.cos(a0), r0 * math.sin(a0)), (r1 * math.cos(a0), r1 * math.sin(a0)),
           (r1 * math.cos(a1), r1 * math.sin(a1)), (r0 * math.cos(a1), r0 * math.sin(a1))]
    poly = [(x, SP + z) for x, z in pts]
    # 讓多邊形從 -Y 看為逆時針
    prism_xz(m, list(reversed(poly)), y0, y1, var)


def build_arch():
    P = 2
    gap = 0.012
    m = mb(P, 'sandstone_dark', bevel=0.025)
    # 拱腳側牆
    ncs = round(SP / BH)
    for c in range(ncs):
        zc = c * BH + BH / 2
        for side in (-1, 1):
            x = side * (AW + 0.2)
            for (a, b) in course_blocks(PW - 0.02, c, rng.uniform(0.4, 1.1)):
                stone(m, (x, (a + b) / 2, zc), (0.4, b - a - 0.025, BH - 0.025))
                step(P, '砌拱道%s側牆第 %d 層（長 %.2f m）' % ('右' if side > 0 else '左', c + 1, b - a))
    # 穹窿石環（錯縫）
    ring_d = 0.48
    nr = int(round((PW - 2 * 0.56) / ring_d))
    ring_d = (PW - 2 * 0.56) / nr
    nb = 15
    for k in range(nr):
        y0 = -PW / 2 + 0.56 + k * ring_d
        off = 0.5 if k % 2 else 0.0
        edges = [0.0] + [math.pi * (i + off) / nb for i in range(1, nb + 1) if (i + off) < nb] + [math.pi]
        for i in range(len(edges) - 1):
            wedge(m, AR, AR + 0.45, edges[i] + gap / AR, edges[i + 1] - gap / AR, y0 + 0.012, y0 + ring_d - 0.012)
            step(P, '砌穹窿第 %d 道石環第 %d 塊楔石' % (k + 1, i + 1))
    # 正背面拱券石
    n = 19
    for side, nm in ((-1, '正面'), (1, '背面')):
        yface = side * PW / 2
        for i in range(n):
            a0 = math.pi * i / n + 0.012
            a1 = math.pi * (i + 1) / n - 0.012
            key = (i == n // 2)
            r1 = AR + VR + (0.16 if key else 0.0)
            proj = 0.06 if key else 0.035
            y_out = yface + side * proj
            y_in = yface - side * 0.58
            wedge(m, AR, r1, a0, a1, min(y_out, y_in), max(y_out, y_in))
            step(P, ('安放%s拱心石' % nm) if key else ('砌%s拱券石第 %d 塊' % (nm, i + 1)))
    # 拱道地面
    mf = mb(P, 'slab', bevel=0.015)
    for k in range(int(PW / 0.9)):
        for j in range(4):
            w = 2 * AW / 4
            box(mf, (-AW + w * (j + 0.5), -PW / 2 + 0.45 + k * 0.9, 0.04), (w - 0.02, 0.88, 0.08))
            step(P, '鋪設拱道地面石板 第 %d 排第 %d 塊' % (k + 1, j + 1))


# ---------------------------------------------------------------------------
# 4. 台頂與腰線
# ---------------------------------------------------------------------------
def build_top():
    P = 3
    m = mb(P, 'slab', bevel=0.02)
    nx, ny = 16, 9
    cx, cy = (PL - 0.1) / nx, (PW - 0.1) / ny
    for j in range(ny):
        for i in range(nx):
            box(m, (-PL / 2 + 0.05 + cx * (i + 0.5), -PW / 2 + 0.05 + cy * (j + 0.5), PH + 0.075), (cx - 0.02, cy - 0.02, 0.15))
            step(P, '鋪台頂石板 第 %d 排第 %d 塊' % (j + 1, i + 1))
    prof = [(-0.42, 0.0), (0.03, 0.0), (0.03, 0.08), (0.10, 0.14), (0.10, 0.34), (0.17, 0.40), (0.17, 0.50), (-0.42, 0.50)]
    ring_sweep(mb(P, 'plaster_trim'), PL / 2, PW / 2, PH - 0.06, prof)
    for nm in ('正面', '右側', '背面', '左側'):
        step(P, '安裝%s線腳腰線' % nm)


# ---------------------------------------------------------------------------
# 5. 女牆
# ---------------------------------------------------------------------------
def build_parapet():
    P = 4
    m = mb(P, 'plaster', bevel=0.01)
    z0 = PH + 0.44
    h = 0.92
    t = 0.38
    hx, hy = PL / 2 - 0.02, PW / 2 - 0.02
    # 以 1.2 m 為一段，模擬分段砌築
    for (ax, ay), (bx, by), nm in [((-hx, -hy), (hx, -hy), '正面'), ((hx, -hy), (hx, hy), '右側'),
                                   ((hx, hy), (-hx, hy), '背面'), ((-hx, hy), (-hx, -hy), '左側')]:
        L = math.hypot(bx - ax, by - ay)
        n = max(1, round(L / 1.2))
        dx, dy = (bx - ax) / L, (by - ay) / L
        nxv, nyv = dy, -dx  # 向外法線
        for i in range(n):
            pa = (lerp(ax, bx, i / n), lerp(ay, by, i / n))
            pb = (lerp(ax, bx, (i + 1) / n), lerp(ay, by, (i + 1) / n))
            ca = (pa[0] - nxv * t / 2, pa[1] - nyv * t / 2, z0 + h / 2)
            cb = (pb[0] - nxv * t / 2, pb[1] - nyv * t / 2, z0 + h / 2)
            bar(m, ca, cb, h, t)
            step(P, '砌%s女牆第 %d 段並粉刷白灰' % (nm, i + 1))
    prof = [(-0.44, 0.0), (0.05, 0.0), (0.05, 0.07), (0.0, 0.13), (-0.39, 0.13), (-0.44, 0.07)]
    ring_sweep(mb(P, 'coping'), hx, hy, z0 + h, prof)
    for nm in ('正面', '右側', '背面', '左側'):
        step(P, '安裝%s女牆壓頂' % nm)


# ---------------------------------------------------------------------------
# 屋頂曲面
# ---------------------------------------------------------------------------
def fcurve(v):
    # 上陡下緩的凹曲線（舉折）
    return 0.45 * v + 0.55 * (1 - (1 - v) * (1 - v))


class Slope:
    def __init__(self, name, hw, dep, zf, orient, vstart, vtop=0.0):
        self.name, self.hw, self.dep, self.zf, self.orient, self.vstart = name, hw, dep, zf, orient, vstart
        self.vtop = vtop

    def pos(self, u, v):
        a = u * self.hw(v)
        d = self.dep(v)
        x, y = self.orient(a, d)
        return Vector((x, y, self.zf(u, v)))

    def pos_a(self, a, v):
        return self.pos(a / max(self.hw(v), 1e-6), v)

    def normal(self, u, v):
        e = 1e-3
        pu = self.pos(min(u + e, 1), v) - self.pos(max(u - e, -1), v)
        pv = self.pos(u, min(v + e, 1.05)) - self.pos(u, max(v - e, 0))
        n = pu.cross(pv).normalized()
        return n if n.z > 0 else -n


ORIENT = {
    'front': lambda a, d: (a, -d),
    'back': lambda a, d: (-a, d),
    'right': lambda a, d: (d, a),
    'left': lambda a, d: (-d, -a),
}
SIDE_NAMES = {'front': '正面', 'back': '背面', 'right': '右側', 'left': '左側'}


def ring_roof(tx, ty, ex, ey, z0, drop, lift):
    slopes = []
    for nm in ('front', 'back', 'right', 'left'):
        if nm in ('front', 'back'):
            t_hw, e_hw, t_d, e_d = tx, ex, ty, ey
        else:
            t_hw, e_hw, t_d, e_d = ty, ey, tx, ex

        def mk(t_hw=t_hw, e_hw=e_hw, t_d=t_d, e_d=e_d, nm=nm):
            hw = lambda v: lerp(t_hw, e_hw, v)
            dep = lambda v: lerp(t_d, e_d, v)
            zf = lambda u, v: z0 - drop * fcurve(v) + lift * abs(u) ** 3 * v * v
            vstart = lambda a: 0.0 if abs(a) <= t_hw else (abs(a) - t_hw) / (e_hw - t_hw)
            return Slope(nm, hw, dep, zf, ORIENT[nm], vstart)
        slopes.append(mk())

    def surf_z(x, y):
        vf = (abs(y) - ty) / (ey - ty)
        vs = (abs(x) - tx) / (ex - tx)
        v = clamp(max(vf, vs), 0.0, 1.05)
        if vf >= vs:
            u = x / lerp(tx, ex, v)
        else:
            u = y / lerp(ty, ey, v)
        return z0 - drop * fcurve(v) + lift * min(1.0, abs(u)) ** 3 * v * v
    return slopes, surf_z


def xieshan_roof(rx, ex, ey, z0, drop, lift, v0):
    slopes = []
    for nm in ('front', 'back'):
        def mkf(nm=nm):
            hw = lambda v: rx if v <= v0 else lerp(rx, ex, (v - v0) / (1 - v0))
            dep = lambda v: v * ey
            bf = lambda v: max(0.0, (v - v0) / (1 - v0))
            zf = lambda u, v: z0 - drop * fcurve(v) + lift * abs(u) ** 3 * bf(v) ** 2
            vstart = lambda a: 0.0 if abs(a) <= rx else v0 + (abs(a) - rx) / (ex - rx) * (1 - v0)
            return Slope(nm, hw, dep, zf, ORIENT[nm], vstart)
        slopes.append(mkf())
    for nm in ('right', 'left'):
        def mks(nm=nm):
            hw = lambda s: lerp(v0 * ey, ey, s)
            dep = lambda s: lerp(rx, ex, s)
            zf = lambda u, s: z0 - drop * fcurve(v0 + (1 - v0) * s) + lift * abs(u) ** 3 * s * s
            vstart = lambda a: 0.0 if abs(a) <= v0 * ey else (abs(a) - v0 * ey) / (ey - v0 * ey)
            return Slope(nm, hw, dep, zf, ORIENT[nm], vstart)
        slopes.append(mks())

    def surf_z(x, y):
        vf = abs(y) / ey
        vg = -1.0
        if abs(x) > rx:
            s = (abs(x) - rx) / (ex - rx)
            vg = v0 + (1 - v0) * s
        v = clamp(max(vf, vg), 0.0, 1.05)
        return z0 - drop * fcurve(v)
    return slopes, surf_z


def roof_build(P, label, slopes, v_kinks=(), deck_t=0.2):
    """望板、椽、板瓦、筒瓦、瓦當、滴水、封簷板。"""
    deck = mb(P, 'deck', solidify=deck_t)
    pan = mb(P, 'tile_pan')
    tube = mb(P, 'tile')
    cap = mb(P, 'tile_cap')
    raft = mb(P, 'rafter')
    fas = mb(P, 'blue')
    T = 0.30          # 筒瓦間距
    TL = 0.33         # 每片瓦長
    for sl in slopes:
        sn = SIDE_NAMES[sl.name]
        # --- 椽 ---
        e_hw = sl.hw(1.0)
        nr = int(2 * e_hw / 0.27)
        for r in range(nr):
            a = -e_hw + (r + 0.5) * 2 * e_hw / nr
            vs = max(sl.vstart(a) + 0.02, 0.5)
            if vs > 0.96:
                continue
            pts = []
            for i in range(9):
                v = lerp(vs, 1.02, i / 8)
                vv = min(v, 1.0)
                u = clamp(a / sl.hw(vv), -1, 1)
                p = sl.pos(u, vv)
                if v > 1.0:
                    p = p + (sl.pos(u, 1.0) - sl.pos(u, 0.98)).normalized() * (v - 1.0) * 4.0
                pts.append(p - sl.normal(u, vv) * 0.17)
            sweep(raft, pts, circle(0.055, 8), smooth=True)
            step(P, '釘設%s%s第 %d 根椽' % (label, sn, r + 1))
        # --- 望板 ---
        vs_list = sorted(set([i / 18 for i in range(19)] + list(v_kinks)))
        nu = 30
        verts, faces = [], []
        for i, v in enumerate(vs_list):
            for j in range(nu + 1):
                u = -1 + 2 * j / nu
                verts.append(sl.pos(u, v))
        for i in range(len(vs_list) - 1):
            for j in range(nu):
                a = i * (nu + 1) + j
                faces.append((a, a + 1, a + nu + 2, a + nu + 1))
        deck.add(verts, faces, smooth=True)
        step(P, '鋪%s%s望板' % (label, sn))
        # --- 封簷板 ---
        pts = [sl.pos(-1 + 2 * j / 40, 1.0) + Vector((0, 0, -0.06)) for j in range(41)]
        sweep(fas, pts, [(-0.06, -0.24), (0.06, -0.24), (0.06, 0.04), (-0.06, 0.04)], smooth=False)
        step(P, '安裝%s%s封簷板' % (label, sn))
        # --- 瓦 ---
        nrow = int(2 * e_hw / T)
        for r in range(nrow):
            a = -e_hw + (r + 0.5) * 2 * e_hw / nrow
            vs = sl.vstart(a) + 0.008
            if vs > 0.97:
                continue
            # 沿坡取樣
            samp = []
            for i in range(41):
                v = lerp(vs, 1.0, i / 40)
                u = clamp(a / sl.hw(v), -1, 1)
                samp.append((sl.pos(u, v), sl.normal(u, v)))
            cum = [0.0]
            for i in range(1, len(samp)):
                cum.append(cum[-1] + (samp[i][0] - samp[i - 1][0]).length)
            total = cum[-1]

            def at(s):
                for i in range(1, len(cum)):
                    if cum[i] >= s:
                        t = (s - cum[i - 1]) / max(cum[i] - cum[i - 1], 1e-9)
                        p = samp[i - 1][0].lerp(samp[i][0], t)
                        nrm = samp[i - 1][1].lerp(samp[i][1], t).normalized()
                        tan = (samp[i][0] - samp[i - 1][0]).normalized()
                        return p, nrm, tan
                return samp[-1][0], samp[-1][1], (samp[-1][0] - samp[-2][0]).normalized()

            # 板瓦（凹）— 位於兩列筒瓦之間，一條連續瓦壟
            a2 = a + T / 2
            if abs(a2) < e_hw - 0.05:
                vs2 = sl.vstart(a2) + 0.008
                if vs2 < 0.97:
                    pp = []
                    for i in range(25):
                        v = lerp(vs2, 1.0, i / 24)
                        u = clamp(a2 / sl.hw(v), -1, 1)
                        pp.append(sl.pos(u, v) + sl.normal(u, v) * 0.1)
                    sweep(pan, pp, [(-0.15, 0.035), (-0.07, 0.0), (0.0, -0.012), (0.07, 0.0), (0.15, 0.035)],
                          cap=False, closed_prof=False, smooth=True)
                    step(P, '鋪%s%s第 %d 壟板瓦' % (label, sn, r + 1))
            # 筒瓦（凸）— 一片一片
            ntile = max(1, int(total / TL))
            for k in range(ntile):
                s0, s1 = k * total / ntile, (k + 1) * total / ntile
                rings = []
                for q, (s, rad, lift_) in enumerate(((s0, 0.072, 0.0), ((s0 + s1) / 2, 0.08, 0.004), (s1 - 0.004, 0.086, 0.012))):
                    p, nrm, tan = at(s)
                    side = tan.cross(nrm).normalized()
                    c = p + nrm * (0.1 + lift_)
                    rings.append([c + side * rad * math.cos(th) + nrm * rad * math.sin(th)
                                  for th in [math.pi * i / 8 for i in range(9)]])
                verts = [v for rg in rings for v in rg]
                faces = []
                for q in range(2):
                    for i in range(8):
                        faces.append((q * 9 + i, q * 9 + i + 1, (q + 1) * 9 + i + 1, (q + 1) * 9 + i))
                tube.add(verts, faces, smooth=True)
                step(P, '鋪%s%s第 %d 列第 %d 片筒瓦' % (label, sn, r + 1, k + 1))
            # 瓦當
            p, nrm, tan = at(total)
            side = tan.cross(nrm).normalized()
            c0 = p + nrm * 0.1 + tan * 0.005
            pts = [c0, c0 + tan * 0.035]
            sweep(cap, pts, circle(0.092, 12), side_hint=side, smooth=False)
            step(P, '安%s%s第 %d 列瓦當' % (label, sn, r + 1))
            # 滴水（介於兩列筒瓦之間、懸於簷口）
            if abs(a2) < e_hw - 0.05:
                u2 = clamp(a2 / sl.hw(1.0), -1, 1)
                pe = sl.pos(u2, 1.0)
                ne = sl.normal(u2, 1.0)
                te = (sl.pos(u2, 1.0) - sl.pos(u2, 0.98)).normalized()
                se = te.cross(ne).normalized()
                q0 = pe + ne * 0.11 + te * 0.01
                poly = [q0 - se * 0.14, q0 + se * 0.14, q0 + se * 0.08 - ne * 0.1 + te * 0.03, q0 - ne * 0.16 + te * 0.04,
                        q0 - se * 0.08 - ne * 0.1 + te * 0.03]
                back = [p_ - te * 0.03 for p_ in poly]
                verts = poly + back
                n5 = len(poly)
                faces = [tuple(range(n5)), tuple(n5 + i for i in reversed(range(n5)))]
                for i in range(n5):
                    j = (i + 1) % n5
                    faces.append((i, n5 + i, n5 + j, j))
                cap.add(verts, faces)
                step(P, '安%s%s第 %d 塊滴水' % (label, sn, r + 1))


def hip_ridges(P, label, slopes, v_from=0.0):
    """四條垂脊與翹角。"""
    m = mb(P, 'ridge')
    orn = mb(P, 'ridge_light')
    prof = [(-0.15, -0.12), (0.15, -0.12), (0.15, 0.1), (0.1, 0.18), (-0.1, 0.18), (-0.15, 0.1)]
    names = {('front', 1): '右前', ('front', -1): '左前', ('back', 1): '左後', ('back', -1): '右後'}
    for sl in slopes:
        if sl.name not in ('front', 'back'):
            continue
        for u in (1.0, -1.0):
            pts, scl = [], []
            for i in range(31):
                v = lerp(v_from, 1.0, i / 30)
                pts.append(sl.pos(u, v) + Vector((0, 0, 0.2)))
                scl.append(1.0)
            p1 = sl.pos(u, 1.0)
            d = sl.pos(u, 1.0) - sl.pos(u, 0.97)
            dh = Vector((d.x, d.y, 0)).normalized()
            for i in range(1, 11):
                s = i / 10
                pts.append(p1 + dh * (0.6 * s) + Vector((0, 0, 0.2 + 0.18 * s + 0.5 * s ** 2.2)))
                scl.append(1.0 - 0.3 * s)
            sweep(m, pts, prof, scales=scl)
            step(P, '安裝%s%s垂脊與翹角' % (label, names[(sl.name, int(u))]))
            # 脊端捲草飾
            tip = pts[-1]
            curl = [tip + dh * (0.12 * math.sin(t)) + Vector((0, 0, 0.12 * (1 - math.cos(t)))) for t in
                    [math.pi * 1.2 * i / 10 for i in range(11)]]
            sweep(orn, curl, circle(0.07, 8), smooth=True)
            step(P, '安裝%s%s翹角捲草飾' % (label, names[(sl.name, int(u))]))


# ---------------------------------------------------------------------------
# 斗栱、樑枋、燈籠
# ---------------------------------------------------------------------------
def bracket_set(P, x, y, z0, dirb, nout, scale, label):
    teal, blue, red = mb(P, 'teal', bevel=0.01), mb(P, 'blue', bevel=0.008), mb(P, 'red_wood', bevel=0.008)
    gold = mb(P, 'gold')
    dirb = Vector(dirb).normalized()
    nout = Vector(nout).normalized()
    c = Vector((x, y, z0))
    s = scale
    up = Vector((0, 0, 1))
    rot = axis_frame(dirb)
    box(teal, c + up * 0.11 * s, (0.38, 0.38, 0.22 * s), rot)
    bar(blue, c - dirb * 0.5 + up * 0.3 * s, c + dirb * 0.5 + up * 0.3 * s, 0.18 * s, 0.16)
    bar(red, c - nout * 0.2 + up * 0.3 * s, c + nout * 0.75 * s + up * 0.3 * s, 0.18 * s, 0.16)
    for p in (c - dirb * 0.45, c + dirb * 0.45, c + nout * 0.62 * s):
        box(teal, p + up * 0.47 * s, (0.2, 0.2, 0.14 * s), rot)
    o2 = c + nout * 0.62 * s
    bar(blue, o2 - dirb * 0.7 + up * 0.63 * s, o2 + dirb * 0.7 + up * 0.63 * s, 0.18 * s, 0.16)
    bar(red, c - nout * 0.2 + up * 0.63 * s, c + nout * 1.25 * s + up * 0.63 * s, 0.18 * s, 0.16)
    # 昂嘴金飾
    box(gold, c + nout * 1.27 * s + up * 0.63 * s, (0.06, 0.06, 0.14 * s), axis_frame(nout))
    for p in (o2 - dirb * 0.62, o2 + dirb * 0.62, c + nout * 1.12 * s):
        box(teal, p + up * 0.79 * s, (0.2, 0.2, 0.14 * s), rot)
    step(P, '安裝%s：坐斗、兩跳華栱、瓜栱、令栱與散斗' % label)


def beams_and_brackets(P, label, ring, top_z, roof_z, per_bay=2, lantern=True, hx=0, hy=0, drop=1.45):
    """ring：逆時針柱位。樑枋、平板枋、斗栱、挑簷枋、燈籠。"""
    red, blue, teal, gold = mb(P, 'red_wood', bevel=0.01), mb(P, 'blue', bevel=0.01), mb(P, 'teal', bevel=0.01), mb(P, 'gold')
    n = len(ring)
    cen = Vector((0, 0, 0))
    for i in range(n):
        a = Vector((ring[i][0], ring[i][1], 0))
        b = Vector((ring[(i + 1) % n][0], ring[(i + 1) % n][1], 0))
        d = (b - a).normalized()
        a2, b2 = a + d * 0.2, b - d * 0.2
        bar(red, a2 + Vector((0, 0, top_z - 0.55)), b2 + Vector((0, 0, top_z - 0.55)), 0.3, 0.24)
        step(P, '架設%s第 %d 間額枋' % (label, i + 1))
        bar(blue, a2 + Vector((0, 0, top_z - 0.18)), b2 + Vector((0, 0, top_z - 0.18)), 0.4, 0.3)
        # 大額枋上下金線
        nout = Vector((d.y, -d.x, 0))
        for dz in (0.17, -0.17):
            bar(gold, a2 + nout * 0.155 + Vector((0, 0, top_z - 0.18 + dz)), b2 + nout * 0.155 + Vector((0, 0, top_z - 0.18 + dz)), 0.025, 0.01)
        step(P, '架設%s第 %d 間彩繪大額枋（藍底金線）' % (label, i + 1))
        bar(teal, a - d * 0.15 + Vector((0, 0, top_z + 0.05)), b + d * 0.15 + Vector((0, 0, top_z + 0.05)), 0.1, 0.42)
        step(P, '鋪設%s第 %d 間平板枋' % (label, i + 1))
    # 斗栱
    for i in range(n):
        a = Vector((ring[i][0], ring[i][1], 0))
        b = Vector((ring[(i + 1) % n][0], ring[(i + 1) % n][1], 0))
        d = (b - a).normalized()
        nout = Vector((d.y, -d.x, 0))
        pts = [(a, '柱頭')] + [(a.lerp(b, (k + 1) / (per_bay + 1)), '補間') for k in range(per_bay)]
        for k, (p, kind) in enumerate(pts):
            no = nout
            if kind == '柱頭':
                prev = Vector((ring[i - 1][0], ring[i - 1][1], 0))
                dprev = (a - prev).normalized()
                no = (nout + Vector((dprev.y, -dprev.x, 0))).normalized()
            outer = p + no * 1.3
            avail = roof_z(outer.x, outer.y) - 0.3 - (top_z + 0.1)
            s = clamp(avail / 0.86, 0.45, 1.0)
            bracket_set(P, p.x, p.y, top_z + 0.1, d, no, s, '%s第 %d 間%s斗栱' % (label, i + 1, kind))
    # 挑簷枋：沿各邊外移，貼合屋面下緣
    for i in range(n):
        a = Vector((ring[i][0], ring[i][1], 0))
        b = Vector((ring[(i + 1) % n][0], ring[(i + 1) % n][1], 0))
        d = (b - a).normalized()
        nout = Vector((d.y, -d.x, 0))
        pts = []
        for k in range(13):
            p = a.lerp(b, k / 12) + nout * 1.2
            z = min(top_z + 0.1 + 0.95, roof_z(p.x, p.y) - 0.32)
            pts.append(Vector((p.x, p.y, z)))
        pts[0] -= d * 0.3
        pts[-1] += d * 0.3
        sweep(blue, pts, [(-0.08, -0.1), (0.08, -0.1), (0.08, 0.1), (-0.08, 0.1)], smooth=False)
        step(P, '架設%s第 %d 面挑簷枋' % (label, i + 1))
    if lantern:
        lanterns(P, label, ring, top_z, hx, hy, drop)


def lanterns(P, label, ring, top_z, hx, hy, drop=1.45):
    lm, cm, cord = mb(P, 'lantern'), mb(P, 'lantern_cap'), mb(P, 'lantern_cap')
    prof = [(0.0, 0.0), (0.07, 0.0), (0.09, 0.02), (0.2, 0.09), (0.25, 0.22), (0.26, 0.32), (0.25, 0.42),
            (0.2, 0.55), (0.09, 0.62), (0.07, 0.64), (0.0, 0.64)]
    for i, (px, py) in enumerate(ring):
        ox = math.copysign(0.45, px) if abs(abs(px) - hx) < 1e-6 else 0.0
        oy = math.copysign(0.45, py) if abs(abs(py) - hy) < 1e-6 else 0.0
        x, y = px + ox, py + oy
        zb = top_z - drop
        lathe(lm, (x, y, zb), prof, seg=16)
        lathe(cm, (x, y, zb - 0.05), [(0, 0), (0.11, 0), (0.11, 0.07), (0, 0.07)], seg=12, smooth=False)
        lathe(cm, (x, y, zb + 0.61), [(0, 0), (0.11, 0), (0.11, 0.07), (0, 0.07)], seg=12, smooth=False)
        sweep(cord, [(x, y, zb + 0.68), (x, y, top_z - 0.4)], circle(0.012, 6))
        # 流蘇
        sweep(cord, [(x, y, zb - 0.05), (x, y, zb - 0.32)], circle(0.025, 6), scales=[1.0, 0.4])
        step(P, '懸掛%s第 %d 盞白燈籠（含吊繩與流蘇）' % (label, i + 1))


def column(P, x, y, z0, h, r, label):
    base = mb(P, 'base_stone')
    red = mb(P, 'red_lacquer')
    lathe(base, (x, y, z0), [(0, 0), (r + 0.17, 0), (r + 0.17, 0.08), (r + 0.12, 0.14), (r + 0.1, 0.2), (r + 0.06, 0.24), (0, 0.24)], seg=20)
    step(P, '安放%s柱礎' % label)
    lathe(red, (x, y, z0 + 0.24), [(0, 0), (r, 0), (r * 1.03, h * 0.3), (r * 0.98, h * 0.7), (r * 0.92, h - 0.24), (0, h - 0.24)], seg=22)
    step(P, '豎立%s朱紅木柱（高 %.2f m）' % (label, h))


# ---------------------------------------------------------------------------
# 6–7. 下層木構、樑枋斗栱
# ---------------------------------------------------------------------------
def lower_ring():
    pts = []
    for i in range(7):
        pts.append((-CL / 2 + i * CL / 6, -CW / 2))
    for j in range(1, 3):
        pts.append((CL / 2, -CW / 2 + j * CW / 3))
    for i in range(6, -1, -1):
        pts.append((-CL / 2 + i * CL / 6, CW / 2))
    for j in range(2, 0, -1):
        pts.append((-CL / 2, -CW / 2 + j * CW / 3))
    return pts


def upper_ring():
    pts = []
    for i in range(6):
        pts.append((-UL / 2 + i * UL / 5, -UW / 2))
    for j in range(1, 3):
        pts.append((UL / 2, -UW / 2 + j * UW / 3))
    for i in range(5, -1, -1):
        pts.append((-UL / 2 + i * UL / 5, UW / 2))
    for j in range(2, 0, -1):
        pts.append((-UL / 2, -UW / 2 + j * UW / 3))
    return pts


def build_lower_wood(lower_z):
    P = 5
    ring = lower_ring()
    for i, (x, y) in enumerate(ring):
        column(P, x, y, FY, COL_H + 0.2, 0.21, '下層第 %d 根簷柱' % (i + 1))
    for i, (x, y) in enumerate(upper_ring()):
        column(P, x, y, FY, UCT - FY, 0.19, '第 %d 根通柱（貫通上下層）' % (i + 1))
    # 內牆：朱紅隔扇
    ur = upper_ring()
    wall = mb(P, 'red_wood', bevel=0.005)
    lat = mb(P, 'window_dark')
    n = len(ur)
    for i in range(n):
        a = Vector((ur[i][0], ur[i][1], 0))
        b = Vector((ur[(i + 1) % n][0], ur[(i + 1) % n][1], 0))
        d = (b - a).normalized()
        a2, b2 = a + d * 0.2, b - d * 0.2
        zt = CT - 0.7
        bar(wall, a2 + Vector((0, 0, FY + 0.45)), b2 + Vector((0, 0, FY + 0.45)), 0.9, 0.1)
        bar(wall, a2 + Vector((0, 0, zt - 0.08)), b2 + Vector((0, 0, zt - 0.08)), 0.16, 0.12)
        bar(lat, a2 + Vector((0, 0, (FY + 0.9 + zt - 0.16) / 2)), b2 + Vector((0, 0, (FY + 0.9 + zt - 0.16) / 2)), zt - 0.16 - FY - 0.9, 0.05)
        L = (b2 - a2).length
        nv = max(2, int(L / 0.2))
        for k in range(1, nv):
            p = a2.lerp(b2, k / nv)
            bar(wall, p + Vector((0, 0, FY + 0.9)), p + Vector((0, 0, zt - 0.16)), 0.04, 0.08)
        for k in range(1, 5):
            z = lerp(FY + 0.9, zt - 0.16, k / 5)
            bar(wall, a2 + Vector((0, 0, z)), b2 + Vector((0, 0, z)), 0.035, 0.08)
        step(P, '安裝下層內圈第 %d 間朱紅隔扇（含格心櫺條）' % (i + 1))
    # 欄杆
    rail = mb(P, 'red_wood', bevel=0.006)
    m = len(ring)
    for i in range(m):
        a = Vector((ring[i][0], ring[i][1], 0))
        b = Vector((ring[(i + 1) % m][0], ring[(i + 1) % m][1], 0))
        d = (b - a).normalized()
        a2, b2 = a + d * 0.24, b - d * 0.24
        bar(rail, a2 + Vector((0, 0, FY + 0.95)), b2 + Vector((0, 0, FY + 0.95)), 0.1, 0.12)
        bar(rail, a2 + Vector((0, 0, FY + 0.3)), b2 + Vector((0, 0, FY + 0.3)), 0.08, 0.1)
        step(P, '安裝第 %d 間欄杆扶手與地栿' % (i + 1))
        L = (b2 - a2).length
        nb = int(L / 0.22)
        for k in range(1, nb):
            p = a2.lerp(b2, k / nb)
            bar(rail, p + Vector((0, 0, FY + 0.34)), p + Vector((0, 0, FY + 0.9)), 0.05, 0.05)
            step(P, '安裝第 %d 間欄杆第 %d 支望柱' % (i + 1, k))


# ---------------------------------------------------------------------------
# 9. 上層樓身
# ---------------------------------------------------------------------------
def build_upper_body():
    P = 8
    ur = upper_ring()
    wallm = mb(P, 'plaster', bevel=0.008)
    win = mb(P, 'window_dark')
    frame = mb(P, 'red_wood', bevel=0.005)
    n = len(ur)
    zb, zt = UY, UCT - 0.72
    for i in range(n):
        a = Vector((ur[i][0], ur[i][1], 0))
        b = Vector((ur[(i + 1) % n][0], ur[(i + 1) % n][1], 0))
        d = (b - a).normalized()
        nout = Vector((d.y, -d.x, 0))
        a2, b2 = a + d * 0.19, b - d * 0.19
        mid = (a + b) / 2
        L = (b2 - a2).length
        w = min(0.62, L * 0.4)
        wz0, wz1 = zb + 0.42, zb + 0.42 + 0.5
        # 窗洞四周牆體
        bar(wallm, a2 + Vector((0, 0, (zb + wz0) / 2)), b2 + Vector((0, 0, (zb + wz0) / 2)), wz0 - zb, 0.2)
        bar(wallm, a2 + Vector((0, 0, (wz1 + zt) / 2)), b2 + Vector((0, 0, (wz1 + zt) / 2)), zt - wz1, 0.2)
        bar(wallm, a2 + Vector((0, 0, (wz0 + wz1) / 2)), mid - d * w / 2 + Vector((0, 0, (wz0 + wz1) / 2)), wz1 - wz0, 0.2)
        bar(wallm, mid + d * w / 2 + Vector((0, 0, (wz0 + wz1) / 2)), b2 + Vector((0, 0, (wz0 + wz1) / 2)), wz1 - wz0, 0.2)
        step(P, '砌上層第 %d 間白牆並留窗洞' % (i + 1))
        cz = (wz0 + wz1) / 2
        bar(win, mid - d * w / 2 + Vector((0, 0, cz)) - nout * 0.04, mid + d * w / 2 + Vector((0, 0, cz)) - nout * 0.04, wz1 - wz0, 0.04)
        for k in (-1, 0, 1):
            p = mid + d * (k * w / 4) + nout * 0.02
            bar(frame, p + Vector((0, 0, wz0)), p + Vector((0, 0, wz1)), 0.035, 0.04)
        bar(frame, mid - d * w / 2 + nout * 0.02 + Vector((0, 0, cz)), mid + d * w / 2 + nout * 0.02 + Vector((0, 0, cz)), 0.035, 0.04)
        for zz in (wz0, wz1):
            bar(frame, mid - d * (w / 2 + 0.05) + nout * 0.05 + Vector((0, 0, zz)), mid + d * (w / 2 + 0.05) + nout * 0.05 + Vector((0, 0, zz)), 0.06, 0.06)
        step(P, '安裝上層第 %d 間小方窗（窗框與十字櫺）' % (i + 1))
    # 匾額：懸於正面中間開間的樑枋前
    step(P, '懸掛「迎曦門」匾額')


def plaque_object():
    P = 8
    w, h, t = 1.95, 0.76, 0.1
    x, y, z = 0.0, -UW / 2 - 0.42, UCT - 0.5
    me = bpy.data.meshes.new('09_plaque')
    hx, hz = w / 2, h / 2
    v = [(-hx, -t / 2, -hz), (hx, -t / 2, -hz), (hx, -t / 2, hz), (-hx, -t / 2, hz),
         (-hx, t / 2, -hz), (hx, t / 2, -hz), (hx, t / 2, hz), (-hx, t / 2, hz)]
    f = [(0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7), (1, 5, 6, 2), (3, 2, 6, 7), (4, 5, 1, 0)]
    me.from_pydata(v, [], f)
    uv = me.uv_layers.new(name='UVMap')
    uvs = {0: [(0, 0), (1, 0), (1, 1), (0, 1)]}
    for poly in me.polygons:
        for li, loop in enumerate(poly.loop_indices):
            uv.data[loop].uv = uvs.get(poly.index, [(0.02, 0.02)] * 4)[li]
    ob = bpy.data.objects.new('09_plaque', me)
    ob.location = (x, y, z)
    ob.rotation_euler = (math.radians(-8), 0, 0)
    ob.data.materials.append(MATS['plaque'])
    COLL[P].objects.link(ob)


# ---------------------------------------------------------------------------
# 11. 上層屋頂附件：山花、博風、圍脊、正脊、燕尾
# ---------------------------------------------------------------------------
def xieshan_extras(P, slopes):
    front = slopes[0]
    zg = UZ0 - UD * fcurve(UV0)
    gable = mb(P, 'red_lacquer', bevel=0.005)
    board = mb(P, 'blue')
    ridge = mb(P, 'ridge')
    light = mb(P, 'ridge_light')
    gold = mb(P, 'gold')
    for sx in (1, -1):
        nm = '右' if sx > 0 else '左'
        poly = []
        for i in range(13):
            v = UV0 * (1 - i / 12)
            poly.append((-v * UEY, front.zf(1.0, v) - 0.05))
        for i in range(1, 13):
            v = UV0 * i / 12
            poly.append((v * UEY, front.zf(1.0, v) - 0.05))
        xg = sx * (URX - 0.25)
        prism_yz(gable, poly, xg - 0.06, xg + 0.06)
        step(P, '砌%s側山花（山牆三角）' % nm)
        for sy in (-1, 1):
            pts = [Vector((sx * (URX + 0.06), sy * UEY * UV0 * (1 - i / 16), front.zf(1.0, UV0 * (1 - i / 16)) + 0.08)) for i in range(17)]
            sweep(board, pts, [(-0.06, -0.3), (0.06, -0.3), (0.06, 0.06), (-0.06, 0.06)], side_hint=(sx, 0, 0), smooth=False)
            step(P, '安裝%s側%s博風板' % (nm, '前' if sy < 0 else '後'))
        # 懸魚
        box(gold, (sx * (URX + 0.1), 0, UZ0 - 0.55), (0.05, 0.28, 0.42))
        step(P, '安裝%s側懸魚' % nm)
        # 圍脊（山花底緣）
        pts = [(sx * URX, y, zg + 0.18) for y in (-UV0 * UEY - 0.1, UV0 * UEY + 0.1)]
        sweep(ridge, pts, [(-0.13, -0.12), (0.13, -0.12), (0.13, 0.12), (-0.13, 0.12)], smooth=False)
        step(P, '安裝%s側圍脊' % nm)
    # 正脊
    half = URX + 0.35
    zr = lambda x: UZ0 + 0.3 + 0.55 * max(0.0, (abs(x) - 0.55 * URX) / (half - 0.55 * URX)) ** 3
    pts = [Vector((x, 0, zr(x))) for x in [-half + 2 * half * i / 60 for i in range(61)]]
    sweep(ridge, pts, [(-0.2, -0.3), (0.2, -0.3), (0.2, 0.22), (0.12, 0.32), (-0.12, 0.32), (-0.2, 0.22)], smooth=True)
    step(P, '砌築正脊脊身')
    for sy in (-1, 1):
        pp = [Vector((x, sy * 0.205, zr(x) + 0.0)) for x in [-0.85 * URX + 1.7 * URX * i / 40 for i in range(41)]]
        sweep(light, pp, [(-0.006, -0.11), (0.006, -0.11), (0.006, 0.11), (-0.006, 0.11)], side_hint=(0, sy, 0), smooth=False)
        step(P, '鑲嵌正脊%s側白色剪黏飾帶' % ('前' if sy < 0 else '後'))
    # 燕尾
    for sx in (1, -1):
        e = Vector((sx * half, 0, zr(half)))
        for sy in (-1, 1):
            pts, scl = [], []
            for i in range(15):
                t = i / 14
                pts.append(e + Vector((sx * (0.95 * t), sy * (0.22 * t), 0.15 * t + 1.05 * t ** 2.2)))
                scl.append(1.0 - 0.6 * t)
            sweep(ridge, pts, [(-0.13, -0.18), (0.13, -0.18), (0.13, 0.15), (-0.13, 0.15)], scales=scl, side_hint=(0, 1, 0))
            step(P, '安裝%s端燕尾%s叉' % ('右' if sx > 0 else '左', '前' if sy < 0 else '後'))
    # 脊剎寶珠
    lathe(gold, (0, 0, UZ0 + 0.6), [(0, 0), (0.18, 0.02), (0.12, 0.12), (0.2, 0.2), (0.24, 0.34), (0.2, 0.48), (0.08, 0.58), (0, 0.66)], seg=20)
    step(P, '安放脊剎寶珠')


def lower_roof_top_ridge(P):
    m = mb(P, 'ridge')
    for (ax, ay), (bx, by) in [((-LTX, -LTY), (LTX, -LTY)), ((LTX, -LTY), (LTX, LTY)), ((LTX, LTY), (-LTX, LTY)), ((-LTX, LTY), (-LTX, -LTY))]:
        d = Vector((bx - ax, by - ay, 0)).normalized()
        a = Vector((ax, ay, LZ0 + 0.1)) - d * 0.15
        b = Vector((bx, by, LZ0 + 0.1)) + d * 0.15
        sweep(m, [a, b], [(-0.14, -0.15), (0.14, -0.15), (0.14, 0.14), (-0.14, 0.14)], smooth=False)
    step(P, '安裝下層屋頂上緣承椽枋與壓脊')


# ---------------------------------------------------------------------------
# 12. 廣場與街景
# ---------------------------------------------------------------------------
def build_plaza():
    P = 11
    # 石柱與鏈條
    post = mb(P, 'bollard')
    chain = mb(P, 'chain')
    posts = rect_ring(PL / 2 + 3.2, PW / 2 + 3.2, 2.6)
    for i, (x, y) in enumerate(posts):
        lathe(post, (x, y, 0.0), [(0, 0), (0.15, 0), (0.15, 0.06), (0.12, 0.1), (0.12, 0.72), (0.15, 0.76), (0.15, 0.84), (0.08, 0.9), (0, 0.92)], seg=14)
        step(P, '安置廣場第 %d 根石柱' % (i + 1))
    for i in range(len(posts)):
        a = Vector((posts[i][0], posts[i][1], 0.68))
        b = Vector((posts[(i + 1) % len(posts)][0], posts[(i + 1) % len(posts)][1], 0.68))
        if (abs(a.y + b.y) / 2 > PW / 2 + 3.0) and abs((a.x + b.x) / 2) < AW + 0.5:
            continue  # 拱道前後留出通道
        pts = [a.lerp(b, t) - Vector((0, 0, 0.22 * math.sin(math.pi * t))) for t in [k / 14 for k in range(15)]]
        sweep(chain, pts, circle(0.022, 6))
        step(P, '掛設第 %d 跨鐵鏈' % (i + 1))
    # 石椅
    bench = mb(P, 'bench_stone', bevel=0.03)
    for i, x in enumerate((-12.5, -9.0, 9.0, 12.5)):
        box(bench, (x, -PW / 2 - 6.3, 0.22), (2.4, 0.6, 0.44))
        step(P, '安置正面第 %d 張石椅' % (i + 1))
    for i, y in enumerate((-3, 3)):
        for sx in (-1, 1):
            box(bench, (sx * (PL / 2 + 6.0), y, 0.22), (0.6, 2.4, 0.44))
            step(P, '安置%s側石椅' % ('右' if sx > 0 else '左'))
    # 花台與矮灌木
    planter, hedge = mb(P, 'bench_stone', bevel=0.03), mb(P, 'hedge', bevel=0.12)
    for i, (x, y, w, d) in enumerate([(-18.5, -12.5, 7.0, 2.2), (18.5, -12.5, 7.0, 2.2)]):
        box(planter, (x, y, 0.3), (w, d, 0.6))
        box(hedge, (x, y, 0.85), (w - 0.3, d - 0.3, 0.6))
        step(P, '砌築第 %d 座花台並栽植矮灌木' % (i + 1))
    # 棕櫚
    trunk, frond = mb(P, 'palm_trunk'), mb(P, 'frond')
    palms = [(17.5, -9.5, 9.5), (21.0, -4.5, 11.0), (-21.0, 4.5, 10.0), (19.0, 9.0, 8.5), (-17.0, 11.0, 9.0)]
    for i, (x, y, h) in enumerate(palms):
        lean = Vector((rng.uniform(-0.4, 0.4), rng.uniform(-0.4, 0.4), 0))
        pts = [Vector((x, y, 0)) + lean * (t * t) + Vector((0, 0, h * t)) for t in [k / 16 for k in range(17)]]
        sweep(trunk, pts, circle(0.24, 12), scales=[1.25 - 0.4 * (k / 16) for k in range(17)])
        step(P, '栽植第 %d 棵大王椰子樹幹' % (i + 1))
        top = pts[-1]
        for k in range(16):
            yaw = 2 * math.pi * k / 16 + rng.uniform(-0.15, 0.15)
            dirh = Vector((math.cos(yaw), math.sin(yaw), 0))
            rise = rng.uniform(0.15, 0.7)
            L = rng.uniform(3.0, 3.9)
            spine = [top + dirh * (L * t) + Vector((0, 0, rise * L * t - 1.6 * L * t * t * 0.55)) for t in [q / 12 for q in range(13)]]
            side = dirh.cross(Vector((0, 0, 1))).normalized()
            verts, faces = [], []
            for q, p in enumerate(spine):
                t = q / 12
                w = 0.55 * math.sin(math.pi * min(1.0, t * 1.1 + 0.05))
                verts += [p - side * w + Vector((0, 0, -0.12 * w)), p, p + side * w + Vector((0, 0, -0.12 * w))]
            for q in range(12):
                b0 = q * 3
                faces += [(b0, b0 + 1, b0 + 4, b0 + 3), (b0 + 1, b0 + 2, b0 + 5, b0 + 4)]
            frond.add(verts, faces, smooth=True)
            step(P, '第 %d 棵椰子樹第 %d 片羽葉' % (i + 1, k + 1))
    # 闊葉樹
    leaf = mb(P, 'tree_leaf')
    bark = mb(P, 'palm_trunk')
    for i, (x, y, s) in enumerate([(-24, -8, 3.2), (-25.5, 1.5, 3.6), (25.5, 2.0, 3.0), (-22, 13, 3.4), (24, 13.5, 3.3)]):
        sweep(bark, [(x, y, 0), (x + 0.2, y, 2.2 * s / 3)], circle(0.22, 10), scales=[1.2, 0.8])
        for k in range(9):
            c = Vector((x + rng.uniform(-1.2, 1.2) * s / 3, y + rng.uniform(-1.2, 1.2) * s / 3, 2.4 * s / 3 + rng.uniform(0.6, 2.2) * s / 3))
            r = rng.uniform(0.9, 1.5) * s / 3
            prof = [(0, -r)] + [(r * math.sin(math.pi * q / 8) * rng.uniform(0.85, 1.12), -r * math.cos(math.pi * q / 8)) for q in range(1, 8)] + [(0, r)]
            lathe(leaf, c, prof, seg=12)
        step(P, '栽植第 %d 棵榕樹' % (i + 1))


def build_environment():
    """地面、廣場鋪面、道路與標線、周邊街屋（常駐，不列入階段）。"""
    E = 'env'
    road = mb(-1, 'asphalt')
    road.add([(-900, -900, -0.02), (900, -900, -0.02), (900, 900, -0.02), (-900, 900, -0.02)], [(0, 1, 2, 3)])
    pave = mb(-1, 'paving')
    hx, hy = 26.0, 17.0
    pave.add([(-hx, -hy, 0.0), (hx, -hy, 0.0), (hx, hy, 0.0), (-hx, hy, 0.0)], [(0, 1, 2, 3)])
    curb = mb(-1, 'curb', bevel=0.02)
    for (ax, ay), (bx, by) in [((-hx, -hy), (hx, -hy)), ((hx, -hy), (hx, hy)), ((hx, hy), (-hx, hy)), ((-hx, hy), (-hx, -hy))]:
        bar(curb, (ax, ay, 0.06), (bx, by, 0.06), 0.16, 0.3)
    mark = mb(-1, 'marking')
    # 前方道路：雙黃線改以白色分向線、車道虛線、停止線、斑馬線
    for y in (-24.5, -31.0):
        for k in range(-30, 31):
            x = k * 4.5
            box(mark, (x, y, 0.0), (2.4, 0.15, 0.01))
    box(mark, (0, -27.8, 0.0), (300, 0.15, 0.01))
    box(mark, (0, -27.55, 0.0), (300, 0.15, 0.01))
    for k in range(10):
        box(mark, (-9 + k * 0.9 - 30, -21.0, 0.0), (0.45, 5.0, 0.01))
    for y in (24.5, 31.0):
        for k in range(-30, 31):
            box(mark, (k * 4.5, y, 0.0), (2.4, 0.15, 0.01))
    for x in (-33.0, 33.0):
        for k in range(-30, 31):
            box(mark, (x, k * 4.5, 0.0), (0.15, 2.4, 0.01))
    # 周邊街屋（遠景）
    cols = ['bldg_a', 'bldg_b', 'bldg_c', 'bldg_d']
    blocks = []
    for i in range(16):
        x0 = -84 + i * 10.5
        blocks.append((x0, 58 + rng.uniform(0, 5), rng.uniform(8.5, 10.5), rng.uniform(9, 19)))
        blocks.append((x0, -64 - rng.uniform(0, 5), rng.uniform(8.5, 10.5), rng.uniform(9, 17)))
    for j in range(11):
        y0 = -50 + j * 10
        blocks.append((-64 - rng.uniform(0, 4), y0, rng.uniform(8, 10), rng.uniform(9, 21)))
        blocks.append((64 + rng.uniform(0, 4), y0, rng.uniform(8, 10), rng.uniform(9, 21)))
    # 外圈街廓（遠景填充）
    for ring_r in (105, 150, 210):
        n = int(2 * math.pi * ring_r / 16)
        for i in range(n):
            a = 2 * math.pi * i / n + rng.uniform(-0.03, 0.03)
            x, y = ring_r * math.cos(a) * 1.15, ring_r * math.sin(a)
            blocks.append((x, y, rng.uniform(10, 15), rng.uniform(8, 22)))
    for k, (x, y, w, h) in enumerate(blocks):
        m = mb(-1, cols[k % 4], bevel=0.05)
        box(m, (x, y, h / 2), (w, 9.0, h))
        mw = mb(-1, 'bldg_window')
        floors = int((h - 3.5) / 3.2)
        for f in range(floors):
            z = 4.6 + f * 3.2
            face = -1 if y > 0 else 1
            if abs(x) > 60:
                box(mw, (x - math.copysign(w / 2 + 0.02, x), y, z), (0.05, 7.6, 1.5))
            else:
                box(mw, (x, y + face * 4.52, z), (w - 1.2, 0.05, 1.5))
        if rng.random() < 0.55:
            sm = mb(-1, rng.choice(['sign_red', 'sign_white', 'sign_blue']))
            if abs(x) <= 60:
                box(sm, (x, y + (-1 if y > 0 else 1) * 4.62, min(h - 2, 9.0)), (w * 0.8, 0.12, rng.uniform(2.0, 4.5)))
            else:
                box(sm, (x - math.copysign(w / 2 + 0.12, x), y, min(h - 2, 9.0)), (0.12, 6.5, rng.uniform(2.0, 4.5)))


# ---------------------------------------------------------------------------
# 材質
# ---------------------------------------------------------------------------
MATS = {}


def new_mat(name, base, rough=0.6, metal=0.0, var=0.0, var2=None, noise_scale=0.0, bump=0.0, spec=0.5, sss=0.0):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = rough
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Specular IOR Level'].default_value = spec
    if sss:
        bsdf.inputs['Subsurface Weight'].default_value = sss
    if var or noise_scale:
        attr = nt.nodes.new('ShaderNodeAttribute')
        attr.attribute_type = 'GEOMETRY'
        attr.attribute_name = 'var'
        fac = attr.outputs['Fac']
        if noise_scale:
            tc = nt.nodes.new('ShaderNodeTexCoord')
            nz = nt.nodes.new('ShaderNodeTexNoise')
            nz.inputs['Scale'].default_value = noise_scale
            nz.inputs['Detail'].default_value = 6.0
            nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
            mad = nt.nodes.new('ShaderNodeMath')
            mad.operation = 'MULTIPLY_ADD'
            mad.inputs[1].default_value = 0.65
            nt.links.new(fac, mad.inputs[0])
            mul = nt.nodes.new('ShaderNodeMath')
            mul.operation = 'MULTIPLY'
            mul.inputs[1].default_value = 0.35
            nt.links.new(nz.outputs['Fac'], mul.inputs[0])
            nt.links.new(mul.outputs[0], mad.inputs[2])
            fac = mad.outputs[0]
            if bump:
                bp = nt.nodes.new('ShaderNodeBump')
                bp.inputs['Strength'].default_value = bump
                nz2 = nt.nodes.new('ShaderNodeTexNoise')
                nz2.inputs['Scale'].default_value = noise_scale * 6
                nz2.inputs['Detail'].default_value = 8.0
                nt.links.new(tc.outputs['Object'], nz2.inputs['Vector'])
                nt.links.new(nz2.outputs['Fac'], bp.inputs['Height'])
                nt.links.new(bp.outputs['Normal'], bsdf.inputs['Normal'])
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        lo = var2 if var2 is not None else tuple(clamp(c * (1 - var), 0, 1) for c in base)
        hi = tuple(clamp(c * (1 + var), 0, 1) for c in base) if var2 is None else base
        ramp.color_ramp.elements[0].color = (*lo, 1)
        ramp.color_ramp.elements[1].color = (*hi, 1)
        nt.links.new(fac, ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        bsdf.inputs['Base Color'].default_value = (*base, 1)
    MATS[name] = m
    return m


def brick_mat(name, c1, c2, mortar, scale, mortar_size, rough=0.85, row_h=0.5, brick_w=0.5, bump=0.25):
    m = bpy.data.materials.new(name)
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    bsdf.inputs['Roughness'].default_value = rough
    tc = nt.nodes.new('ShaderNodeTexCoord')
    br = nt.nodes.new('ShaderNodeTexBrick')
    br.inputs['Color1'].default_value = (*c1, 1)
    br.inputs['Color2'].default_value = (*c2, 1)
    br.inputs['Mortar'].default_value = (*mortar, 1)
    br.inputs['Scale'].default_value = scale
    br.inputs['Mortar Size'].default_value = mortar_size
    br.inputs['Row Height'].default_value = row_h
    br.inputs['Brick Width'].default_value = brick_w
    br.offset = 0.5
    nt.links.new(tc.outputs['Object'], br.inputs['Vector'])
    nt.links.new(br.outputs['Color'], bsdf.inputs['Base Color'])
    if bump:
        bp = nt.nodes.new('ShaderNodeBump')
        bp.inputs['Strength'].default_value = bump
        bp.invert = True
        nt.links.new(br.outputs['Fac'], bp.inputs['Height'])
        nt.links.new(bp.outputs['Normal'], bsdf.inputs['Normal'])
    MATS[name] = m
    return m


def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def build_materials():
    new_mat('mortar', srgb('#b8ad98'), 0.95)
    new_mat('sandstone', srgb('#d9c79e'), 0.88, var=0.0, var2=srgb('#b9a273'), noise_scale=1.6, bump=0.35)
    new_mat('sandstone_dark', srgb('#cbb68a'), 0.88, var2=srgb('#a8915f'), noise_scale=1.6, bump=0.35)
    new_mat('slab', srgb('#b9b1a0'), 0.9, var2=srgb('#9a927f'), noise_scale=2.0, bump=0.2)
    new_mat('plaster', srgb('#f2eee4'), 0.85, var2=srgb('#e3ddd0'), noise_scale=3.0, bump=0.05)
    new_mat('plaster_trim', srgb('#f4f1ea'), 0.8)
    new_mat('coping', srgb('#d9d3c6'), 0.8)
    new_mat('red_lacquer', srgb('#b02a1f'), 0.38, spec=0.6)
    new_mat('red_wood', srgb('#9e2a1e'), 0.5)
    new_mat('blue', srgb('#23509f'), 0.45)
    new_mat('teal', srgb('#2b8f86'), 0.5)
    new_mat('gold', srgb('#d6a43a'), 0.32, metal=1.0)
    new_mat('base_stone', srgb('#8f877a'), 0.85, var2=srgb('#7b7366'), noise_scale=4.0, bump=0.2)
    new_mat('deck', srgb('#6e2a1a'), 0.8)
    new_mat('tile', srgb('#d95b22'), 0.55, var2=srgb('#b8461a'), noise_scale=0.8)
    new_mat('tile_pan', srgb('#c24d1c'), 0.6, var2=srgb('#a73f17'), noise_scale=0.8)
    new_mat('tile_cap', srgb('#c9521e'), 0.55)
    new_mat('rafter', srgb('#b5381f'), 0.5)
    new_mat('ridge', srgb('#2a4a95'), 0.4)
    new_mat('ridge_light', srgb('#e9edf2'), 0.4)
    new_mat('window_dark', srgb('#1a1310'), 0.6)
    new_mat('lantern', srgb('#f4f0e6'), 0.6, sss=0.15)
    new_mat('lantern_cap', srgb('#2a2220'), 0.5)
    new_mat('bollard', srgb('#cdbf9f'), 0.85, var2=srgb('#b8a983'), noise_scale=3.0, bump=0.2)
    new_mat('chain', srgb('#4a4c52'), 0.35, metal=1.0)
    new_mat('bench_stone', srgb('#c4b593'), 0.85, var2=srgb('#a99872'), noise_scale=2.0, bump=0.25)
    new_mat('hedge', srgb('#3f6b2a'), 0.9, var2=srgb('#2d5220'), noise_scale=5.0, bump=0.8)
    new_mat('palm_trunk', srgb('#8c7a63'), 0.9, var2=srgb('#6e5e4a'), noise_scale=6.0, bump=0.5)
    new_mat('frond', srgb('#4f8f3a'), 0.65, var2=srgb('#33702a'), noise_scale=1.0)
    new_mat('tree_leaf', srgb('#4e8a36'), 0.8, var2=srgb('#2f6224'), noise_scale=2.5, bump=0.6)
    new_mat('asphalt', srgb('#55565a'), 0.92, var2=srgb('#46474b'), noise_scale=0.6, bump=0.15)
    brick_mat('paving', srgb('#aaa9a2'), srgb('#97968f'), srgb('#7d7c76'), 1.0, 0.012, row_h=0.6, brick_w=1.2, bump=0.15)
    new_mat('curb', srgb('#a39d90'), 0.85)
    new_mat('marking', srgb('#ecebe6'), 0.7)
    new_mat('bldg_a', srgb('#cbbfae'), 0.85)
    new_mat('bldg_b', srgb('#a9b3b8'), 0.85)
    new_mat('bldg_c', srgb('#d8cfc2'), 0.85)
    new_mat('bldg_d', srgb('#b5876a'), 0.85)
    new_mat('bldg_window', srgb('#3c4a57'), 0.2, spec=0.8)
    new_mat('sign_red', srgb('#c0302a'), 0.6)
    new_mat('sign_white', srgb('#f0eee8'), 0.6)
    new_mat('sign_blue', srgb('#2d5aa0'), 0.6)
    # 匾額
    m = bpy.data.materials.new('plaque')
    try:
        m.use_nodes = True
    except Exception:
        pass
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(os.path.join(HERE, 'textures', 'plaque.png'))
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.45
    MATS['plaque'] = m


# ---------------------------------------------------------------------------
# 物件化
# ---------------------------------------------------------------------------
COLL = {}


def make_collections():
    root = bpy.context.scene.collection
    env = bpy.data.collections.new('00_環境')
    root.children.link(env)
    COLL[-1] = env
    for i, (nm, _) in enumerate(PHASES):
        c = bpy.data.collections.new('%02d_%s' % (i + 1, nm))
        root.children.link(c)
        COLL[i] = c


def finalize():
    for key, b in BUILDERS.items():
        if not b.f:
            continue
        me = bpy.data.meshes.new(b.name)
        me.from_pydata(b.v, [], b.f)
        me.update()
        attr = me.attributes.new('var', 'FLOAT', 'FACE')
        attr.data.foreach_set('value', b.var)
        me.polygons.foreach_set('use_smooth', b.smooth)
        me.materials.append(MATS[b.mat])
        ob = bpy.data.objects.new(b.name, me)
        COLL[b.phase].objects.link(ob)
        if b.bevel:
            md = ob.modifiers.new('bevel', 'BEVEL')
            md.width = b.bevel
            md.segments = 2
            md.limit_method = 'ANGLE'
            md.angle_limit = math.radians(40)
            md.harden_normals = False
        if b.solidify:
            md = ob.modifiers.new('solidify', 'SOLIDIFY')
            md.thickness = b.solidify
            md.offset = 0.0


# ---------------------------------------------------------------------------
# 燈光、相機、算圖
# ---------------------------------------------------------------------------
def setup_world():
    sc = bpy.context.scene
    w = bpy.data.worlds.new('sky')
    try:
        w.use_nodes = True
    except Exception:
        pass
    sc.world = w
    nt = w.node_tree
    bg = nt.nodes['Background']
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_disc = False
    sky.sun_elevation = math.radians(56)
    sky.sun_rotation = math.radians(205)
    sky.altitude = 30.0
    try:
        sky.air_density = 1.0
        sky.aerosol_density = 1.6
    except Exception:
        pass
    # 雲：把視線方向投影到高空平面，再以噪波閾值切出雲塊
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    zc = nt.nodes.new('ShaderNodeMath'); zc.operation = 'MAXIMUM'; zc.inputs[1].default_value = 0.03
    nt.links.new(sep.outputs['Z'], zc.inputs[0])
    dx = nt.nodes.new('ShaderNodeMath'); dx.operation = 'DIVIDE'
    dy = nt.nodes.new('ShaderNodeMath'); dy.operation = 'DIVIDE'
    nt.links.new(sep.outputs['X'], dx.inputs[0]); nt.links.new(zc.outputs[0], dx.inputs[1])
    nt.links.new(sep.outputs['Y'], dy.inputs[0]); nt.links.new(zc.outputs[0], dy.inputs[1])
    comb = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(dx.outputs[0], comb.inputs['X']); nt.links.new(dy.outputs[0], comb.inputs['Y'])
    comb.inputs['Z'].default_value = 3.7
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 0.9
    nz.inputs['Detail'].default_value = 10.0
    nz.inputs['Roughness'].default_value = 0.62
    nt.links.new(comb.outputs['Vector'], nz.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[1].position = 0.7
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    fade = nt.nodes.new('ShaderNodeMapRange')
    fade.inputs['From Min'].default_value = 0.03
    fade.inputs['From Max'].default_value = 0.3
    nt.links.new(sep.outputs['Z'], fade.inputs['Value'])
    fac = nt.nodes.new('ShaderNodeMath'); fac.operation = 'MULTIPLY'
    nt.links.new(ramp.outputs['Color'], fac.inputs[0]); nt.links.new(fade.outputs['Result'], fac.inputs[1])
    bw = nt.nodes.new('ShaderNodeRGBToBW')
    nt.links.new(sky.outputs['Color'], bw.inputs['Color'])
    bright = nt.nodes.new('ShaderNodeMath'); bright.operation = 'MULTIPLY'; bright.inputs[1].default_value = 1.9
    nt.links.new(bw.outputs['Val'], bright.inputs[0])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    sock = lambda coll, ident: next(x for x in coll if x.identifier == ident)
    nt.links.new(fac.outputs[0], sock(mix.inputs, 'Factor_Float'))
    nt.links.new(sky.outputs['Color'], sock(mix.inputs, 'A_Color'))
    nt.links.new(bright.outputs[0], sock(mix.inputs, 'B_Color'))
    nt.links.new(sock(mix.outputs, 'Result_Color'), bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 0.18
    sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
    sc.collection.objects.link(sun)
    sun.data.energy = 5.2
    sun.data.angle = math.radians(0.6)
    sun.data.color = (1.0, 0.96, 0.9)
    to_sun = Vector((-0.38, -0.62, 0.95)).normalized()
    sun.rotation_euler = (-to_sun).to_track_quat('-Z', 'Y').to_euler()
    sc.render.engine = 'CYCLES'
    cp = sc.cycles
    cp.device = 'CPU'
    cp.samples = args.samples
    cp.use_adaptive_sampling = True
    cp.adaptive_threshold = 0.02
    cp.use_denoising = True
    try:
        cp.denoiser = 'OPENIMAGEDENOISE'
    except Exception:
        pass
    cp.max_bounces = 6
    cp.diffuse_bounces = 3
    cp.glossy_bounces = 3
    cp.transparent_max_bounces = 4
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    sc.view_settings.exposure = 0.0
    sc.render.image_settings.file_format = 'JPEG'
    sc.render.image_settings.quality = 92


def add_camera(name, loc, target=None, rot=None, lens=35, shift_y=0.0, shift_x=0.0):
    cam = bpy.data.objects.new(name, bpy.data.cameras.new(name))
    bpy.context.scene.collection.objects.link(cam)
    cam.location = loc
    cam.data.lens = lens
    cam.data.sensor_width = 36
    cam.data.shift_y = shift_y
    cam.data.shift_x = shift_x
    cam.data.clip_end = 600
    if rot is not None:
        cam.rotation_euler = rot
    else:
        d = Vector(target) - Vector(loc)
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    return cam


def render(cam, path, w, h, samples=None):
    sc = bpy.context.scene
    sc.camera = cam
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    if samples:
        sc.cycles.samples = samples
    sc.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print('  rendered %s in %.0fs' % (os.path.basename(path), time.time() - t), flush=True)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable('cycles', default_set=True)
    build_materials()
    make_collections()

    lower_slopes, lower_z = ring_roof(LTX, LTY, LEX, LEY, LZ0, LD, LLIFT)
    upper_slopes, upper_z = xieshan_roof(URX, UEX, UEY, UZ0, UD, ULIFT, UV0)

    build_core()
    build_walls()
    build_arch()
    build_top()
    build_parapet()
    build_lower_wood(lower_z)
    beams_and_brackets(6, '下層', lower_ring(), CT, lower_z, per_bay=2, hx=CL / 2, hy=CW / 2)
    roof_build(7, '下層屋頂', lower_slopes)
    hip_ridges(7, '下層屋頂', lower_slopes)
    lower_roof_top_ridge(7)
    build_upper_body()
    beams_and_brackets(9, '上層', upper_ring(), UCT, upper_z, per_bay=1, hx=UL / 2, hy=UW / 2, drop=0.88)
    roof_build(10, '上層屋頂', upper_slopes, v_kinks=(UV0,))
    hip_ridges(10, '上層屋頂', upper_slopes, v_from=UV0)
    xieshan_extras(10, upper_slopes)
    build_plaza()
    build_environment()
    finalize()
    plaque_object()
    setup_world()
    print('built %d steps, %d objects in %.0fs' % (len(STEPS), len(bpy.data.objects), time.time() - t0), flush=True)

    with open(os.path.join(OUT, 'steps.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['步驟', '階段編號', '階段', '說明'])
        w.writerows(STEPS)
    with open(os.path.join(OUT, 'phases.csv'), 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.writer(f)
        w.writerow(['階段編號', '階段', '起', '迄', '步數', '說明'])
        for i, (nm, note) in enumerate(PHASES):
            ns = [s[0] for s in STEPS if s[1] == i + 1]
            w.writerow([i + 1, nm, ns[0], ns[-1], len(ns), note])

    # 相機：依照片推算（鏡頭 30 mm、相機高 1.6 m、水平拍攝加垂直位移）
    cam_photo = add_camera('Cam_照片視角', (1.2, -44.0, 1.6), rot=(math.radians(90), 0, 0), lens=30, shift_y=0.25)
    cam_aerial = add_camera('Cam_鳥瞰', (-34.0, -38.0, 23.0), target=(0.5, 0.0, 7.2), lens=42)
    cam_corner = add_camera('Cam_翹角特寫', (-17.5, -15.5, 11.2), target=(-9.6, -6.6, 11.2), lens=55)
    bpy.context.scene.camera = cam_photo

    R = os.path.join(OUT, 'renders')
    W = args.res
    if args.render in ('test',):
        render(cam_photo, os.path.join(R, 'test_photo.jpg'), 900, 600, 24)
        render(cam_aerial, os.path.join(R, 'test_aerial.jpg'), 900, 600, 24)
    if args.render in ('hero', 'all'):
        render(cam_photo, os.path.join(R, 'photo_angle.jpg'), W, int(W * 2 / 3))
        render(cam_aerial, os.path.join(R, 'aerial.jpg'), W, int(W * 2 / 3))
        render(cam_corner, os.path.join(R, 'roof_corner.jpg'), W, int(W * 2 / 3))
    if args.render in ('phases', 'all'):
        for p in range(len(PHASES)):
            for i, c in COLL.items():
                if i >= 0:
                    c.hide_render = i > p
            render(cam_aerial, os.path.join(R, 'phase_%02d.jpg' % (p + 1)), 960, 640, max(24, args.samples // 4))
        for i, c in COLL.items():
            c.hide_render = False

    if not args.no_blend:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'east_gate.blend'), compress=True)
    if args.glb:
        for ob in bpy.data.objects:
            for md in ob.modifiers:
                if md.type == 'BEVEL':
                    md.show_viewport = md.show_render = False
        for name, mat in MATS.items():
            nt = mat.node_tree
            bsdf = nt.nodes.get('Principled BSDF')
            if not bsdf or name == 'plaque':
                continue
            inp = bsdf.inputs['Base Color']
            for lk in list(inp.links):
                src = lk.from_node
                col = None
                if src.type == 'VALTORGB':
                    a, b = src.color_ramp.elements[0].color, src.color_ramp.elements[-1].color
                    col = [(a[i] + b[i]) / 2 for i in range(3)] + [1]
                elif src.type == 'TEX_BRICK':
                    col = list(src.inputs['Color1'].default_value)
                nt.links.remove(lk)
                if col:
                    inp.default_value = col
            nrm = bsdf.inputs['Normal']
            for lk in list(nrm.links):
                nt.links.remove(lk)
        hidden = [o for o in COLL[-1].objects if o.name.startswith('00_bldg') or o.name.startswith('00_sign')]
        for o in hidden:
            o.hide_set(True)
            o.hide_render = True
        bpy.ops.export_scene.gltf(filepath=os.path.join(OUT, 'east_gate.glb'), export_format='GLB',
                                  export_apply=True, export_cameras=False, export_lights=False,
                                  use_visible=True, export_draco_mesh_compression_enable=True,
                                  export_draco_mesh_compression_level=7)
    print('done in %.0fs' % (time.time() - t0), flush=True)


main()
