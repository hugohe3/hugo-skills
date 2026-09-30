"""Figures for chapters 2 and 5: site climate / solar resource charts and the power-system sketch.

Usage:
    python make_context_figures.py climate --nasa NASA_POWER.json --out 2-figures [--table work/太阳能资源统计.md]
    python make_context_figures.py diagram --params params.json --out 2-figures

climate  draws 图2.1-2 (temperature + precipitation) and 图2.2-1 (monthly irradiation, beam + diffuse)
         from a NASA POWER climatology JSON (fetch_nasa_power.py), and writes the monthly table with the
         GB/T 37526-2019 richness / stability / direct-ratio grades.
diagram  draws 图5.3-1 (project power-system sketch) from the "diagram" block of params.json.
Figure numbers and titles can be overridden through the "figures" map of params.json.
"""
import argparse
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch
import numpy as np

BLUE, ORANGE, AQUA, PURPLE = "#2a78d6", "#eb6834", "#1baf7a", "#8a5cd1"
INK, INK2, MUTED, GRID, AXIS, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
WIDTH = 6.3
MONTHS = [f"{m}月" for m in range(1, 13)]
KEYS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
KIND_COLOR = {"pv": BLUE, "wind": PURPLE, "bess": AQUA, "station": ORANGE, "load": BLUE, "grid": MUTED}

CJK_FONTS = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC",
             "WenQuanYi Micro Hei"]
installed = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({
    "font.family": [f for f in CJK_FONTS if f in installed] + ["sans-serif"],
    "axes.unicode_minus": False, "font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.dpi": 220,
})


def style(ax, ylabel=""):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", visible=False)
    if ylabel:
        ax.set_ylabel(ylabel)


def save(fig, out, no, title, overrides):
    ov = overrides.get(no, {})
    if ov is False:
        plt.close(fig)
        return
    name = f"图{ov.get('no', no)}_{ov.get('title', title)}.png"
    fig.tight_layout()
    fig.savefig(out / name)
    plt.close(fig)
    print("saved", name)


# ---------------------------------------------------------------- climate
def grade(value, bands):
    for threshold, label in bands:
        if value >= threshold:
            return label
    return bands[-1][1]


