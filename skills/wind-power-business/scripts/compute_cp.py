#!/usr/bin/env python3
"""Calculate wind turbine Cp values from a pasted power curve."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

BETZ_LIMIT = 0.593
MIN_AIR_DENSITY = 0.5
MAX_AIR_DENSITY = 1.5
MIN_ROTOR_DIAMETER_M = 30.0
MAX_ROTOR_DIAMETER_M = 350.0
MODEL_DIAMETER_TOLERANCE_RATIO = 0.10
MODEL_DIAMETER_TOLERANCE_MIN_M = 10.0
NUMBER_RE = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")
MODEL_DIAMETER_RE = re.compile(r"\b[A-Za-z]+\d{3,6}[-_](\d{2,3})\b")


@dataclass
class CurvePoint:
    wind_speed_ms: float
    power_kw: float
    ct: float | None
    theoretical_power_kw: float
    cp: float


@dataclass
class Summary:
    rho: float
    diameter_m: float
    swept_area_m2: float
    row_count: int
    cp_max: float
    cp_max_wind_speed_ms: float
    cp_max_power_kw: float
    cp_max_theoretical_power_kw: float
    cp_max_ct: float | None
    betz_limit: float
    cp_above_betz_count: int


class UnphysicalCpError(ValueError):
    """Raised when calculated Cp values are physically impossible."""


class ParameterValidationError(ValueError):
    """Raised when required calculation parameters are outside expected bounds."""


def parse_number(raw: str) -> float:
    return float(raw.replace(",", ""))


def read_input(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8-sig")


def infer_diameter_from_model(text: str) -> float | None:
    for line in text.splitlines():
        if "机型" not in line and "model" not in line.lower():
            continue
        match = MODEL_DIAMETER_RE.search(line)
        if match:
            return float(match.group(1))
    match = MODEL_DIAMETER_RE.search(text)
    if match:
        return float(match.group(1))
    return None


def validate_input_parameters(
    source_text: str,
    rho: float,
    diameter_m: float,
    allow_suspicious_parameters: bool = False,
) -> None:
    if allow_suspicious_parameters:
        return

    if not MIN_AIR_DENSITY <= rho <= MAX_AIR_DENSITY:
        raise ParameterValidationError(
            f"Air density rho={rho:g} kg/m^3 is outside the broad sanity-check range "
            f"{MIN_AIR_DENSITY:g}-{MAX_AIR_DENSITY:g} kg/m^3. Ask the user to confirm rho before calculating."
        )

    if not MIN_ROTOR_DIAMETER_M <= diameter_m <= MAX_ROTOR_DIAMETER_M:
        raise ParameterValidationError(
            f"Rotor diameter D={diameter_m:g} m is outside the broad sanity-check range "
            f"{MIN_ROTOR_DIAMETER_M:g}-{MAX_ROTOR_DIAMETER_M:g} m. Ask the user to confirm D before calculating."
        )

    inferred_diameter = infer_diameter_from_model(source_text)
    if inferred_diameter is None:
        return

    tolerance = max(MODEL_DIAMETER_TOLERANCE_MIN_M, inferred_diameter * MODEL_DIAMETER_TOLERANCE_RATIO)
    if abs(diameter_m - inferred_diameter) > tolerance:
        raise ParameterValidationError(
            f"Rotor diameter D={diameter_m:g} m appears inconsistent with model-name hint D~{inferred_diameter:g} m. "
            f"Ask the user to confirm D before calculating, or rerun with --allow-suspicious-parameters after confirmation."
        )


def parse_curve(text: str) -> list[tuple[float, float, float | None]]:
    rows: list[tuple[float, float, float | None]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or not re.match(r"^[-+]?\d", stripped):
            continue

        matches = NUMBER_RE.findall(stripped)
        if len(matches) < 2:
            continue

        wind_speed = parse_number(matches[0])
        power = parse_number(matches[1])
        ct = parse_number(matches[2]) if len(matches) >= 3 else None
        rows.append((wind_speed, power, ct))

    if not rows:
        raise ValueError("No valid power-curve rows found. Need at least wind speed and power columns.")
    return rows


def calculate(rows: Iterable[tuple[float, float, float | None]], rho: float, diameter_m: float) -> tuple[list[CurvePoint], Summary]:
    if rho <= 0:
        raise ValueError("Air density must be positive.")
    if diameter_m <= 0:
        raise ValueError("Rotor diameter must be positive.")

    swept_area = math.pi * diameter_m**2 / 4
    points: list[CurvePoint] = []

    for wind_speed, power, ct in rows:
        if wind_speed <= 0:
            continue
        theoretical_power = 0.5 * rho * wind_speed**3 * swept_area / 1000
        if theoretical_power <= 0:
            continue
        cp = power / theoretical_power
        points.append(
            CurvePoint(
                wind_speed_ms=wind_speed,
                power_kw=power,
                ct=ct,
                theoretical_power_kw=theoretical_power,
                cp=cp,
            )
        )

    if not points:
        raise ValueError("No calculable rows found after filtering invalid wind speeds.")

    max_point = max(points, key=lambda item: item.cp)
    summary = Summary(
        rho=rho,
        diameter_m=diameter_m,
        swept_area_m2=swept_area,
        row_count=len(points),
        cp_max=max_point.cp,
        cp_max_wind_speed_ms=max_point.wind_speed_ms,
        cp_max_power_kw=max_point.power_kw,
        cp_max_theoretical_power_kw=max_point.theoretical_power_kw,
        cp_max_ct=max_point.ct,
        betz_limit=BETZ_LIMIT,
        cp_above_betz_count=sum(1 for point in points if point.cp > BETZ_LIMIT),
    )
    return points, summary


def validate_physical_result(summary: Summary, source_text: str, allow_unphysical: bool = False) -> None:
    if allow_unphysical or summary.cp_above_betz_count == 0:
        return

    inferred_diameter = infer_diameter_from_model(source_text)
    hints = [
        f"Cp,max={summary.cp_max:.6f} exceeds the Betz limit {BETZ_LIMIT}.",
        f"{summary.cp_above_betz_count} row(s) exceed the Betz limit.",
        "Check rotor diameter D, air density rho, and whether power is in kW.",
    ]
    if inferred_diameter and inferred_diameter != summary.diameter_m:
        hints.append(
            f"The model name in the input suggests rotor diameter may be {inferred_diameter:g} m."
        )
    raise UnphysicalCpError(" ".join(hints))


def format_float(value: float | None, digits: int) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def render_markdown(points: list[CurvePoint], summary: Summary, digits: int) -> str:
    lines = [
        "# Cp 计算结果",
        "",
        "## 参数",
        "",
        f"- 空气密度 rho：`{summary.rho:g} kg/m^3`",
        f"- 叶轮直径 D：`{summary.diameter_m:g} m`",
        f"- 扫掠面积 A：`{summary.swept_area_m2:.3f} m^2`",
        "",
        "## 最终结果",
        "",
        f"- `Cp,max`：`{summary.cp_max:.6f}`",
        f"- 对应风速：`{summary.cp_max_wind_speed_ms:g} m/s`",
        f"- 对应功率：`{summary.cp_max_power_kw:.1f} kW`",
        f"- 对应理论风功率：`{summary.cp_max_theoretical_power_kw:.1f} kW`",
    ]

    if summary.cp_max_ct is not None:
        lines.append(f"- 对应 Ct：`{summary.cp_max_ct:.3f}`")

    if summary.cp_above_betz_count:
        lines.append(f"- 异常提示：有 `{summary.cp_above_betz_count}` 个 Cp 超过贝茨极限 `{summary.betz_limit}`。")
    else:
        lines.append(f"- 异常提示：未发现 Cp 超过贝茨极限 `{summary.betz_limit}`。")

    lines.extend(
        [
            "",
            "## 明细",
            "",
            "| 风速 (m/s) | 功率 (kW) | Ct | 理论风功率 (kW) | Cp |",
            "|---:|---:|---:|---:|---:|",
        ]
    )

    for point in points:
        ct_value = format_float(point.ct, 3)
        lines.append(
            "| "
            f"{point.wind_speed_ms:g} | "
            f"{point.power_kw:.1f} | "
            f"{ct_value} | "
            f"{point.theoretical_power_kw:.1f} | "
            f"{point.cp:.{digits}f} |"
        )

    lines.append("")
    return "\n".join(lines)


def render_csv(points: list[CurvePoint]) -> str:
    from io import StringIO

    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "wind_speed_ms",
            "power_kw",
            "ct",
            "theoretical_power_kw",
            "cp",
        ],
        lineterminator="\n",
    )
    writer.writeheader()
    for point in points:
        writer.writerow(asdict(point))
    return output.getvalue()


def render_json(points: list[CurvePoint], summary: Summary) -> str:
    payload = {
        "summary": asdict(summary),
        "points": [asdict(point) for point in points],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def infer_format(output_path: str | None, explicit_format: str | None) -> str:
    if explicit_format:
        return explicit_format
    if output_path:
        suffix = Path(output_path).suffix.lower()
        if suffix == ".csv":
            return "csv"
        if suffix == ".json":
            return "json"
    return "markdown"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Calculate Cp values from wind-speed, power, and optional Ct columns.",
    )
    parser.add_argument("input", nargs="?", default="-", help="Input text/CSV file. Use '-' or omit for stdin.")
    parser.add_argument("--rho", type=float, required=True, help="Required air density in kg/m^3.")
    parser.add_argument("--diameter", type=float, required=True, help="Required rotor diameter in meters.")
    parser.add_argument("--format", choices=["markdown", "csv", "json"], help="Output format. Defaults to markdown or inferred from --output.")
    parser.add_argument("--output", help="Output file path. Defaults to stdout.")
    parser.add_argument("--digits", type=int, default=6, help="Decimal places for Cp values in markdown output.")
    parser.add_argument(
        "--allow-unphysical",
        action="store_true",
        help="Allow output even when Cp exceeds the Betz limit. Use only for diagnostics.",
    )
    parser.add_argument(
        "--allow-suspicious-parameters",
        action="store_true",
        help="Allow output after the user confirms parameters flagged by broad sanity checks.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        text = read_input(args.input)
        validate_input_parameters(
            text,
            rho=args.rho,
            diameter_m=args.diameter,
            allow_suspicious_parameters=args.allow_suspicious_parameters,
        )
        rows = parse_curve(text)
        points, summary = calculate(rows, rho=args.rho, diameter_m=args.diameter)
        validate_physical_result(summary, text, allow_unphysical=args.allow_unphysical)
    except (OSError, ValueError, UnphysicalCpError) as exc:
        parser.error(str(exc))
        return 2

    output_format = infer_format(args.output, args.format)
    if output_format == "csv":
        rendered = render_csv(points)
    elif output_format == "json":
        rendered = render_json(points, summary)
    else:
        rendered = render_markdown(points, summary, digits=args.digits)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
