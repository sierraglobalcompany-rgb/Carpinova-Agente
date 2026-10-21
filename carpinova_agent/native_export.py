"""Explicit, allowlisted native CAD export from ONE reviewed CADExchange.

Native programs run only after host-side environment opt-in and human
confirmation of a *review* export. Never accept executables, scripts,
filesystem destinations or shell expressions from a language-model tool call.
No manufacturing/cutting authority is conferred by native file production.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZipFile

from .cad_exchange import validate_exchange
from .core import DesignError

REVIEW_CONFIRMATION = "AUTORIZO_EXPORTAR_BORRADOR_3D"
_RELEASE_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready", "purchase_ready")
FILES = ("native.FCStd", "native.blend", "presentation.blend",
         "presentation.png", "native-manifest.json")


class NativeExportError(ValueError):
    """Native CAD export has not passed an explicit safety or integrity gate."""


def _binary(value: str | None, expected: str) -> Path:
    if not value:
        raise NativeExportError("Configuración faltante: CARPINOVA_" + expected.upper())
    path = Path(value).expanduser()
    if not path.is_absolute() or not path.is_file():
        raise NativeExportError("Aplicación nativa debe ser un ejecutable local absoluto y existente.")
    # Ubuntu may package freecadcmd/blender as system-managed symlinks.
    # Require BOTH the configured entrypoint and its resolved target to have
    # an allowlisted basename: a link to sh/cmd/python is always rejected.
    resolved = path.resolve(strict=True)
    allowed = ({"freecadcmd", "freecadcmd.exe"} if expected == "freecadcmd"
               else {"blender", "blender.exe"})
    if path.name.lower() not in allowed or resolved.name.lower() not in allowed:
        raise NativeExportError("Nombre de ejecutable no autorizado para " + expected)
    return resolved


def _load_review(folder: Path) -> dict[str, Any]:
    folder = Path(folder)
    cadfile = folder / "cad-exchange.json"
    manifestfile = folder / "manifest.json"
    if (not folder.is_dir() or folder.is_symlink()
            or cadfile.is_symlink() or manifestfile.is_symlink()
            or not cadfile.is_file() or not manifestfile.is_file()
            or cadfile.stat().st_size > 262144 or manifestfile.stat().st_size > 65536):
        raise NativeExportError("Proyecto fuente inexistente, externo o no confiable.")
    cad = validate_exchange(json.loads(cadfile.read_text(encoding="utf-8")))
    review = json.loads(manifestfile.read_text(encoding="utf-8"))
    if (review.get("status") != "DRAFT_NOT_FOR_CUTTING"
            or review.get("geometry_sha256") != cad["geometry_sha256"]
            or review.get("piece_count") != len(cad["boxes"])
            or any(review.get(k) is not False for k in _RELEASE_FLAGS)):
        raise NativeExportError("Manifiesto y geometría de revisión no coinciden.")
    return cad


def _checked_report(
    output: str, prefix: str, cad: dict[str, Any],
) -> dict[str, Any]:
    matches = [line[len(prefix):] for line in output.splitlines()
               if line.startswith(prefix)]
    if len(matches) != 1:
        raise NativeExportError("No se obtuvo un reporte nativo único: " + prefix)
    try:
        report = json.loads(matches[0])
        proof = report["native_measurements"]
    except (KeyError, ValueError, TypeError) as exc:
        raise NativeExportError("Reporte nativo corrupto.") from exc
    if (report.get("geometry_sha256") != cad["geometry_sha256"]
            or proof.get("geometry_sha256") != cad["geometry_sha256"]
            or proof.get("verified_piece_count") != len(cad["boxes"])
            or proof.get("status") != "NATIVE_GEOMETRY_MATCH"
            or any(proof.get(k) is not False
                   for k in ("fabrication_ready", "cutting_ready", "drilling_ready"))
            or type(proof.get("max_abs_error_mm")) not in (float, int)
            or not (0 <= proof["max_abs_error_mm"] <= 0.05)):
        raise NativeExportError("Geometría medida no coincide con el CAD aprobado.")
    return report


def export_native_project(
    project_folder: Path,
    *,
    confirmation: str,
    freecad_executable: str | None,
    blender_executable: str | None,
    enabled: bool,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Create NEW native/ artifacts from one checked project using fixed scripts.

    All inputs are determined by the server and its trusted environment; the
    language model may supply only its existing project ID and the explicit
    review-confirmation phrase. Runs in a temporary folder on same filesystem.
    """
    if enabled is not True or confirmation != REVIEW_CONFIRMATION:
        raise NativeExportError("Requiere habilitación del host y confirmación explícita.")
    freecad = _binary(freecad_executable, "freecadcmd")
    blender = _binary(blender_executable, "blender")
    folder = Path(project_folder)
    cad = _load_review(folder)
    dest = folder / "native"
    if dest.exists() or dest.is_symlink():
        raise NativeExportError("Ya existe exportación nativa: no sobrescribir.")
    repo = Path(__file__).resolve().parents[1]
    fcscript = repo / "integrations" / "freecad_headless_proof.FCScript"
    blenderscript = repo / "integrations" / "blender_from_contract.py"
    presentation = repo / "integrations" / "blender_presentation.py"
    if not all(p.is_file() for p in (fcscript, blenderscript, presentation)):
        raise NativeExportError("Adaptador nativo faltante en repositorio; clone incompleto.")

    with TemporaryDirectory(prefix=".carpinova-native-", dir=folder) as tmp:
        stage = Path(tmp) / "native"
        stage.mkdir()
        environment = {
            **os.environ,
            "GITHUB_WORKSPACE": str(repo),
            "PYTHONPATH": str(repo),
            "RUNNER_TEMP": str(folder.resolve(strict=True)),
            "CARPINOVA_CAD_INPUT": str((folder / "cad-exchange.json").resolve(strict=True)),
            "CARPINOVA_FCSTD_OUTPUT": str(stage / "native.FCStd"),
        }
        jobs = (
            ("FreeCAD", [str(freecad), str(fcscript)], "FREECAD_NATIVE_RESULT=", 180),
            ("Blender", [str(blender), "--background", "--factory-startup",
                         "--disable-autoexec", "--python-use-system-env",
                         "--python-exit-code", "12", "--python", str(blenderscript),
                         "--", "--input", environment["CARPINOVA_CAD_INPUT"],
                         "--output", str(stage / "native.blend")], "", 180),
            ("BlenderPresentation", [
                str(blender), "--background", "--factory-startup",
                "--disable-autoexec", "--python-use-system-env", "--python-exit-code", "12",
                "--python", str(presentation), "--",
                "--input-cad", environment["CARPINOVA_CAD_INPUT"],
                "--input-blend", str(stage / "native.blend"),
                "--output-blend", str(stage / "presentation.blend"),
                "--output-png", str(stage / "presentation.png"),
            ], "BLENDER_PRESENTATION_RESULT=", 240),
        )
        reports = {}
        for name, command, prefix, seconds in jobs:
            try:
                result = runner(command, cwd=str(repo), env=environment,
                                capture_output=True, text=True, timeout=seconds,
                                check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                raise NativeExportError(name + " no pudo ejecutarse/terminar.") from exc
            if result.returncode != 0:
                raise NativeExportError(name + " falló (código " + str(result.returncode)
                                        + "); no se publica ningún archivo.")
            output = result.stdout
            if not isinstance(output, str) or len(output) > 500000:
                raise NativeExportError("Reporte nativo excesivo o inválido.")
            # Blender's existing adapter emits a single JSON report line.
            if name == "Blender":
                candidates = [line for line in output.splitlines()
                              if line.startswith('{"geometry_sha256"')
                              or (line.startswith("{") and '"native_measurements"' in line)]
                if len(candidates) != 1:
                    raise NativeExportError("Blender no devolvió un informe JSON único.")
                output = "BLENDER_NATIVE_RESULT=" + candidates[0]
                prefix = "BLENDER_NATIVE_RESULT="
            reports[name] = _checked_report(output, prefix, cad)
        with ZipFile(stage / "native.FCStd") as z:
            if z.testzip() is not None or "Document.xml" not in z.namelist():
                raise NativeExportError("Archivo FreeCAD inválido.")
        for name in ("native.blend", "presentation.blend"):
            if (stage / name).read_bytes()[:7] != b"BLENDER":
                raise NativeExportError("Archivo Blender inválido.")
        image = (stage / "presentation.png").read_bytes()
        if image[:8] != b"\x89PNG\r\n\x1a\n":
            raise NativeExportError("Render PNG inválido.")
        manifest = {
            "status": "NATIVE_PREVIEW_NOT_FOR_CUTTING",
            "geometry_sha256": cad["geometry_sha256"],
            "piece_count": len(cad["boxes"]),
            "files": list(FILES),
            "reports": {k: v["native_measurements"] for k, v in reports.items()},
            "presentation_png_sha256": hashlib.sha256(image).hexdigest(),
            **{key: False for key in _RELEASE_FLAGS},
        }
        (stage / "native-manifest.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if dest.exists() or dest.is_symlink():
            raise NativeExportError("Otra ejecución creó native; no sobrescribir.")
        os.rename(stage, dest)
    return manifest
