"""Assemble a standard 8760 h dataset for a green-power direct-connection project and summarise it.

Output CSV columns (power in 10^4 kW = 万kW, so each hourly value is also energy in 万kWh):
    time   typical-year timestamp (placeholder non-leap year)
    pv     PV output delivered at the project side
    wind   wind output (0 when the project has no wind)
    load   load consumption
    bat    storage power at the load side, positive = charging, negative = discharging
    curt   curtailed renewable energy
    grid   power purchased from the public grid (0 for off-grid projects)

Usage example (calc workbook for load / storage / curtailment, PVsyst CSV for PV):
    python prepare_hourly.py --xlsx calc.xlsm --sheet "财务评价-等本金-25年" --first-row 2 \
        --col load=BR --col bat=BV --col curt=CA --pvsyst pvsyst_hourly.csv \
        --pv-ac 150 --load-rated 75.6 --out work/hourly.csv --summary work/逐时指标摘要.md
"""
import argparse
import csv
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

N = 8760
COLUMNS = ["pv", "wind", "load", "bat", "curt", "grid"]
UNIT_TO_WAN_KW = {"万kW": 1.0, "MW": 0.1, "kW": 1e-4, "W": 1e-7, "GW": 100.0}


def col_index(letters):
    n = 0
    for ch in letters.upper():
        n = n * 26 + ord(ch) - 64
    return n


def read_xlsx_columns(path, sheet, first_row, mapping):
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet]
    idx = {name: col_index(letter) for name, letter in mapping.items()}
    lo, hi = min(idx.values()), max(idx.values())
    out = {name: [] for name in idx}
    for row in ws.iter_rows(min_row=first_row, max_row=first_row + N - 1, min_col=lo, max_col=hi, values_only=True):
        for name, c in idx.items():
            v = row[c - lo]
            out[name].append(float(v) if isinstance(v, (int, float)) else 0.0)
    for name, vals in out.items():
        if len(vals) != N:
            sys.exit(f"{sheet}!{mapping[name]} 只读到 {len(vals)} 行，应为 {N} 行")
    return out


def read_pvsyst(path, column):
    """Read one column of a PVsyst hourly CSV export; returns values in 万kW."""
    lines = path.read_bytes().decode("latin-1").splitlines()
    rows = list(csv.reader(lines))
    head = next(i for i, r in enumerate(rows) if column in [c.strip() for c in r])
    ci = [c.strip() for c in rows[head]].index(column)
    unit = rows[head + 1][ci].strip() if head + 1 < len(rows) else "kW"
    unit = unit.replace("kWh", "kW").replace("MWh", "MW").replace("Wh", "W") or "kW"
    if unit not in UNIT_TO_WAN_KW:
        sys.exit(f"PVsyst 列 {column} 的单位“{unit}”无法识别，请先转换为 kW 或 MW")
    date = re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{2,4} \d{1,2}:\d{2}")
    vals = [float(r[ci] or 0) for r in rows[head + 1:] if r and date.match(r[0])]
    if len(vals) != N:
        sys.exit(f"PVsyst 文件逐时数据 {len(vals)} 行，应为 {N} 行")
    return [max(v, 0.0) * UNIT_TO_WAN_KW[unit] for v in vals]


def build(args):
    data = {c: [0.0] * N for c in COLUMNS}
    if args.xlsx:
        mapping = dict(item.split("=", 1) for item in args.col)
        unknown = set(mapping) - set(COLUMNS)
        if unknown:
            sys.exit(f"--col 只能映射 {COLUMNS}，收到 {sorted(unknown)}")
        scale = UNIT_TO_WAN_KW[args.xlsx_unit]
        for name, vals in read_xlsx_columns(args.xlsx, args.sheet, args.first_row, mapping).items():
            data[name] = [v * scale for v in vals]
    if args.pvsyst:
        data["pv"] = read_pvsyst(args.pvsyst, args.pvsyst_column)
    df = pd.DataFrame(data)
    df["bat"] *= args.bat_sign
    start = datetime(args.year, 1, 1)
    df.insert(0, "time", [start + timedelta(hours=h) for h in range(N)])
    return df


