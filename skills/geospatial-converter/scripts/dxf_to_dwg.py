#!/usr/bin/env python3
"""Convert DXF to DWG with ODA round-trip validation."""

from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DWG_SIGNATURES = {
    "r2000": "AC1015",
    "r2004": "AC1018",
    "r2007": "AC1021",
    "r2010": "AC1024",
    "r2013": "AC1027",
    "r2018": "AC1032",
}

ODA_VERSIONS = {
    "r2000": "ACAD2000",
    "r2004": "ACAD2004",
    "r2007": "ACAD2007",
    "r2010": "ACAD2010",
    "r2013": "ACAD2013",
    "r2018": "ACAD2018",
}


def _load_ezdxf() -> tuple[Any, Any]:
    try:
        import ezdxf
        from ezdxf import bbox
    except ImportError as exc:
        raise RuntimeError(
            "Missing dependency 'ezdxf'. Install resources/requirements.txt first."
        ) from exc
    return ezdxf, bbox


def _executable(path: Path) -> Path | None:
    expanded = path.expanduser().resolve()
    if expanded.suffix.lower() == ".app":
        candidate = expanded / "Contents" / "MacOS" / "ODAFileConverter"
        return candidate if candidate.is_file() and os.access(candidate, os.X_OK) else None
    return expanded if expanded.is_file() and os.access(expanded, os.X_OK) else None


def _find_oda(explicit: Path | None) -> Path | None:
    if explicit:
        return _executable(explicit)

    env_value = os.environ.get("ODA_FILE_CONVERTER")
    if env_value:
        executable = _executable(Path(env_value))
        if executable:
            return executable

    found = shutil.which("ODAFileConverter")
    if found:
        return Path(found).resolve()

    application = _executable(Path("/Applications/ODAFileConverter.app"))
    return application


def _find_libredwg(explicit: Path | None) -> Path | None:
    if explicit:
        return _executable(explicit)
    env_value = os.environ.get("DWGWRITE")
    if env_value:
        executable = _executable(Path(env_value))
        if executable:
            return executable
    found = shutil.which("dwgwrite")
    return Path(found).resolve() if found else None


def _select_converter(mode: str, explicit: Path | None) -> tuple[str, Path]:
    if mode in {"auto", "oda"}:
        executable = _find_oda(explicit)
        if executable:
            return "oda", executable
        if mode == "auto" and explicit:
            raise ValueError(
                "--converter-path is not an ODA executable or .app bundle. "
                "Select --converter libredwg explicitly for GNU LibreDWG."
            )
        raise FileNotFoundError(
            "ODAFileConverter not found. Install ODA File Converter, add its executable "
            "to PATH, set ODA_FILE_CONVERTER, or pass --converter-path. Auto mode does "
            "not fall back to experimental LibreDWG output."
        )

    executable = _find_libredwg(explicit)
    if not executable:
        raise FileNotFoundError(
            "dwgwrite not found; add it to PATH, set DWGWRITE, or pass --converter-path"
        )
    return "libredwg", executable


def _libredwg_env(executable: Path) -> dict[str, str]:
    env = os.environ.copy()
    candidate = executable.parent.parent / "lib"
    if candidate.exists():
        current_macos = env.get("DYLD_LIBRARY_PATH", "")
        env["DYLD_LIBRARY_PATH"] = f"{candidate}:{current_macos}".rstrip(":")
        current_linux = env.get("LD_LIBRARY_PATH", "")
        env["LD_LIBRARY_PATH"] = f"{candidate}:{current_linux}".rstrip(":")
    return env


