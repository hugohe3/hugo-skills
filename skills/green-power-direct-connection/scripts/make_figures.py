"""Draw the data figures of a green-power direct-connection declaration (chapters 3 and 4).

Usage:
    python make_figures.py --hourly work/hourly.csv --params params.json [--schemes schemes.csv] \
        [--out 2-figures] [--data-xlsx 2-figures/图表数据.xlsx] [--only 3.2-1,4.2-4]

Inputs:
    hourly.csv    8760 h dataset from prepare_hourly.py (power in 万kW)
    params.json   project parameters; see resources/params.example.json
    schemes.csv   optional scale-comparison schemes for figures 4.3-1 / 4.3-2

Every figure is registered under its default outline number (e.g. "4.2-1"). params.json may
renumber, retitle or disable a figure through its "figures" map; --data-xlsx writes the exact
numbers behind each figure so the report text can be checked against them.
"""
import argparse
import json
import math
import sys
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd

# Colorblind-checked categorical slots and chart ink
BLUE, ORANGE, AQUA, YELLOW, PURPLE = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a5cd1"
INK2, MUTED, GRID, AXIS, SURFACE = "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#ffffff"
WIDTH = 6.3   # inches, about 16 cm: the text width of an A4 report page
MONTHS = [f"{m}月" for m in range(1, 13)]

CJK_FONTS = ["Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC", "Source Han Sans SC",
             "WenQuanYi Micro Hei"]
installed = {f.name for f in font_manager.fontManager.ttflist}
plt.rcParams.update({
    # keep only fonts that exist on this machine to avoid a findfont warning per text element
    "font.family": [f for f in CJK_FONTS if f in installed] + ["sans-serif"],
    "axes.unicode_minus": False, "font.size": 10, "axes.edgecolor": AXIS, "axes.labelcolor": INK2,
    "xtick.color": MUTED, "ytick.color": MUTED, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.axisbelow": True, "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.dpi": 220,
})

REGISTRY = {}   # default number -> (default title, function)


def figure(no, title):
    def wrap(fn):
        REGISTRY[no] = (title, fn)
        return fn
    return wrap


# ---------------------------------------------------------------- context
class Ctx:
    def __init__(self, df, p, schemes, out):
        self.df, self.p, self.schemes, self.out = df, p, schemes, out
        self.year = int(df["time"].iloc[0].year)
        self.has_wind = df["wind"].abs().sum() > 0
        self.has_pv = df["pv"].abs().sum() > 0
        self.has_grid = df["grid"].abs().sum() > 0
        self.load_name = p.get("load_name", "负荷")
        self.rated = float(p["load_rated"])
        self.pmax = self.rated * float(p.get("load_max_ratio", 1.0))
        df["re"] = df["pv"] + df["wind"]
        self.re_name = "新能源出力" if (self.has_wind and self.has_pv) else ("风电出力" if self.has_wind else "光伏出力")
        self.src = "新能源" if (self.has_wind and self.has_pv) else ("风电" if self.has_wind else "光伏")
        self.sources = [(c, n, k) for c, n, k in (("pv", "光伏", ORANGE), ("wind", "风电", PURPLE))
                        if df[c].abs().sum() > 0]
        # PV output rates may be quoted against DC capacity ("pv_rate_base") when the hourly series is DC-based
        self.caps = {"pv": p.get("pv_rate_base") or p.get("pv_ac"), "wind": p.get("wind")}
        self.days = self._typical_days()
        self.data = {}   # sheet name -> DataFrame exported with --data-xlsx

    def _typical_days(self):
        daily = self.df.groupby("day")["re"].sum()
        month = self.df.groupby("day")["month"].first()
        auto = {"summer_clear": int(daily[month == 6].idxmax()), "winter_clear": int(daily[month == 12].idxmax()),
                "summer_cloudy": int(daily[month == 6].idxmin())}
        for key, value in self.p.get("typical_days", {}).items():
            mm, dd = (int(x) for x in value.split("-"))
            auto[key] = datetime(self.year, mm, dd).timetuple().tm_yday
        return auto

    def day_label(self, key):
        d = datetime(self.year, 1, 1) + timedelta(days=self.days[key] - 1)
        return f"{d.month}月{d.day}日"

    def day_name(self, key):
        default = {"summer_clear": "夏季晴天", "winter_clear": "冬季晴天", "summer_cloudy": "夏季阴天"}
        return self.p.get("typical_day_names", {}).get(key, default[key])