# ---------------------------------------------------------------- summary
def typical_days(df):
    re_out = df["pv"] + df["wind"]
    daily = re_out.groupby(df["time"].dt.dayofyear).sum()
    month = pd.Series([pd.Timestamp(df["time"].iloc[0].year, 1, 1) + timedelta(days=d - 1) for d in daily.index],
                      index=daily.index).dt.month
    jun, dec = daily[month == 6], daily[month == 12]
    return {"summer_clear": int(jun.idxmax()), "winter_clear": int(dec.idxmax()), "summer_cloudy": int(jun.idxmin())}


def fmt_day(year, doy):
    d = datetime(year, 1, 1) + timedelta(days=doy - 1)
    return f"{d.month:02d}-{d.day:02d}"


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(str(x) for x in r) + " |" for r in rows]
    return "\n".join(lines)


def summarise(df, args):
    gen_pv, gen_wind = df["pv"].sum(), df["wind"].sum()
    gen = gen_pv + gen_wind
    load, grid, curt = df["load"].sum(), df["grid"].sum(), df["curt"].sum()
    charge, discharge = df["bat"].clip(lower=0).sum(), -df["bat"].clip(upper=0).sum()
    direct = load - grid                  # renewable energy consumed by the load, incl. storage discharge
    residual = gen + grid + discharge - load - charge - curt
    storage_loss = charge - discharge

    rows = [("新能源年发电量", f"{gen:.1f} 万kWh"), ("其中光伏", f"{gen_pv:.1f} 万kWh"), ("其中风电", f"{gen_wind:.1f} 万kWh")]
    if args.pv_ac:
        rows.append(("光伏利用小时（交流侧）", f"{gen_pv / args.pv_ac:.2f} h"))
    if args.pv_dc:
        rows.append(("光伏利用小时（直流侧）", f"{gen_pv / args.pv_dc:.2f} h"))
    if args.wind_cap:
        rows.append(("风电利用小时", f"{gen_wind / args.wind_cap:.2f} h"))
    rows += [("负荷年用电量", f"{load:.1f} 万kWh"),
             ("新能源供负荷电量（绿电直连电量）", f"{direct:.1f} 万kWh"),
             ("自发自用电量占可用发电量比例", f"{direct / gen:.2%}（要求 ≥ {args.min_gen_share:.0%}）"),
             ("自发自用电量占总用电量比例", f"{direct / load:.2%}（要求 ≥ {args.min_load_share:.0%}）"),
             ("外购电量", f"{grid:.1f} 万kWh"),
             ("弃电量 / 弃电率", f"{curt:.1f} 万kWh / {curt / gen:.2%}"),
             ("新能源利用率（1−弃电率）", f"{1 - curt / gen:.2%}"),
             ("储能年充电 / 放电量", f"{charge:.1f} / {discharge:.1f} 万kWh"),
             ("储能损耗", f"{storage_loss:.1f} 万kWh"),
             ("电量平衡残差（发电+外购+放电−负荷−充电−弃电）", f"{residual:.3f} 万kWh"),
             ("负荷最大 / 平均 / 最小（运行时）", f"{df['load'].max():.2f} / {df['load'].mean():.2f} / "
                                          f"{df.loc[df['load'] > 0, 'load'].min():.2f} 万kW"),
             ("负荷运行小时 / 停机小时", f"{int((df['load'] > 0).sum())} / {int((df['load'] == 0).sum())} h")]
    if args.load_rated:
        rows.append(("负荷等效满负荷小时", f"{load / args.load_rated:.0f} h"))

    m = df.groupby(df["time"].dt.month)
    monthly = []
    for k, g in m:
        monthly.append((k, f"{g['pv'].sum():.1f}", f"{g['wind'].sum():.1f}", f"{g['load'].sum():.1f}",
                        f"{g['bat'].clip(lower=0).sum():.1f}", f"{-g['bat'].clip(upper=0).sum():.1f}",
                        f"{g['curt'].sum():.1f}", f"{g['grid'].sum():.1f}", f"{g['load'].mean():.2f}"))
    hp = df.groupby(df["time"].dt.hour)[["pv", "wind", "load", "bat"]].mean()
    hourly = [(h, f"{r.pv:.2f}", f"{r.wind:.2f}", f"{r.load:.2f}", f"{r.bat:.2f}") for h, r in hp.iterrows()]

    td = typical_days(df)
    year = df["time"].iloc[0].year
    text = [f"# 逐时指标摘要\n\n数据：`{args.out.name}`，功率单位万 kW，电量单位万 kWh。\n",
            "## 年度指标\n", md_table(["指标", "数值"], rows),
            "\n## 逐月电量\n",
            md_table(["月", "光伏", "风电", "负荷用电", "储能充电", "储能放电", "弃电", "外购电", "月均负荷（万kW）"], monthly),
            "\n## 日内平均功率（万 kW）\n", md_table(["时", "光伏", "风电", "负荷", "储能（充为正）"], hourly),
            "\n## 自动选取的典型日\n",
            md_table(["典型日", "日期", "选取规则"],
                     [("夏季晴天", fmt_day(year, td["summer_clear"]), "6 月新能源日发电量最大日"),
                      ("冬季晴天", fmt_day(year, td["winter_clear"]), "12 月新能源日发电量最大日"),
                      ("夏季阴天", fmt_day(year, td["summer_cloudy"]), "6 月新能源日发电量最小日")]),
            "\n可将日期写入 params.json 的 `typical_days`；需要换日时直接改日期。\n"]
    if abs(residual) > 0.01 * gen:
        text.append(f"\n> 电量平衡残差 {residual:.1f} 万kWh 超过发电量的 1%，请核对储能符号（--bat-sign）、"
                    "放电是否已扣效率、弃电列是否包含储能损耗。\n")
    return "\n".join(text)