def climate(args, overrides):
    data = json.loads(args.nasa.read_text(encoding="utf-8"))
    p = data["properties"]["parameter"]
    monthly = lambda key: np.array([p[key][k] * n for k, n in zip(KEYS, DAYS)])
    ghi, dhi = monthly("ALLSKY_SFC_SW_DWN"), monthly("ALLSKY_SFC_SW_DIFF")
    beam = ghi - dhi
    x = np.arange(1, 13)

    fig, ax = plt.subplots(figsize=(WIDTH, 3.2))
    ax.bar(x, beam, width=0.62, color=BLUE, edgecolor=SURFACE, linewidth=1.5, label="水平面直接辐射")
    ax.bar(x, dhi, width=0.62, bottom=beam, color=ORANGE, edgecolor=SURFACE, linewidth=1.5, label="散射辐射")
    top = np.ceil(ghi.max() * 1.18 / 50) * 50
    for xi, total in zip(x, ghi):
        ax.text(xi, total + top * 0.012, f"{total:.0f}", ha="center", va="bottom", fontsize=8, color=INK2)
    ax.set_xticks(x, MONTHS)
    ax.set_ylim(0, top)
    ax.legend(frameon=False, loc="upper left", fontsize=9, ncol=2)
    style(ax, "月辐射量（kWh/m²）")
    save(fig, args.out, "2.2-1", "场址逐月太阳辐射量", overrides)

    # temperature and precipitation use two panels instead of a dual axis
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 2.9))
    ax = axes[0]
    tmax, tmean, tmin = ([p[k][m] for m in KEYS] for k in ("T2M_MAX", "T2M", "T2M_MIN"))
    ax.plot(x, tmax, color=ORANGE, linewidth=1.6, marker="o", markersize=3.5, label="极端最高")
    ax.plot(x, tmean, color=INK2, linewidth=2, marker="o", markersize=3.5, label="月平均")
    ax.plot(x, tmin, color=BLUE, linewidth=1.6, marker="o", markersize=3.5, label="极端最低")
    ax.axhline(0, color=AXIS, linewidth=0.8)
    ax.set_xticks([1, 4, 7, 10], ["1月", "4月", "7月", "10月"])
    lo, hi = np.floor(min(tmin) / 5 - 1) * 5, np.ceil(max(tmax) / 5 + 3) * 5
    ax.set_ylim(lo, hi)
    ax.legend(frameon=False, loc="upper left", fontsize=7.5, ncol=3)
    ax.set_title("气温（℃）", fontsize=9, color=INK2)
    style(ax)
    ax = axes[1]
    pre = monthly("PRECTOTCORR")
    ax.bar(x, pre, width=0.62, color=AQUA, edgecolor=SURFACE, linewidth=1)
    ax.set_xticks([1, 4, 7, 10], ["1月", "4月", "7月", "10月"])
    ax.set_ylim(0, np.ceil(pre.max() * 1.25 / 5) * 5)
    ax.set_title(f"降水量（mm），年合计 {pre.sum():.0f} mm", fontsize=9, color=INK2)
    style(ax)
    save(fig, args.out, "2.1-2", "场址逐月气温及降水", overrides)

    # GB/T 37526-2019 grades
    daily = np.array([p["ALLSKY_SFC_SW_DWN"][k] for k in KEYS])
    total = ghi.sum()
    rw, rd = daily.min() / daily.max(), beam.sum() / total
    rich = grade(total, [(1750, "最丰富（A）"), (1400, "很丰富（B）"), (1050, "丰富（C）"), (-1, "一般（D）")])
    stable = grade(rw, [(0.47, "很稳定（A）"), (0.36, "稳定（B）"), (0.28, "一般（C）"), (-1, "欠稳定（D）")])
    direct = grade(rd, [(0.6, "很高（A）"), (0.5, "高（B）"), (0.35, "中（C）"), (-1, "低（D）")])
    lon, lat, elev = data["geometry"]["coordinates"]
    rows = ["| 月份 | 水平面总辐射量（kWh/m²） | 水平面直接辐射量（kWh/m²） | 散射辐射量（kWh/m²） | "
            "水平面总辐射量（MJ/m²） | 月平均日辐照量（kWh/m²·d） | 月平均气温（℃） | 降水量（mm） |",
            "|---|---|---|---|---|---|---|---|"]
    for i in range(12):
        rows.append(f"| {i + 1} 月 | {ghi[i]:.1f} | {beam[i]:.1f} | {dhi[i]:.1f} | {ghi[i] * 3.6:.1f} | "
                    f"{daily[i]:.2f} | {tmean[i]:.1f} | {pre[i]:.1f} |")
    rows.append(f"| 全年 | {total:.1f} | {beam.sum():.1f} | {dhi.sum():.1f} | {total * 3.6:.1f} | "
                f"{total / 365:.2f} | {p['T2M']['ANN']:.1f} | {pre.sum():.1f} |")
    text = "\n".join([
        f"# 场址太阳能资源统计\n\nNASA POWER {data['header']['range']}；数据点 {lat}°N、{lon}°E，海拔 {elev:.0f} m。\n",
        *rows, "",
        "## 资源等级（GB/T 37526—2019）\n",
        f"- 丰富程度：GHR = {total:.1f} kWh/m²（{total * 3.6:.1f} MJ/m²），{rich}",
        f"- 稳定程度：Rw = {daily.min():.2f}/{daily.max():.2f} = {rw:.3f}，{stable}",
        f"- 直射比：Rd = {beam.sum():.1f}/{total:.1f} = {rd:.3f}，{direct}",
        f"- 季节占比：春 {ghi[2:5].sum() / total:.1%}，夏 {ghi[5:8].sum() / total:.1%}，"
        f"秋 {ghi[8:11].sum() / total:.1%}，冬 {(ghi[11] + ghi[0] + ghi[1]) / total:.1%}", ""])
    if args.table:
        args.table.parent.mkdir(parents=True, exist_ok=True)
        args.table.write_text(text, encoding="utf-8")
        print("saved", args.table)
    else:
        print(text)


# ---------------------------------------------------------------- system diagram
def box(ax, x, y, w, h, text, kind):
    color = KIND_COLOR.get(kind, BLUE)
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.06",
                                facecolor=color + "22", edgecolor=color, linewidth=1.4,
                                linestyle="--" if kind == "grid" else "-"))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=7.5, color=INK, linespacing=1.45)


def arrow(ax, start, end, dashed=False, both=False):
    ax.annotate("", xy=end, xytext=start, arrowprops=dict(arrowstyle="<|-|>" if both else "-|>", color=INK2,
                                                          lw=1.2, linestyle="--" if dashed else "-"))


def label(ax, x, y, text, ha="center", va="center"):
    ax.text(x, y, text, ha=ha, va=va, fontsize=7.5, color=INK2, linespacing=1.35)