# ---------------------------------------------------------------- helpers
def nice_top(value, headroom=1.12):
    """Round an axis maximum up to a 1/2/2.5/5 x 10^n step."""
    v = max(value * headroom, 1e-9)
    base = 10 ** math.floor(math.log10(v))
    for m in (1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if m * base >= v:
            return m * base
    return 10 * base


def style(ax, ylabel="", xgrid=False):
    ax.spines[["top", "right", "left"]].set_visible(False)
    ax.tick_params(length=0)
    ax.grid(axis="x", visible=xgrid)
    if ylabel:
        ax.set_ylabel(ylabel)


def hour_axis(ax, step=2):
    ax.set_xticks(range(0, 24, step), [f"{h}:00" for h in range(0, 24, step)])
    ax.set_xlim(-0.5, 23.5)


def month_axis_days(ax, year):
    ax.set_xticks([pd.Timestamp(year, m, 1).dayofyear for m in range(1, 13)], MONTHS)
    ax.set_xlim(1, 365)


def bar_labels(ax, bars, values, fmt, top):
    for b, v in zip(bars, values):
        ax.text(b.get_x() + b.get_width() / 2, v + top * 0.01, fmt.format(v), ha="center", va="bottom",
                fontsize=8, color=INK2)


def energy_unit(values_wan_kwh):
    """Pick 亿kWh when monthly totals are large, else 万kWh."""
    return (1e4, "亿kWh", "{:.2f}") if np.nanmax(values_wan_kwh) >= 1e4 else (1, "万kWh", "{:.0f}")


# ---------------------------------------------------------------- chapter 3: load
@figure("3.2-1", "全年逐日负荷曲线")
def load_daily(c, ax_new):
    d = c.df.groupby("day").agg(dmax=("load", "max"), dmean=("load", "mean"))
    fig, ax = ax_new(3.2)
    if (d.dmax - d.dmean).abs().max() < 1e-6:     # load constant within each day: one line is enough
        ax.plot(d.index, d.dmean, color=BLUE, linewidth=1.6, label="日负荷")
    else:
        ax.plot(d.index, d.dmax, color=BLUE, linewidth=1.2, label="日最大负荷")
        ax.plot(d.index, d.dmean, color=ORANGE, linewidth=1.2, label="日平均负荷")
    ax.axhline(c.rated, color=INK2, linewidth=0.9, linestyle="--", label=f"额定功率（{c.rated:g}万kW）")
    month_axis_days(ax, c.year)
    ax.set_ylim(0, nice_top(max(d.dmax.max(), c.rated), 1.25))
    ax.legend(frameon=False, loc="upper left", fontsize=8.5, ncol=3)
    style(ax, f"{c.load_name}（万kW）")
    return fig, d.rename(columns={"dmax": "日最大负荷（万kW）", "dmean": "日平均负荷（万kW）"})


@figure("3.2-2", "年内月平均负荷")
def load_monthly(c, ax_new):
    m = c.df.groupby("month")["load"].mean()
    fig, ax = ax_new(3.0)
    top = nice_top(m.max())
    bars = ax.bar(m.index, m.values, width=0.62, color=BLUE, edgecolor=SURFACE, linewidth=1.5)
    bar_labels(ax, bars, m.values, "{:.2f}", top)
    ax.set_xticks(range(1, 13), MONTHS)
    ax.set_ylim(0, top)
    style(ax, "月平均负荷（万kW）")
    return fig, m.rename("月平均负荷（万kW）").to_frame()


@figure("3.2-3", "年内日平均负荷")
def load_hourly_avg(c, ax_new):
    hp = c.df.groupby("hour")[["load", "re"]].mean()
    fig, ax = ax_new(3.0)
    ax.plot(hp.index, hp["re"], color=ORANGE, linewidth=2, marker="o", markersize=4, label=c.re_name)
    ax.plot(hp.index, hp["load"], color=BLUE, linewidth=2, marker="o", markersize=4, label=c.load_name)
    hour_axis(ax)
    ax.set_ylim(0, nice_top(hp.values.max(), 1.3))
    ax.legend(frameon=False, loc="upper left", fontsize=9, ncol=2)
    style(ax, "平均功率（万kW）")
    return fig, hp.rename(columns={"load": f"{c.load_name}（万kW）", "re": f"{c.re_name}（万kW）"})


@figure("3.2-4", "典型日负荷曲线")
def load_typical(c, ax_new):
    fig, ax = ax_new(3.0)
    out = {}
    for key, color in (("summer_clear", BLUE), ("winter_clear", ORANGE)):
        sub = c.df[c.df.day == c.days[key]]
        label = f"{c.day_name(key)}（{c.day_label(key)}）"
        ax.plot(sub["hour"], sub["load"], color=color, linewidth=2, marker="o", markersize=4, label=label)
        out[label] = sub["load"].values
    ax.axhline(c.rated, color=MUTED, linewidth=0.8, linestyle="--")
    ax.text(23.3, c.rated * 1.015, f"额定功率 {c.rated:g}", fontsize=8, color=INK2, va="bottom", ha="right")
    hour_axis(ax)
    ax.set_ylim(0, nice_top(max(c.pmax, c.rated), 1.3))
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    style(ax, f"{c.load_name}（万kW）")
    return fig, pd.DataFrame(out, index=pd.Index(range(24), name="时刻"))


@figure("3.3-1", "负荷率区间分布")
def load_rate(c, ax_new):
    rate = c.df["load"] / c.rated
    edges = c.p.get("load_rate_edges")
    if not edges:
        # start at the lower of the minimum ratio and the lowest running rate, rounded down to 5 %
        run = rate[rate > 0]
        lo = math.floor(min(float(c.p.get("load_min_ratio", 0.2)), run.min()) * 20 + 1e-9) / 20
        hi = max(float(c.p.get("load_max_ratio", 1.0)), 1.0)
        edges = [lo] + [x for x in (0.4, 0.6, 0.8, 1.0) if lo + 0.049 < x < hi] + [hi]
    bands = []
    if (c.df["load"] == 0).any():
        bands.append(("停机", c.df["load"] == 0))
    for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
        lo = (rate > 0) if i == 0 else (rate >= a - 1e-6)
        hi = (rate <= b + 1e-6) if i == len(edges) - 2 else (rate < b - 1e-6)
        bands.append((f"{a * 100:g}%～{b * 100:g}%", (c.df["load"] > 0) & lo & hi))
    hours = [int(m.sum()) for _, m in bands]
    fig, ax = ax_new(3.0)
    top = nice_top(max(hours))
    bars = ax.bar([b for b, _ in bands], hours, width=0.6, color=BLUE, edgecolor=SURFACE, linewidth=1.5)
    bar_labels(ax, bars, hours, "{}", top)
    ax.set_ylim(0, top)
    style(ax, "小时数（h）")
    ax.set_xlabel("负荷率区间", color=INK2)
    return fig, pd.DataFrame({"小时数（h）": hours}, index=pd.Index([b for b, _ in bands], name="负荷率区间"))


# ---------------------------------------------------------------- chapter 4.1: output
@figure("4.1-2", "{src}各月发电量")
def gen_monthly(c, ax_new):
    mon = c.df.groupby("month")[[s for s, _, _ in c.sources]].sum()
    div, unit, fmt = energy_unit(mon.sum(axis=1).values)
    mon = mon / div
    fig, ax = ax_new(3.0)
    top = nice_top(mon.sum(axis=1).max())
    bottom = np.zeros(12)
    for col, name, color in c.sources:
        ax.bar(mon.index, mon[col], width=0.62, bottom=bottom, color=color if len(c.sources) > 1 else BLUE,
               edgecolor=SURFACE, linewidth=1.5, label=name)
        bottom += mon[col].values
    bar_labels(ax, ax.patches[-12:], bottom, fmt, top)
    if len(c.sources) > 1:
        ax.legend(frameon=False, loc="upper left", fontsize=9, ncol=2)
    ax.set_xticks(range(1, 13), MONTHS)
    ax.set_ylim(0, top)
    style(ax, f"月发电量（{unit}）")
    return fig, mon.rename(columns={s: f"{n}（{unit}）" for s, n, _ in c.sources})


@figure("4.1-3", "{src}全年逐日发电量")
def gen_daily(c, ax_new):
    daily = c.df.groupby("day")["re"].sum()
    roll = daily.rolling(15, center=True, min_periods=1).mean()
    fig, ax = ax_new(3.0)
    ax.plot(daily.index, daily.values, color=BLUE, linewidth=1, label="日发电量")
    ax.plot(roll.index, roll.values, color=ORANGE, linewidth=2, label="15日滑动平均")
    month_axis_days(ax, c.year)
    ax.set_ylim(0, nice_top(daily.max()))
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    style(ax, "日发电量（万kWh）")
    return fig, pd.DataFrame({"日发电量（万kWh）": daily, "15日滑动平均（万kWh）": roll})


@figure("4.1-4", "{src}年内日平均出力")
def gen_hourly_avg(c, ax_new):
    cols = [s for s, _, _ in c.sources] + (["re"] if len(c.sources) > 1 else [])
    hp = c.df.groupby("hour")[cols].mean()
    fig, ax = ax_new(3.0)
    if len(c.sources) == 1:
        s = hp[cols[0]]
        ax.plot(hp.index, s, color=BLUE, linewidth=2, marker="o", markersize=4)
        ax.fill_between(hp.index, s, color=BLUE, alpha=0.08)
        ax.annotate(f"峰值 {s.max():.1f}", (int(s.idxmax()), s.max()), textcoords="offset points", xytext=(8, 4),
                    fontsize=8, color=INK2)
    else:
        for col, name, color in c.sources:
            ax.plot(hp.index, hp[col], color=color, linewidth=2, label=name)
        ax.plot(hp.index, hp["re"], color=BLUE, linewidth=2, label="合计")
        ax.legend(frameon=False, loc="upper left", fontsize=9, ncol=3)
    hour_axis(ax)
    ax.set_ylim(0, nice_top(hp.values.max()))
    style(ax, "平均出力（万kW）")
    return fig, hp.rename(columns={"pv": "光伏（万kW）", "wind": "风电（万kW）", "re": "合计（万kW）"})


@figure("4.1-5", "{src}各月日内平均出力")
def gen_month_profiles(c, ax_new):
    prof = c.df.groupby(["month", "hour"])[[s for s, _, _ in c.sources]].mean()
    top = nice_top(prof.values.max(), 1.08)
    fig, axes = plt.subplots(3, 4, figsize=(WIDTH, 5.0), sharex=True, sharey=True)
    for m, ax in zip(range(1, 13), axes.flat):
        for col, name, color in c.sources:
            y = prof.loc[m][col]
            k = color if len(c.sources) > 1 else BLUE
            ax.plot(y.index, y.values, color=k, linewidth=1.6, label=name)
            ax.fill_between(y.index, y.values, color=k, alpha=0.08)
        ax.set_title(f"{m}月", fontsize=9, color=INK2, pad=2)
        ax.set_xticks([6, 12, 18], ["6", "12", "18"])
        ax.tick_params(labelsize=7.5, length=0)
        ax.set_xlim(0, 23)
        ax.set_ylim(0, top)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.grid(axis="x", visible=False)
    if len(c.sources) > 1:
        h, lab = axes.flat[0].get_legend_handles_labels()
        fig.legend(h, lab, frameon=False, fontsize=8, loc="upper center", ncol=len(lab))
    fig.supxlabel("时刻（h）", fontsize=9, color=INK2)
    fig.supylabel("平均出力（万kW）", fontsize=9, color=INK2)
    if len(c.sources) > 1:
        fig.tight_layout(rect=(0, 0, 1, 0.95))
        fig.laid_out = True
    return fig, prof.unstack(0)


@figure("4.1-6", "代表月日内平均出力")
def gen_rep_months(c, ax_new):
    fig, ax = ax_new(3.2)
    out = {}
    for m, color in ((1, BLUE), (4, ORANGE), (7, AQUA), (10, YELLOW)):
        prof = c.df[c.df.month == m].groupby("hour")["re"].mean()
        ax.plot(prof.index, prof.values, color=color, linewidth=2, label=f"{m}月")
        out[f"{m}月（万kW）"] = prof.values
    top = nice_top(max(v.max() for v in out.values()))
    hour_axis(ax)
    ax.set_ylim(0, top)
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    style(ax, "平均出力（万kW）")
    return fig, pd.DataFrame(out, index=pd.Index(range(24), name="时刻"))


@figure("4.1-7", "{src}典型日出力")
def gen_typical(c, ax_new):
    fig, ax = ax_new(3.2)
    out = {}
    for key, color in (("summer_clear", BLUE), ("winter_clear", ORANGE), ("summer_cloudy", AQUA)):
        sub = c.df[c.df.day == c.days[key]]
        label = f"{c.day_name(key)}（{c.day_label(key)}）"
        ax.plot(sub["hour"], sub["re"], color=color, linewidth=2, marker="o", markersize=3.5, label=label)
        out[label] = sub["re"].values
    hour_axis(ax)
    ax.set_ylim(0, nice_top(max(v.max() for v in out.values()), 1.2))
    ax.legend(frameon=False, loc="upper left", fontsize=9)
    style(ax, f"{c.re_name}（万kW）")
    return fig, pd.DataFrame(out, index=pd.Index(range(24), name="时刻"))


@figure("4.1-8", "{src}出力频率分布")
def gen_frequency(c, ax_new):
    edges = np.arange(0, 1.01, 0.1)
    labels = [f"{int(a * 100)}~{int(b * 100)}%" for a, b in zip(edges[:-1], edges[1:])]
    table = {}
    for col, name, _ in c.sources:
        cap = c.caps[col]
        # PV counts generation hours only; wind counts every hour
        s = c.df.loc[c.df[col] > 0, col] if col == "pv" else c.df[col]
        cnt, _ = np.histogram((s / cap).clip(0, 0.9999), bins=edges)
        table[f"{name}（%）"] = cnt / cnt.sum() * 100
    t = pd.DataFrame(table, index=pd.Index(labels, name="出力占装机比例"))
    fig, ax = ax_new(3.0)
    top = nice_top(t.values.max())
    w = 0.62 / len(t.columns)
    for j, ((col, name, color), key) in enumerate(zip(c.sources, t.columns)):
        x = np.arange(len(labels)) + (j - (len(t.columns) - 1) / 2) * w
        bars = ax.bar(x, t[key], width=w, color=color if len(c.sources) > 1 else BLUE, edgecolor=SURFACE,
                      linewidth=1.2, label=name)
        if len(c.sources) == 1:
            bar_labels(ax, bars, t[key], "{:.1f}%", top)
    ax.set_xticks(range(len(labels)), labels)
    if len(c.sources) > 1:
        ax.legend(frameon=False, fontsize=9)
    ax.set_ylim(0, top)
    ax.tick_params(axis="x", labelsize=8)
    style(ax, "出现频率（%）")
    note = ("（光伏按直流侧容量、有出力时段统计）" if c.p.get("pv_rate_base") else "（光伏按有出力时段统计）") if c.has_pv else ""
    ax.set_xlabel("出力占装机容量比例" + note, color=INK2)
    return fig, t


@figure("4.1-9", "{src}年出力持续曲线")
def gen_duration(c, ax_new):
    fig, ax = ax_new(3.0)
    out = {}
    for col, name, color in c.sources:
        s = np.sort(c.df[col].values)[::-1] / c.caps[col] * 100
        k = color if len(c.sources) > 1 else BLUE
        ax.plot(np.arange(1, len(s) + 1), s, color=k, linewidth=2, label=name)
        out[f"{name}（%）"] = s
        if len(c.sources) == 1:
            for level in (80, 50, 30):
                h = int((s >= level).sum())
                ax.plot([h], [level], marker="o", markersize=5, color=k)
                ax.text(h + 120, level + 2, f"≥{level}%：{h} h", fontsize=8, color=INK2)
    if len(c.sources) > 1:
        ax.legend(frameon=False, fontsize=9)
    ax.set_xlim(0, 8760)
    ax.set_ylim(0, 100)
    style(ax, "出力占装机容量（%）", xgrid=True)
    ax.set_xlabel("累计小时数（h）", color=INK2)
    return fig, pd.DataFrame(out, index=pd.Index(range(1, 8761), name="累计小时"))


# ---------------------------------------------------------------- chapter 4.2: operation
@figure("4.2-1", "全年8760h生产模拟运行情况")
def op_year(c, ax_new):
    fig, ax = ax_new(3.2)
    x = np.arange(len(c.df))
    ax.plot(x, c.df["re"], color=ORANGE, linewidth=0.35, label=c.re_name)
    ax.plot(x, c.df["load"], color=BLUE, linewidth=1.0, label=c.load_name, zorder=3)
    if c.pmax > c.rated + 1e-9:
        ax.axhline(c.pmax, color=INK2, linewidth=0.9, linestyle="--", label=f"最大运行功率（{c.pmax:.2f}万kW）")
    ax.set_xticks([(pd.Timestamp(c.year, m, 1).dayofyear - 1) * 24 for m in range(1, 13)], MONTHS)
    ax.set_xlim(0, 8760)
    ax.set_ylim(0, nice_top(max(c.df["re"].max(), c.pmax), 1.3))
    leg = ax.legend(frameon=False, loc="upper left", fontsize=8.5, ncol=3)
    for line in leg.get_lines():
        line.set_linewidth(2)
    style(ax, "功率（万kW）")
    return fig, c.df.set_index("time")[["re", "load", "grid"]].rename(
        columns={"re": f"{c.re_name}（万kW）", "load": f"{c.load_name}（万kW）", "grid": "外购电（万kW）"})


@figure("4.2-2", "月度电量平衡")
def op_monthly(c, ax_new):
    g = c.df.groupby("month")
    discharge = g["bat"].apply(lambda v: -v[v < 0].sum())
    charge = g["bat"].apply(lambda v: v[v > 0].sum())
    grid = g["grid"].sum()
    direct = g["load"].sum() - discharge - grid     # renewable energy straight to the load
    curt = g["curt"].sum()
    div, unit, _ = energy_unit((direct + charge + curt).values)
    t = pd.DataFrame({"新能源直供负荷": direct, "储能充电": charge, "弃电": curt,
                      "储能放电": discharge, "外购电": grid}) / div
    xm = np.arange(1, 13)
    panels = [("新能源电量去向", [("新能源直供负荷", BLUE), ("储能充电", ORANGE), ("弃电", AQUA)])]
    if c.has_grid:
        panels.append((f"{c.load_name}电量来源", [("新能源直供负荷", BLUE), ("储能放电", YELLOW), ("外购电", PURPLE)]))
    fig, axes = plt.subplots(1, len(panels), figsize=(WIDTH, 3.2), sharey=True, squeeze=False)
    top = nice_top(max(t[[k for k, _ in s]].sum(axis=1).max() for _, s in panels), 1.2)
    legend = {}
    for ax, (title, stack) in zip(axes[0], panels):
        bottom = np.zeros(12)
        for key, color in stack:
            legend[key] = ax.bar(xm, t[key], width=0.62, bottom=bottom, color=color, edgecolor=SURFACE,
                                 linewidth=1.2, label=key)
            bottom += t[key].values
        ax.set_xticks(xm, MONTHS if len(panels) == 1 else [str(m) for m in xm])
        ax.set_ylim(0, top)
        if len(panels) > 1:
            ax.set_title(title, fontsize=9, color=INK2)
            ax.set_xlabel("月份", fontsize=8, color=INK2)
        style(ax, f"电量（{unit}）" if ax is axes[0][0] else "")
    if len(panels) == 1:
        axes[0][0].legend(frameon=False, loc="upper left", fontsize=9, ncol=3)
    else:
        fig.legend(legend.values(), legend.keys(), frameon=False, loc="lower center", ncol=len(legend), fontsize=8)
        fig.tight_layout(rect=(0, 0.07, 1, 1))
        fig.laid_out = True
    return fig, t.rename(columns=lambda k: f"{k}（{unit}）")


@figure("4.2-3", "日平均系统运行")
def op_hourly_avg(c, ax_new):
    hp = c.df.groupby("hour")[["re", "load", "bat", "grid"]].mean()
    fig, ax = ax_new(3.2)
    ax.bar(hp.index, hp["bat"], width=0.6, color=AQUA, edgecolor=SURFACE, linewidth=1, label="储能充放电（充为正）")
    ax.plot(hp.index, hp["re"], color=ORANGE, linewidth=2, label=c.re_name)
    ax.plot(hp.index, hp["load"], color=BLUE, linewidth=2, label=c.load_name)
    if c.has_grid:
        ax.plot(hp.index, hp["grid"], color=PURPLE, linewidth=2, label="外购电")
    ax.axhline(0, color=AXIS, linewidth=0.8)
    hour_axis(ax)
    top = nice_top(hp[["re", "load"]].values.max(), 1.3)
    ax.set_ylim(min(0, nice_top(-hp["bat"].min(), 1.3) * -1), top)
    ax.legend(frameon=False, loc="upper left", fontsize=8.5, ncol=2)
    style(ax, "平均功率（万kW）")
    return fig, hp.rename(columns={"re": f"{c.re_name}（万kW）", "load": f"{c.load_name}（万kW）",
                                   "bat": "储能（充为正，万kW）", "grid": "外购电（万kW）"})


@figure("4.2-4", "典型日系统运行")
def op_typical(c, ax_new):
    fig, axes = plt.subplots(1, 2, figsize=(WIDTH, 3.2), sharey=True)
    frames = []
    lo, hi = 0, 0
    for ax, key in zip(axes, c.p.get("op_typical_days", ("summer_clear", "winter_clear"))):
        sub = c.df[c.df.day == c.days[key]].set_index("hour")
        bars = [("bat", AQUA, "储能充放电（充为正）"), ("curt", YELLOW, "弃电")]
        if c.has_grid:
            bars.append(("grid", PURPLE, "外购电"))
        w = 0.8 / len(bars)
        for j, (col, color, label) in enumerate(bars):
            ax.bar(sub.index + (j - (len(bars) - 1) / 2) * w, sub[col], width=w, color=color, label=label)
        ax.plot(sub.index, sub["re"], color=ORANGE, linewidth=2, label=c.re_name)
        ax.plot(sub.index, sub["load"], color=BLUE, linewidth=2, label=c.load_name)
        ax.axhline(0, color=AXIS, linewidth=0.8)
        ax.set_xticks(range(0, 24, 4), [f"{h}:00" for h in range(0, 24, 4)])
        ax.tick_params(axis="x", labelsize=8)
        ax.set_xlim(-0.5, 23.5)
        title = f"{c.day_name(key)}（{c.day_label(key)}）"
        ax.set_title(title, fontsize=9, color=INK2)
        style(ax, "功率（万kW）" if ax is axes[0] else "")
        lo = min(lo, sub["bat"].min())
        hi = max(hi, sub[["re", "load"]].values.max())
        f = sub[["re", "load", "bat", "curt", "grid"]].copy()
        f.columns = [f"{title}{k}" for k in (c.re_name, c.load_name, "储能", "弃电", "外购电")]
        frames.append(f)
    axes[0].set_ylim(-nice_top(-lo, 1.3) if lo < 0 else 0, nice_top(hi))
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, loc="lower center", ncol=len(labels), fontsize=8)
    fig.tight_layout(rect=(0, 0.08, 1, 1))
    fig.laid_out = True
    return fig, pd.concat(frames, axis=1)


