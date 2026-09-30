"""Draw a site sketch: renewable site polygon(s) from a KML, the load location and the distance between them.

Use it when no satellite screenshot is available (or as the schematic 图4.1-1). For a satellite-backed
location map, overlay the KML polygon on the owner's screenshot with the geospatial-converter skill instead.

Usage:
    python make_site_map.py --kml 场址.ovkml --load 89.2425,44.8920 --load-name "新疆宜化化工有限公司\n（负荷侧）" \
        --site-name "新能源场址\n（风电、光伏及储能）" --line-km 70 --out 2-figures/图4.1-1_场址及负荷位置示意.png

Inputs:
    --kml       KML / OVKML with one or more <Polygon> rings, lon/lat in CGCS2000 or WGS84 (the difference is
                far below the drawing resolution)
    --load      "lon,lat" of the load site in decimal degrees
    --line-km   optional planned transmission-line length printed next to the straight-line distance
"""
import argparse
import math
import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon
from matplotlib.ticker import MaxNLocator

BLUE, ORANGE = "#2a78d6", "#eb6834"
INK, INK2, MUTED, GRID = "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
R = 6371.0088   # mean Earth radius, km

CJK = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei"]
installed = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({"font.family": [f for f in CJK if f in installed] + ["sans-serif"], "axes.unicode_minus": False,
                     "savefig.dpi": 220})


def km_between(a, b):
    lo1, la1, lo2, la2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def read_rings(path):
    text = path.read_text(encoding="utf-8-sig")
    rings = []
    for block in re.findall(r"<coordinates>(.*?)</coordinates>", text, re.S):
        pts = [tuple(map(float, p.split(",")[:2])) for p in block.split() if "," in p]
        if len(pts) >= 3:
            rings.append(pts)
    if not rings:
        sys.exit(f"{path} 中没有找到面要素坐标")
    return rings


def centroid(ring):
    """Area centroid (shoelace) of a ring in planar coordinates; returns (cx, cy, |area|)."""
    r = ring + ring[:1]
    cross = [x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(r, r[1:])]
    area = sum(cross) / 2
    cx = sum((a[0] + b[0]) * c for a, b, c in zip(r, r[1:], cross)) / (6 * area)
    cy = sum((a[1] + b[1]) * c for a, b, c in zip(r, r[1:], cross)) / (6 * area)
    return cx, cy, abs(area)


def nice_step(span, target=6):
    raw = span / target
    for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5):
        if step >= raw:
            return step
    return 5


def main():
    ap = argparse.ArgumentParser(description="由 KML 场址范围和负荷坐标绘制场址位置示意图")
    ap.add_argument("--kml", type=Path, required=True)
    ap.add_argument("--load", required=True, help="负荷经纬度 lon,lat")
    ap.add_argument("--load-name", default="用电负荷")
    ap.add_argument("--site-name", default="新能源场址")
    ap.add_argument("--line-km", type=float, help="拟建送出线路长度（km）")
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    load = tuple(float(v) for v in args.load.split(","))
    rings = read_rings(args.kml)
    lat0 = sum(p[1] for r in rings for p in r) / sum(len(r) for r in rings)
    kx = math.cos(math.radians(lat0))           # equirectangular: 1 km has the same length on both axes
    planar = [[(lo * kx, la) for lo, la in r] for r in rings]

    total = sum(centroid(r)[2] for r in planar)
    cx = sum(centroid(r)[0] * centroid(r)[2] for r in planar) / total
    cy = sum(centroid(r)[1] * centroid(r)[2] for r in planar) / total
    site_lonlat = (cx / kx, cy)
    dist = km_between(site_lonlat, load)
    lx, ly = load[0] * kx, load[1]

    fig, ax = plt.subplots(figsize=(6.3, 3.6))
    for r in planar:
        ax.add_patch(Polygon(r, closed=True, facecolor=BLUE + "22", edgecolor=BLUE, linewidth=1.6))
    ax.text(cx, cy, args.site_name.replace("\\n", "\n"), ha="center", va="center", fontsize=8.5, color=INK)
    ax.plot([lx], [ly], marker="s", markersize=8, color=ORANGE)

    # dashed link from the load to the site vertex nearest to it
    ex, ey = min((p for r in planar for p in r), key=lambda p: math.hypot(p[0] - lx, p[1] - ly))
    ax.plot([lx, ex], [ly, ey], color=INK2, linewidth=1, linestyle="--")
    note = f"至场址形心直线距离约 {dist:.0f} km" + (f"，送出线路长度约 {args.line_km:g} km" if args.line_km else "")
    angle = math.degrees(math.atan2(ey - ly, ex - lx))
    if abs(angle) > 90:
        angle += 180
    ax.annotate(note, ((lx + ex) / 2, (ly + ey) / 2), xytext=(0, -5), textcoords="offset points", ha="center",
                va="top", fontsize=8, color=INK2, rotation=angle, rotation_mode="anchor")

    xs = [p[0] for r in planar for p in r] + [lx]
    ys = [p[1] for r in planar for p in r] + [ly]
    padx, pady = (max(xs) - min(xs)) * 0.10, (max(ys) - min(ys)) * 0.30
    x0, x1, y0, y1 = min(xs) - padx, max(xs) + padx, min(ys) - pady, max(ys) + pady
    ax.text(lx, ly + pady * 0.15, args.load_name.replace("\\n", "\n"), ha="center", va="bottom", fontsize=8.5, color=INK)

    # scale bar (rounded to 5/10/20/50 km) and north arrow
    deg_per_km = 1 / (R * math.pi / 180)
    bar_km = next(k for k in (5, 10, 20, 50, 100, 200) if k * deg_per_km >= (x1 - x0) * 0.12 or k == 200)
    bx, by = x0 + (x1 - x0) * 0.05, y0 + pady * 0.35
    ax.plot([bx, bx + bar_km * deg_per_km], [by, by], color=INK, linewidth=2)
    ax.text(bx + bar_km * deg_per_km / 2, by - pady * 0.08, f"{bar_km} km", ha="center", va="top", fontsize=7.5,
            color=INK2)
    nx, ny = x1 - (x1 - x0) * 0.04, y1 - pady * 0.9
    ax.annotate("N", xy=(nx, ny), xytext=(nx, ny - pady * 0.7), ha="center", va="top", fontsize=9, color=INK,
                arrowprops=dict(arrowstyle="-|>", color=INK, lw=1.2))

    ax.set_aspect("equal")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    lon_step, lat_step = nice_step((x1 - x0) / kx), nice_step(y1 - y0)
    lon_ticks = [v for v in (round(k * lon_step, 4) for k in range(int(x0 / kx / lon_step), int(x1 / kx / lon_step) + 2))
                 if x0 <= v * kx <= x1]
    lat_ticks = [v for v in (round(k * lat_step, 4) for k in range(int(y0 / lat_step), int(y1 / lat_step) + 2))
                 if y0 <= v <= y1]
    ax.set_xticks([v * kx for v in lon_ticks], [f"{v:g}°E" for v in lon_ticks])
    ax.set_yticks(lat_ticks, [f"{v:g}°N" for v in lat_ticks])
    ax.tick_params(labelsize=7.5, colors=MUTED, length=0)
    ax.grid(color=GRID, linewidth=0.6)
    for side in ax.spines.values():
        side.set_color(GRID)
    fig.tight_layout()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out)
    print("saved", args.out, f"形心 {site_lonlat[0]:.4f}°E {site_lonlat[1]:.4f}°N，至负荷 {dist:.1f} km")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