def default_sources(p):
    src = []
    if p.get("pv_ac"):
        dc = f"\n直流侧 {p['pv_dc']:g} 万 kWp" if p.get("pv_dc") else ""
        src.append({"kind": "pv", "label": f"光伏发电单元\n交流侧 {p['pv_ac']:g} 万 kW{dc}", "link": "35 kV 集电线路"})
    if p.get("wind"):
        src.append({"kind": "wind", "label": f"风力发电单元\n{p['wind']:g} 万 kW", "link": "35 kV 集电线路"})
    if p.get("bess_power"):
        mw, mwh = p["bess_power"] * 10, p.get("bess_energy", 0) * 10
        src.append({"kind": "bess", "label": f"电化学储能\n{mw:g} MW / {mwh:g} MWh", "link": "35 kV 电缆"})
    return src


def diagram(args, overrides):
    p = json.loads(args.params.read_text(encoding="utf-8"))
    d = p.get("diagram", {})
    sources = d.get("sources") or default_sources(p)
    grid = d.get("grid")
    H = 7.6 if grid else 6.4
    fig, ax = plt.subplots(figsize=(WIDTH, 3.4 * H / 6.4))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, H)
    ax.axis("off")

    hub_y = 3.55                                   # centre line of the station boxes
    n = len(sources)
    bh = 1.6 if n <= 2 else 1.25
    span_lo, span_hi = 1.2, 6.0 if not grid else 6.2
    centers = [hub_y] if n == 1 else list(np.linspace(span_hi - bh / 2, span_lo + bh / 2, n))
    for s, cy in zip(sources, centers):
        box(ax, 0.1, cy - bh / 2, 2.6, bh, s["label"], s.get("kind", "pv"))
        end_y = hub_y + (cy - hub_y) * 0.35
        arrow(ax, (2.7, cy), (4.5, end_y))
        if s.get("link"):
            above = cy >= hub_y
            label(ax, 2.8, cy + (0.3 if above else -0.3), s["link"], ha="left")

    box(ax, 4.5, hub_y - 0.95, 2.1, 1.9, d.get("booster", "220 kV\n新能源升压站"), "station")
    box(ax, 9.3, hub_y - 0.95, 2.0, 1.9, d.get("load_sub", "220 kV\n负荷侧变电站"), "station")
    circuits = int(d.get("circuits", 2))
    offsets = [0.0] if circuits == 1 else list(np.linspace(0.3, -0.3, circuits))
    for off in offsets:
        arrow(ax, (6.6, hub_y + off), (9.3, hub_y + off))
    label(ax, 7.95, hub_y + 0.7, d.get("line_top", f"220 kV 直连专线 {circuits} 回"))
    if d.get("line_bottom"):
        label(ax, 7.95, hub_y - 0.7, d["line_bottom"])
    load_label = d.get("load", f"{p.get('load_name', '用电负荷')}\n{p.get('load_rated', 0) * 10:g} MW")
    box(ax, 12.1, hub_y - 1.2, 1.8, 2.4, load_label, "load")
    arrow(ax, (11.3, hub_y), (12.1, hub_y))
    label(ax, 11.7, hub_y + 0.35, d.get("load_link", "35 kV"))

    if grid:
        gy = hub_y + 0.95 + 1.6
        box(ax, 9.3, gy, 2.0, 1.2, grid.get("label", "公共电网"), "grid")
        arrow(ax, (10.3, gy), (10.3, hub_y + 0.95), dashed=True)
        label(ax, 10.5, gy - 0.8, grid.get("link", "关口计量 / 防逆流\n物理分界点"), ha="left")

    ax.plot([0.1, 13.9], [0.85, 0.85], color=AXIS, linewidth=0.8, linestyle="--")
    default_note = ("一体化调控平台统一调度源、储、荷；项目通过防逆流装置接入公共电网，不向电网反送电" if grid else
                    "一体化调控平台统一调度源、储、荷；项目离网运行，不与公共电网连接")
    label(ax, 7.0, 0.45, d.get("footnote", default_note))
    save(fig, args.out, "5.3-1", "项目电力系统接线示意", overrides)


def main():
    ap = argparse.ArgumentParser(description="生成绿电直连申报方案气候资源图和电力系统接线示意图")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("climate", help="NASA POWER 气候与辐射图")
    c.add_argument("--nasa", type=Path, required=True)
    c.add_argument("--table", type=Path, help="输出逐月统计及资源等级 Markdown")
    c.add_argument("--params", type=Path, help="用于图号覆盖")
    c.add_argument("--out", type=Path, default=Path("2-figures"))
    g = sub.add_parser("diagram", help="电力系统接线示意图")
    g.add_argument("--params", type=Path, required=True)
    g.add_argument("--out", type=Path, default=Path("2-figures"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    overrides = {}
    if args.params:
        overrides = json.loads(args.params.read_text(encoding="utf-8")).get("figures", {})
    (climate if args.cmd == "climate" else diagram)(args, overrides)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