# ---------------------------------------------------------------- chapter 4.3: scale comparison
def default_panels(schemes):
    options = [("util", "新能源利用率（%）", 100, "{:.1f}"), ("gen_share", "自发自用电量占发电量（%）", 100, "{:.1f}"),
               ("load_share", "自发自用电量占用电量（%）", 100, "{:.1f}"), ("price", "反推供电价格（元/kWh）", 1, "{:.4f}")]
    return [dict(col=k, title=t, scale=s, fmt=f) for k, t, s, f in options if k in schemes][:3]


@figure("4.3-1", "{src}装机规模比选")
def scale_compare(c, ax_new):
    if c.schemes is None or "recommended" not in c.p.get("schemes", {}):
        return None
    cfg = c.p.get("schemes", {})
    rec = cfg["recommended"]
    xcol = cfg.get("scale_col", "pv")
    s = c.schemes[(c.schemes.bess_ratio.round(4) == round(rec["bess_ratio"], 4)) &
                  (c.schemes.bess_hours == rec["bess_hours"])].sort_values(xcol)
    for k in ("pv", "wind"):
        if k in rec and k != xcol and k in s:
            s = s[s[k] == rec[k]]
    panels = cfg.get("scale_panels") or default_panels(s)
    fig, axes = plt.subplots(1, len(panels), figsize=(WIDTH, 2.6), squeeze=False)
    x = s[xcol].values
    for k, (ax, pnl) in enumerate(zip(axes[0], panels)):
        y = s[pnl["col"]].astype(float).values * pnl.get("scale", 1)
        ax.plot(x, y, color=BLUE, linewidth=2, marker="o", markersize=4)
        hit = np.where(np.isclose(x, rec[xcol]))[0]
        if hit.size:
            i = hit[0]
            ax.plot([x[i]], [y[i]], marker="o", markersize=8, color=ORANGE, zorder=3)
            offset, ha = ((6, 6), "left") if k == 0 else ((-6, 6), "right")
            ax.annotate(pnl.get("fmt", "{:.2f}").format(y[i]), (x[i], y[i]), textcoords="offset points",
                        xytext=offset, ha=ha, fontsize=8, color=INK2)
        if "ref" in pnl:
            ax.axhline(pnl["ref"], color=MUTED, linewidth=0.8, linestyle="--")
            ax.text(x.max(), pnl["ref"], pnl.get("ref_label", ""), fontsize=7.5, color=INK2, ha="right", va="top")
        ax.set_xlabel(cfg.get("scale_label", "光伏交流侧装机（万kW）"), fontsize=8)
        ax.set_title(pnl["title"], fontsize=9, color=INK2)
        style(ax)
    cols = [xcol] + [p["col"] for p in panels]
    return fig, s[cols].set_index(xcol)


