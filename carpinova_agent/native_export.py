"""Explicit, allowlisted native CAD export from ONE reviewed CADExchange.

Native programs run only after host-side environment opt-in and human
confirmation of a *review* export. Never accept executables, scripts,
filesystem destinations or shell expressions from a language-model tool call.
No manufacturing/cutting authority is conferred by native file production.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZipFile

from .pilot_cli import PilotError, verify_pilot_bundle
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
    allowed = ({"freecadcmd", "freecadcmd.exe", "freecadcmd-python3"} if expected == "freecadcmd"
               else {"blender", "blender.exe"})
    if path.name.lower() not in allowed or resolved.name.lower() not in allowed:
        raise NativeExportError("Nombre de ejecutable no autorizado para " + expected)
    return resolved


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



def _approval_location(project_folder: Path, approval_dir: Path | None) -> Path:
    """Host-owned sidecar OUTSIDE the review output root; never an MCP argument."""
    root = Path(approval_dir) if approval_dir is not None else Path(
        os.environ.get("CARPINOVA_NATIVE_APPROVAL_DIR", "")
    )
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        raise NativeExportError("Configurar directorio local de autorizaciones fuera de los proyectos.")
    root = root.resolve(strict=True)
    folder = project_folder.resolve(strict=True)
    if root == folder.parent or root.is_relative_to(folder.parent):
        raise NativeExportError("Las autorizaciones no deben guardarse en la salida del Agente.")
    name = hashlib.sha256(str(folder).encode("utf-8")).hexdigest()[:24]
    return root / ("native-" + name + ".json")


def issue_native_approval(
    project_folder: Path, approval_dir: Path, *, ttl_seconds: int = 900,
) -> Path:
    """Trusted local operator/CI harness ONLY; never exposed as an MCP tool.

    The host must separately acquire informed consent before calling this
    method. The sidecar is tied to project absolute path AND geometry digest,
    cannot be overwritten, and expires in no more than 15 minutes.
    """
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
        raise NativeExportError("Ventana de autorización inválida.")
    folder = Path(project_folder)
    try:
        cad = verify_pilot_bundle(folder)
    except (PilotError, DesignError) as exc:
        raise NativeExportError("No se puede autorizar un proyecto inconsistente.") from exc
    location = _approval_location(folder, approval_dir)
    payload = {
        "schema": 1,
        "project": str(folder.resolve(strict=True)),
        "geometry_sha256": cad["geometry_sha256"],
        "piece_count": len(cad["boxes"]),
        "expires_at": int(time.time()) + ttl_seconds,
    }
    try:
        with location.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(payload, output, sort_keys=True)
            output.write("\n")
        os.chmod(location, 0o600)
    except FileExistsError as exc:
        raise NativeExportError("Ya hay una autorización pendiente; no sobrescribir.") from exc
    return location


def _consume_native_approval(
    folder: Path, cad: dict[str, Any], approval_dir: Path | None,
) -> None:
    path = _approval_location(folder, approval_dir)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 2048:
        raise NativeExportError("Falta aprobación local de un solo uso para exportar CAD.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise NativeExportError("Aprobación local inválida.") from exc
    if (type(data) is not dict or set(data) != {
        "schema", "project", "geometry_sha256", "piece_count", "expires_at"
    } or data["schema"] != 1
            or data["project"] != str(folder.resolve(strict=True))
            or data["geometry_sha256"] != cad["geometry_sha256"]
            or data["piece_count"] != len(cad["boxes"])
            or type(data["expires_at"]) is not int
            or data["expires_at"] < int(time.time())
            or data["expires_at"] > int(time.time()) + 900):
        raise NativeExportError("Aprobación vencida o incompatible con el mueble.")
    # One-shot gate. Failure/timeout also consumes approval; reapproval is
    # explicit and cannot be obtained through the MCP model tools.
    path.unlink()


def main(argv: list[str] | None = None) -> int:
    """Real owner must approve from a separate human PowerShell/terminal."""
    parser = argparse.ArgumentParser(description="Autorizar UNA previsualización 3D; no fabricar.")
    parser.add_argument("--approve-project", required=True, type=Path)
    parser.add_argument("--approval-dir", required=True, type=Path)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        parser.error("La aprobación requiere terminal interactiva del propietario.")
    cad = verify_pilot_bundle(args.approve_project)
    print("Mueble:", args.approve_project.resolve(strict=True))
    print("Piezas:", len(cad["boxes"]))
    print("CAD SHA-256:", cad["geometry_sha256"])
    print("Solo borrador. NO cortar, perforar ni comprar.")
    phrase = input("Escribir AUTORIZO y los últimos 8 caracteres del SHA separados por espacio: ")
    if phrase.strip() != "AUTORIZO " + cad["geometry_sha256"][-8:]:
        raise NativeExportError("Aprobación humana no recibida.")
    location = issue_native_approval(args.approve_project, args.approval_dir)
    print("Aprobación local emitida; vence en 15 minutos y admite UN uso.")
    return 0


def export_native_project(
    project_folder: Path,
    *,
    confirmation: str,
    freecad_executable: str | None,
    blender_executable: str | None,
    enabled: bool,
    approval_dir: Path | None = None,
    runner: Any = subprocess.run,
) -> dict[str, Any]:
    """Create NEW native/ artifacts from one checked project using fixed scripts.

    All programs and paths come from the trusted host. The MCP model can
    supply a project ID and phrase but cannot issue the separate, expiring
    human approval. Runs in a temporary folder on the same filesystem.
    """
    if enabled is not True or confirmation != REVIEW_CONFIRMATION:
        raise NativeExportError("Requiere habilitación del host y confirmación explícita.")
    freecad = _binary(freecad_executable, "freecadcmd")
    blender = _binary(blender_executable, "blender")
    folder = Path(project_folder)
    try:
        cad = verify_pilot_bundle(folder)
    except (PilotError, DesignError) as exc:
        raise NativeExportError("Manifiesto, CAD y Maestro no coinciden.") from exc
    dest = folder / "native"
    if dest.exists() or dest.is_symlink():
        raise NativeExportError("Ya existe exportación nativa: no sobrescribir.")
    repo = Path(__file__).resolve().parents[1]
    fcscript = repo / "integrations" / "freecad_headless_proof.FCScript"
    blenderscript = repo / "integrations" / "blender_from_contract.py"
    presentation = repo / "integrations" / "blender_presentation.py"
    if not all(p.is_file() for p in (fcscript, blenderscript, presentation)):
        raise NativeExportError("Adaptador nativo faltante en repositorio; clone incompleto.")
    # A model-generated phrase never constitutes human approval by itself.
    # Check the sidecar AFTER all source checks but BEFORE any subprocess.
    _consume_native_approval(folder, cad, approval_dir)

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


if __name__ == "__main__":
    raise SystemExit(main())
