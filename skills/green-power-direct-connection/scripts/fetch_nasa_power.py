"""Download the NASA POWER 20-year monthly climatology for a site (resource / climate chapter data).

Usage:
    python fetch_nasa_power.py --lat 44.0 --lon 87.9 --out 0-inputs/NASA_POWER_气候统计_87.9E_44.0N.json

Parameters fetched: GHI, diffuse, DNI, 2 m temperature (mean / max / min), corrected precipitation,
2 m relative humidity and 10 m wind speed. Daily-mean values; make_context_figures.py converts
them to monthly totals.
"""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://power.larc.nasa.gov/api/temporal/climatology/point"
PARAMETERS = ["ALLSKY_SFC_SW_DWN", "ALLSKY_SFC_SW_DIFF", "ALLSKY_SFC_SW_DNI", "T2M", "T2M_MAX", "T2M_MIN",
              "PRECTOTCORR", "RH2M", "WS10M"]


def main():
    ap = argparse.ArgumentParser(description="下载 NASA POWER 场址多年月气候统计")
    ap.add_argument("--lat", type=float, required=True, help="纬度（十进制度）")
    ap.add_argument("--lon", type=float, required=True, help="经度（十进制度）")
    ap.add_argument("--start", type=int, default=2001)
    ap.add_argument("--end", type=int, default=2020)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    query = urllib.parse.urlencode({"parameters": ",".join(PARAMETERS), "community": "RE", "latitude": args.lat,
                                    "longitude": args.lon, "start": args.start, "end": args.end, "format": "JSON"})
    with urllib.request.urlopen(f"{API}?{query}", timeout=120) as resp:
        data = json.load(resp)
    if "properties" not in data:
        sys.exit(f"NASA POWER 返回异常：{json.dumps(data, ensure_ascii=False)[:500]}")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    p = data["properties"]["parameter"]
    print("saved", args.out)
    print(f"年均日 GHI {p['ALLSKY_SFC_SW_DWN']['ANN']:.2f} kWh/m²/d，年 GHI 约 "
          f"{p['ALLSKY_SFC_SW_DWN']['ANN'] * 365:.1f} kWh/m²；年均气温 {p['T2M']['ANN']:.1f} ℃；"
          f"海拔 {data['geometry']['coordinates'][2]:.0f} m")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