@figure("4.3-2", "储能配置比选")
def storage_compare(c, ax_new):
    if c.schemes is None or "recommended" not in c.p.get("schemes", {}):
        return None
    cfg = c.p.get("schemes", {})
    rec = cfg["recommended"]
    xcol = cfg.get("scale_col", "pv")
    st = c.schemes[np.isclose(c.schemes[xcol], rec[xcol])]
    for k in ("pv", "wind"):
        if k in rec and k != xcol and k in st:
            st = st[np.isclose(st[k], rec[k])]
    ratios = sorted(st.bess_ratio.round(4).unique())
    hours = sorted(st.bess_hours.unique())
    panels = cfg.get("storage_panels") or [p for p in default_panels(st) if p["col"] in ("price", "util")][:2] \
        or default_panels(st)[:2]
    colors = [BLUE, ORANGE, AQUA, YELLOW, PURPLE]
    w = 0.8 / len(hours)
    fig, axes = plt.subplots(1, len(panels), figsize=(WIDTH, 2.8), squeeze=False)
    for ax, pnl in zip(axes[0], panels):
        vals = []
        for j, h in enumerate(hours):
            sub = st[st.bess_hours == h].assign(r=lambda t: t.bess_ratio.round(4)).set_index("r").reindex(ratios)
            y = sub[pnl["col"]].astype(float) * pnl.get("scale", 1)
            vals.extend(y.dropna().tolist())
            ax.bar(np.arange(len(ratios)) + (j - (len(hours) - 1) / 2) * w, y, width=w, color=colors[j % 5],
                   edgecolor=SURFACE, linewidth=1, label=f"{h:g} h")
        ri, hj = ratios.index(round(rec["bess_ratio"], 4)), hours.index(rec["bess_hours"])
        yr = st[(st.bess_ratio.round(4) == ratios[ri]) & (st.bess_hours == hours[hj])][pnl["col"]].iloc[0]
        yr *= pnl.get("scale", 1)
        ax.annotate("推荐", (ri + (hj - (len(hours) - 1) / 2) * w, yr), textcoords="offset points", xytext=(0, 4),
                    ha="center", fontsize=7.5, color=INK2)
        span = max(vals) - min(vals) or abs(max(vals)) * 0.1 or 1
        ax.set_ylim(pnl.get("ylim", (min(vals) - span * 0.6, max(vals) + span * 0.6)))
        ax.set_xticks(range(len(ratios)), [f"{r * 100:g}%" for r in ratios])
        ax.set_xlabel("储能功率配比", fontsize=8)
        ax.set_title(pnl["title"], fontsize=9, color=INK2)
        style(ax)
    axes[0][0].legend(frameon=False, fontsize=8, loc="upper left", ncol=len(hours))
    cols = ["bess_ratio", "bess_hours"] + [p["col"] for p in panels]
    return fig, st[cols].set_index(["bess_ratio", "bess_hours"])