def main():
    ap = argparse.ArgumentParser(description="生成绿电直连项目 8760 h 标准逐时数据并输出指标摘要")
    ap.add_argument("--xlsx", type=Path, help="测算表（xlsx / xlsm）")
    ap.add_argument("--sheet", help="逐时模拟所在工作表")
    ap.add_argument("--first-row", type=int, default=2, help="第 1 个小时所在行号")
    ap.add_argument("--col", action="append", default=[], help="列映射，如 load=BR，可重复")
    ap.add_argument("--xlsx-unit", choices=list(UNIT_TO_WAN_KW), default="万kW", help="测算表逐时数据单位")
    ap.add_argument("--pvsyst", type=Path, help="PVsyst 逐时 CSV，提供时覆盖 pv 列")
    ap.add_argument("--pvsyst-column", default="E_Grid", help="PVsyst 取用的列名")
    ap.add_argument("--bat-sign", type=float, default=1.0, help="原数据放电为正时传 -1")
    ap.add_argument("--year", type=int, default=2026, help="典型年占位年份（须为平年）")
    ap.add_argument("--pv-ac", type=float, help="光伏交流侧装机（万kW）")
    ap.add_argument("--pv-dc", type=float, help="光伏直流侧装机（万kWp）")
    ap.add_argument("--wind-cap", type=float, help="风电装机（万kW）")
    ap.add_argument("--load-rated", type=float, help="负荷额定功率（万kW）")
    ap.add_argument("--min-gen-share", type=float, default=0.6, help="自发自用电量占发电量下限")
    ap.add_argument("--min-load-share", type=float, default=0.3, help="自发自用电量占用电量下限")
    ap.add_argument("--out", type=Path, required=True, help="输出 hourly.csv")
    ap.add_argument("--summary", type=Path, help="输出指标摘要 Markdown")
    args = ap.parse_args()
    if args.xlsx and not (args.sheet and args.col):
        ap.error("使用 --xlsx 时须同时给出 --sheet 和至少一个 --col")
    if not args.xlsx and not args.pvsyst:
        ap.error("至少提供 --xlsx 或 --pvsyst")

    df = build(args)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(args.out, index=False, encoding="utf-8-sig", float_format="%.6f")
    print("saved", args.out)
    text = summarise(df, args)
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(text, encoding="utf-8")
        print("saved", args.summary)
    else:
        print(text)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