def _run_libredwg(
    executable: Path,
    input_path: Path,
    output_path: Path,
    version: str,
) -> subprocess.CompletedProcess[str]:
    if version != "r2000":
        raise ValueError("GNU LibreDWG fallback only supports r2000; use ODA for newer DWG versions")
    return subprocess.run(
        [
            str(executable),
            "--as",
            version,
            "--format",
            "DXF",
            "--file",
            str(output_path),
            "--overwrite",
            str(input_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=_libredwg_env(executable),
    )


def _run_oda_conversion(
    executable: Path,
    input_path: Path,
    output_path: Path,
    version: str,
    output_type: str,
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="oda-input-") as input_name, tempfile.TemporaryDirectory(
        prefix="oda-output-"
    ) as output_name:
        input_dir = Path(input_name)
        output_dir = Path(output_name)
        staged_input = input_dir / f"source{input_path.suffix.lower()}"
        shutil.copy2(input_path, staged_input)
        result = subprocess.run(
            [
                str(executable),
                str(input_dir),
                str(output_dir),
                ODA_VERSIONS[version],
                output_type,
                "0",
                "1",
                f"*{input_path.suffix.lower()}",
            ],
            capture_output=True,
            text=True,
            check=False,
            cwd=executable.parent,
        )
        generated = output_dir / staged_input.with_suffix(f".{output_type.lower()}").name
        if result.returncode == 0 and generated.exists():
            shutil.copy2(generated, output_path)
        return result


def _bbox_values(extents: Any) -> list[float] | None:
    if not extents.has_data:
        return None
    return [
        float(extents.extmin.x),
        float(extents.extmin.y),
        float(extents.extmin.z),
        float(extents.extmax.x),
        float(extents.extmax.y),
        float(extents.extmax.z),
    ]


def _inspect_dxf(path: Path, ezdxf: Any, bbox: Any) -> dict[str, Any]:
    try:
        document = ezdxf.readfile(path)
    except (OSError, ezdxf.DXFError) as exc:
        raise ValueError(f"Unable to read DXF: {path}") from exc
    auditor = document.audit()
    entities = list(document.modelspace())
    type_counts = Counter(entity.dxftype() for entity in entities)
    layer_counts = Counter(entity.dxf.layer for entity in entities)
    return {
        "auditErrors": len(auditor.errors),
        "auditFixes": len(auditor.fixes),
        "entityCount": len(entities),
        "entityTypes": dict(sorted(type_counts.items())),
        "entityLayers": dict(sorted(layer_counts.items())),
        "bbox3d": _bbox_values(bbox.extents(entities, fast=True)),
    }


def _bbox_matches(first: list[float] | None, second: list[float] | None) -> bool:
    if first is None or second is None:
        return first == second
    scale = max([1.0, *[abs(value) for value in first], *[abs(value) for value in second]])
    tolerance = max(1e-6, scale * 1e-10)
    return all(abs(left - right) <= tolerance for left, right in zip(first, second, strict=True))


def _verify_oda_roundtrip(
    executable: Path,
    source_dxf: Path,
    output_dwg: Path,
    version: str,
    source: dict[str, Any],
    ezdxf: Any,
    bbox: Any,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="oda-roundtrip-") as temp_name:
        roundtrip_path = Path(temp_name) / source_dxf.name
        result = _run_oda_conversion(
            executable,
            output_dwg,
            roundtrip_path,
            version,
            "DXF",
        )
        if result.returncode != 0 or not roundtrip_path.exists():
            raise RuntimeError(
                "ODA DWG-to-DXF round-trip failed: "
                f"exit={result.returncode}; {result.stderr[-4000:]}"
            )
        roundtrip = _inspect_dxf(roundtrip_path, ezdxf, bbox)

    checks = {
        "roundtripAuditClean": not roundtrip["auditErrors"] and not roundtrip["auditFixes"],
        "entityTypesMatch": source["entityTypes"] == roundtrip["entityTypes"],
        "entityLayersMatch": source["entityLayers"] == roundtrip["entityLayers"],
        "bboxMatches": _bbox_matches(source["bbox3d"], roundtrip["bbox3d"]),
    }
    if not all(checks.values()):
        raise RuntimeError(
            "ODA round-trip verification failed: "
            f"checks={checks}; source={source}; roundtrip={roundtrip}"
        )
    return {
        "verified": True,
        "method": "ODA DWG-to-DXF round trip plus ezdxf audit",
        "checks": checks,
        "sourceDxf": source,
        "roundtripDxf": roundtrip,
    }


def _verify_with_dwgread(output_path: Path, converter_path: Path) -> dict[str, Any] | None:
    candidates = [converter_path.with_name("dwgread")]
    path_candidate = shutil.which("dwgread")
    if path_candidate:
        candidates.append(Path(path_candidate))
    dwgread = next((path for path in candidates if path.exists()), None)
    if not dwgread:
        return None

    with tempfile.TemporaryDirectory(prefix="dwgread-verify-") as temp_name:
        json_path = Path(temp_name) / "verify.json"
        result = subprocess.run(
            [str(dwgread), "-O", "minJSON", "-o", str(json_path), str(output_path)],
            capture_output=True,
            text=True,
            check=False,
            env=_libredwg_env(dwgread),
        )
        if result.returncode != 0 or not json_path.exists():
            return {"verified": False, "error": result.stderr.strip()[-1000:]}
        data = json.loads(json_path.read_text(encoding="utf-8"))
        objects = data.get("OBJECTS", [])
        entities = Counter(
            item["entity"] for item in objects if isinstance(item.get("entity"), str)
        )
        return {
            "verified": True,
            "method": "LibreDWG self-read only; not a delivery compatibility guarantee",
            "version": data.get("FILEHEADER", {}).get("version"),
            "entities": dict(sorted(entities.items())),
            "layers": [
                item.get("name") for item in objects if item.get("object") == "LAYER"
            ],
        }


def _write_json_atomic(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".dwg-report-", dir=path.parent) as temp_name:
        staged_path = Path(temp_name) / path.name
        staged_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        json.loads(staged_path.read_text(encoding="utf-8"))
        os.replace(staged_path, path)


def convert(
    input_path: Path,
    output_path: Path,
    converter: str,
    converter_path: Path | None,
    version: str,
    overwrite: bool,
) -> dict[str, Any]:
    if output_path.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {output_path}; pass --overwrite to replace it")
    source_prj = input_path.with_suffix(".prj")
    output_prj = output_path.with_suffix(".prj")
    if (
        source_prj.exists()
        and source_prj.resolve() != output_prj.resolve()
        and output_prj.exists()
        and not overwrite
    ):
        raise FileExistsError(
            f"Output CRS sidecar exists: {output_prj}; pass --overwrite to replace it"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    mode, executable = _select_converter(converter, converter_path)
    ezdxf, bbox = _load_ezdxf()
    source_inspection = _inspect_dxf(input_path, ezdxf, bbox)
    if source_inspection["auditErrors"] or source_inspection["auditFixes"]:
        raise RuntimeError(
            "Source DXF failed ezdxf audit before DWG conversion: "
            f"errors={source_inspection['auditErrors']}, "
            f"fixes={source_inspection['auditFixes']}"
        )

    with tempfile.TemporaryDirectory(
        prefix="dxf-to-dwg-",
        dir=output_path.parent,
    ) as temp_name:
        staged_output = Path(temp_name) / output_path.name
        if mode == "oda":
            result = _run_oda_conversion(
                executable,
                input_path,
                staged_output,
                version,
                "DWG",
            )
        else:
            result = _run_libredwg(executable, input_path, staged_output, version)
        if result.returncode != 0 or not staged_output.exists():
            raise RuntimeError(
                f"DWG conversion failed with {mode} (exit {result.returncode}):\n"
                f"{result.stderr[-4000:]}"
            )

        signature = staged_output.read_bytes()[:6].decode("ascii", errors="replace")
        expected_signature = DWG_SIGNATURES[version]
        if signature != expected_signature:
            raise RuntimeError(
                f"Unexpected DWG signature {signature!r}; expected {expected_signature!r} for {version}"
            )

        if mode == "oda":
            verification = _verify_oda_roundtrip(
                executable,
                input_path,
                staged_output,
                version,
                source_inspection,
                ezdxf,
                bbox,
            )
            delivery_status = "validated"
        else:
            verification = {
                "sourceDxf": source_inspection,
                "selfRead": _verify_with_dwgread(staged_output, executable),
            }
            delivery_status = "experimental-not-for-delivery"

        os.replace(staged_output, output_path)

    if source_prj.exists() and source_prj.resolve() != output_prj.resolve():
        shutil.copy2(source_prj, output_prj)

    return {
        "source": str(input_path.resolve()),
        "output": str(output_path.resolve()),
        "converter": mode,
        "converterPath": str(executable),
        "requestedVersion": version,
        "dwgSignature": signature,
        "deliveryStatus": delivery_status,
        "verification": verification,
        "converterWarnings": result.stderr.strip().splitlines()[:50],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Convert DXF to DWG. ODA output is round-trip validated; LibreDWG is experimental."
    )
    parser.add_argument("input", type=Path, help="Input .dxf file")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument(
        "--converter",
        choices=("auto", "oda", "libredwg"),
        default="auto",
        help="Auto uses ODA only; LibreDWG must be selected explicitly",
    )
    parser.add_argument(
        "--converter-path",
        type=Path,
        help="ODA executable, macOS .app bundle, or explicit dwgwrite executable",
    )
    parser.add_argument("--version", choices=tuple(DWG_SIGNATURES), default="r2000")
    parser.add_argument("--report", type=Path, help="Optional JSON validation report")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    try:
        input_path = args.input.resolve()
        output_path = (args.output or input_path.with_suffix(".dwg")).resolve()
        report_path = args.report.resolve() if args.report else None
        if not input_path.is_file():
            raise ValueError(f"Input file not found: {input_path}")
        if input_path.suffix.lower() != ".dxf":
            raise ValueError("Input must be a .dxf file")
        if output_path.suffix.lower() != ".dwg":
            raise ValueError("Output must be a .dwg file")
        if report_path:
            if report_path.suffix.lower() != ".json":
                raise ValueError("Validation report must be a .json file")
            if report_path in {input_path, output_path}:
                raise ValueError("Validation report must differ from input and output files")
            if report_path.exists() and not args.overwrite:
                raise FileExistsError(
                    f"Report exists: {report_path}; pass --overwrite to replace it"
                )
        summary = convert(
            input_path,
            output_path,
            args.converter,
            args.converter_path,
            args.version,
            args.overwrite,
        )
        if report_path:
            summary["validationReport"] = str(report_path)
            _write_json_atomic(report_path, summary)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"OUTPUT: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