# ---------------------------------------------------------------- driver
def load_hourly(path):
    df = pd.read_csv(path, parse_dates=["time"], encoding="utf-8-sig")
    if len(df) != 8760:
        sys.exit(f"{path} 应为 8760 行，实际 {len(df)} 行")
    for col in ("pv", "wind", "load", "bat", "curt", "grid"):
        if col not in df:
            df[col] = 0.0
    df["month"], df["day"], df["hour"] = df["time"].dt.month, df["time"].dt.dayofyear, df["time"].dt.hour
    return df


def main():
    ap = argparse.ArgumentParser(description="生成绿电直连申报方案第三、四章数据插图")
    ap.add_argument("--hourly", type=Path, required=True)
    ap.add_argument("--params", type=Path, required=True)
    ap.add_argument("--schemes", type=Path, help="规模比选方案 CSV")
    ap.add_argument("--out", type=Path, default=Path("2-figures"))
    ap.add_argument("--data-xlsx", type=Path, help="导出每张图的数据")
    ap.add_argument("--only", help="只生成指定默认图号，逗号分隔")
    args = ap.parse_args()

    p = json.loads(args.params.read_text(encoding="utf-8"))
    schemes = pd.read_csv(args.schemes, encoding="utf-8-sig") if args.schemes else None
    c = Ctx(load_hourly(args.hourly), p, schemes, args.out)
    args.out.mkdir(parents=True, exist_ok=True)
    wanted = set(args.only.split(",")) if args.only else None
    overrides = p.get("figures", {})

    def ax_new(height):
        return plt.subplots(figsize=(WIDTH, height))

    for no, (title, fn) in REGISTRY.items():
        if wanted and no not in wanted:
            continue
        ov = overrides.get(no, {})
        if ov is False:
            continue
        no_out = ov.get("no", no)
        title_out = ov.get("title", title.format(src=c.src))
        with plt.rc_context({"font.size": 9} if no.startswith("4.3") else {}):
            result = fn(c, ax_new)
            if result is None:
                print(f"skip 图{no}（需要 --schemes 及 params.json 的 schemes.recommended）")
                continue
            fig, data = result
            name = f"图{no_out}_{title_out}.png"
            if not getattr(fig, "laid_out", False):
                fig.tight_layout()
            fig.savefig(args.out / name)
            plt.close(fig)
        c.data[f"图{no_out}"] = data
        print("saved", name)

    print("典型日：", {k: c.day_label(k) for k in c.days})
    if args.data_xlsx:
        args.data_xlsx.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(args.data_xlsx) as xw:
            for sheet, data in c.data.items():
                data.to_excel(xw, sheet_name=sheet[:31])
        print("saved", args.data_xlsx)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
