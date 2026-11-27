"""Prepare the isolated, nominal CarpiNova MCP runtime on Windows."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
from typing import Any


PINS = {"mcp": "1.30.0", "resvg_py": "0.5.0", "Pillow": "13.0.0"}
REQUIRED_ENV = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "TEMP", "TMP")


class RuntimeBlocked(RuntimeError):
    pass


def _path_linked(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(root.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _minimal_env(*, pip: bool = False) -> dict[str, str]:
    env = {}
    for name in REQUIRED_ENV:
        value = os.environ.get(name)
        if not value:
            raise RuntimeBlocked(f"Windows requiere la variable {name}.")
        env[name] = value
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    if pip:
        env["PIP_CONFIG_FILE"] = "NUL"
    return env


def _run(command: list[str], *, repo: Path, env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command, cwd=repo, env=env, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=timeout, check=False,
    )


def _source_python(requested: str | None, repo: Path) -> Path:
    if requested:
        candidate = Path(requested)
        if not candidate.is_absolute() or not candidate.is_file() or _path_linked(candidate):
            raise RuntimeBlocked("-PythonExe debe ser un ejecutable absoluto existente y real.")
    else:
        located = shutil.which("python")
        if not located:
            raise RuntimeBlocked("No se encontró Python 3.12 en PATH; no se instala Python global.")
        candidate = Path(located)
    candidate = candidate.resolve(strict=True)
    result = _run(
        [str(candidate), "-c", "import json,sys; print(json.dumps({'exe':sys.executable,'version':list(sys.version_info[:3])}))"],
        repo=repo, env=_minimal_env(), timeout=15,
    )
    if result.returncode != 0:
        raise RuntimeBlocked("No se pudo comprobar el Python elegido: " + result.stderr[-1200:].strip())
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeBlocked("Python devolvió una identidad no legible.") from exc
    if identity.get("version", [])[:2] != [3, 12]:
        raise RuntimeBlocked(f"Se requiere Python 3.12; se encontró {identity.get('version')}.")
    actual = Path(identity["exe"]).resolve(strict=True)
    if actual != candidate:
        raise RuntimeBlocked("sys.executable no coincide con el Python absoluto elegido.")
    return candidate


def _read_venv_identity(python: Path, expected: Path, repo: Path) -> tuple[dict[str, Any] | None, str]:
    cfg = expected / "pyvenv.cfg"
    if _path_linked(expected) or not python.is_file() or _path_linked(python) or not cfg.is_file():
        return None, "falta ejecutable/pyvenv.cfg o el entorno usa un enlace"
    if not _inside(expected, repo):
        return None, "la ruta real sale del checkout"
    try:
        values = {}
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip().lower()] = value.strip().lower()
        if values.get("include-system-site-packages", "false") != "false":
            return None, "include-system-site-packages no es false"
    except OSError as exc:
        return None, f"no se leyó pyvenv.cfg: {exc}"
    probe = (
        "import importlib.metadata as m, json, pathlib, sys; "
        "import mcp, resvg_py; from PIL import Image; "
        "from mcp.client.stdio import stdio_client; "
        "print(json.dumps({'exe':sys.executable,'prefix':sys.prefix,'base':sys.base_prefix,"
        "'python_version':list(sys.version_info[:3]),"
        "'versions':{'mcp':m.version('mcp'),'resvg_py':m.version('resvg_py'),'Pillow':m.version('Pillow')}}))"
    )
    result = _run([str(python), "-c", probe], repo=repo, env=_minimal_env(), timeout=20)
    if result.returncode != 0:
        return None, "dependencias/imports o versiones no válidos: " + result.stderr[-1200:].strip()
    try:
        identity = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None, "Python devolvió identidad no legible"
    if identity.get("python_version", [])[:2] != [3, 12]:
        return None, f"el venv no usa Python 3.12: {identity.get('python_version')}"
    expected_real = expected.resolve(strict=True)
    if Path(identity["prefix"]).resolve(strict=True) != expected_real:
        return None, "sys.prefix no corresponde al venv candidato"
    if Path(identity["base"]).resolve(strict=True) == expected_real:
        return None, "sys.prefix coincide con base_prefix"
    if Path(identity["exe"]).resolve(strict=True) != python.resolve(strict=True):
        return None, "sys.executable no corresponde al venv"
    if {key: identity["versions"].get(key) for key in PINS} != PINS:
        return None, f"pins distintos: {identity['versions']}"
    pip_check = _run([str(python), "-m", "pip", "check"], repo=repo, env=_minimal_env(pip=True), timeout=45)
    if pip_check.returncode != 0:
        return None, "pip check falló: " + (pip_check.stdout + pip_check.stderr)[-1200:].strip()
    identity["pip_check"] = "PASS"
    identity["imports"] = ["mcp", "resvg_py", "PIL.Image", "mcp.client.stdio.stdio_client"]
    return identity, "validado"


def _ensure_real_dir(path: Path, repo: Path, *, create: bool) -> Path:
    if path.exists():
        if _path_linked(path) or not path.is_dir() or not _inside(path, repo):
            raise RuntimeBlocked(f"Directorio no real/seguro: {path}")
    elif create:
        path.mkdir()
    else:
        raise RuntimeBlocked(f"Falta el directorio requerido: {path}")
    resolved = path.resolve(strict=True)
    if not _inside(resolved, repo):
        raise RuntimeBlocked(f"Directorio fuera del checkout: {path}")
    return resolved


def _new_venv_path(runtime_root: Path, repo: Path) -> Path:
    default = runtime_root / "venv"
    if not default.exists() and not default.is_symlink():
        return default
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for sequence in range(100):
        suffix = f"-{sequence}" if sequence else ""
        candidate = runtime_root / f"venv-{stamp}{suffix}"
        if not candidate.exists() and not candidate.is_symlink():
            if not _inside(runtime_root, repo):
                raise RuntimeBlocked("La raíz de runtime no pertenece al checkout.")
            return candidate
    raise RuntimeBlocked("No se encontró una ruta nueva para crear el venv sin sobrescribir.")


def _write_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_name(path.name + ".tmp")
    raw = json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    temporary.write_text(raw, encoding="utf-8", newline="\n")
    temporary.replace(path)


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write_config(repo: Path, python: Path, projects: Path, config_dir: Path) -> Path:
    config = config_dir / "codex-config.toml.example"
    environment = {
        "PYTHONPATH": str(repo),
        "CARPINOVA_OUTPUT_ROOT": str(projects),
        "CARPINOVA_NATIVE_EXECUTION_ENABLED": "0",
        "PYTHONNOUSERSITE": "1",
    }
    escaped = lambda value: _toml_string(value)
    text = (
        "[mcp_servers.carpinova]\n"
        f"command = {escaped(str(python))}\n"
        'args = ["-m", "carpinova_agent.mcp_bridge"]\n'
        "startup_timeout_sec = 30\n"
        "tool_timeout_sec = 90\n\n"
        "[mcp_servers.carpinova.env]\n"
        + "".join(f"{key} = {escaped(value)}\n" for key, value in environment.items())
    )
    if config.exists():
        if config.read_text(encoding="utf-8") != text:
            raise RuntimeBlocked(f"No se sobrescribe un ejemplo local distinto: {config}")
    else:
        config.write_text(text, encoding="utf-8", newline="\n")
    parsed = tomllib.loads(config.read_text(encoding="utf-8"))
    server = parsed["mcp_servers"]["carpinova"]
    if (server["command"] != str(python) or server["args"] != ["-m", "carpinova_agent.mcp_bridge"]
            or server["startup_timeout_sec"] != 30 or server["tool_timeout_sec"] != 90
            or server["env"] != environment or "CARPINOVA_NATIVE_APPROVAL_DIR" in server["env"]):
        raise RuntimeBlocked("El ejemplo TOML no coincide con las rutas/flags esperados.")
    if Path(server["command"]).resolve(strict=True) != python.resolve(strict=True):
        raise RuntimeBlocked("command del TOML no resuelve al Python validado.")
    if Path(server["env"]["PYTHONPATH"]).resolve(strict=True) != repo:
        raise RuntimeBlocked("PYTHONPATH del TOML no apunta a este checkout.")
    if Path(server["env"]["CARPINOVA_OUTPUT_ROOT"]).resolve(strict=True) != projects:
        raise RuntimeBlocked("CARPINOVA_OUTPUT_ROOT no apunta a projects.")
    return config


def _install(python: Path, requirements: Path, repo: Path, wheelhouse: Path | None,
             allow_download: bool, log_path: Path) -> tuple[str, str]:
    base = [str(python), "-m", "pip", "--isolated", "--disable-pip-version-check",
            "--no-input", "--no-cache-dir", "install", "--only-binary=:all:"]
    attempts: list[tuple[str, list[str]]] = []
    if wheelhouse is not None:
        attempts.append(("OFFLINE", base + ["--no-index", "--find-links", str(wheelhouse), "-r", str(requirements)]))
    elif allow_download:
        attempts.append(("PYPI", base + ["--index-url", "https://pypi.org/simple", "--timeout", "15", "--retries", "1", "-r", str(requirements)]))
    else:
        raise RuntimeBlocked("No hay runtime válido y falta -AllowDownload o un wheelhouse.")
    if wheelhouse is not None and allow_download:
        attempts.append(("PYPI_FALLBACK_ONCE", base + ["--index-url", "https://pypi.org/simple", "--timeout", "15", "--retries", "1", "-r", str(requirements)]))
    lines: list[str] = []
    deadline = time.monotonic() + 300
    for index, (method, command) in enumerate(attempts):
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            break
        result = _run(command, repo=repo, env=_minimal_env(pip=True), timeout=remaining)
        lines.append(f"method={method} exit_code={result.returncode}\n{result.stdout}{result.stderr}")
        if result.returncode == 0:
            log_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
            return method, "\n".join(lines)
        if index == len(attempts) - 1:
            break
    log_path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    raise RuntimeBlocked("La instalación con ruedas binarias falló; consulte runtime-install.log.")


def prepare(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve(strict=True)
    if not repo.is_dir() or not (repo / "requirements-mcp.txt").is_file():
        raise RuntimeBlocked("--repo debe ser la raíz de CarpiNova con requirements-mcp.txt.")
    requirements = repo / "requirements-mcp.txt"
    requirements_hash = hashlib.sha256(requirements.read_bytes()).hexdigest()
    pins_seen = {}
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = re.fullmatch(r"\s*([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+-]+)\s*", line)
        if match:
            pins_seen[match.group(1)] = match.group(2)
    if pins_seen != PINS:
        raise RuntimeBlocked(f"requirements-mcp.txt no coincide con los pines fijados: {pins_seen}")

    source_python = _source_python(args.python_exe, repo)
    work = repo / "work"
    runtime_root = work / "mcp-runtime"
    if not work.is_dir() or _path_linked(work) or work.resolve(strict=True) != work:
        raise RuntimeBlocked("work debe ser un directorio real del checkout.")
    if not runtime_root.exists():
        runtime_root.mkdir()
    runtime_root = _ensure_real_dir(runtime_root, repo, create=False)
    log_path = runtime_root / "runtime-install.log"
    candidates = [repo / ".venv", runtime_root / "venv"]
    valid = None
    candidate_notes = []
    for candidate in candidates:
        if not candidate.exists():
            continue
        python = candidate / "Scripts" / "python.exe"
        identity, note = _read_venv_identity(python, candidate, repo)
        candidate_notes.append({"path": str(candidate), "valid": identity is not None, "note": note})
        if identity is not None:
            valid = (candidate.resolve(strict=True), python.resolve(strict=True), identity)
            break

    method = "REUSED"
    if valid is None:
        venv_path = _new_venv_path(runtime_root, repo)
        create = _run([str(source_python), "-m", "venv", str(venv_path)],
                      repo=repo, env=_minimal_env(), timeout=120)
        if create.returncode != 0:
            raise RuntimeBlocked("No se pudo crear el venv local: " + (create.stdout+create.stderr)[-1200:].strip())
        if _path_linked(venv_path) or not _inside(venv_path, repo):
            raise RuntimeBlocked("El venv creado no es un directorio real dentro del checkout.")
        venv_path = venv_path.resolve(strict=True)
        venv_python = venv_path / "Scripts" / "python.exe"
        if not venv_python.is_file():
            raise RuntimeBlocked("El venv nuevo no contiene Scripts/python.exe.")
        wheelhouse = None
        if args.wheelhouse:
            wheelhouse = Path(args.wheelhouse)
            if not wheelhouse.is_absolute() or not wheelhouse.is_dir() or _path_linked(wheelhouse):
                raise RuntimeBlocked("--wheelhouse debe ser una ruta absoluta real existente.")
            wheelhouse = wheelhouse.resolve(strict=True)
        method, _install_log = _install(venv_python, requirements, repo, wheelhouse,
                                        args.allow_download, log_path)
        identity, note = _read_venv_identity(venv_python, venv_path, repo)
        if identity is None:
            raise RuntimeBlocked("El entorno instalado no pasó validación: " + note)
        valid = (venv_path, venv_python.resolve(strict=True), identity)

    venv_path, venv_python, identity = valid
    projects = runtime_root / "projects"
    config_dir = runtime_root / "configuracion-local"
    for path in (projects, config_dir):
        if not path.exists():
            path.mkdir()
        _ensure_real_dir(path, repo, create=False)
    config = _write_config(repo, venv_python, projects.resolve(strict=True), config_dir.resolve(strict=True))
    data = {
        "status": "READY",
        "repo": str(repo),
        "python_exe": str(venv_python),
        "venv": str(venv_path),
        "python_version": ".".join(map(str, identity["python_version"])),
        "versions": identity["versions"],
        "pip_check": identity["pip_check"],
        "imports_verified": identity["imports"],
        "requirements_sha256": requirements_hash,
        "requirements_pins": PINS,
        "method": method,
        "config_local": str(config),
        "projects_root": str(projects.resolve(strict=True)),
        "native_execution_enabled": "0",
        "approval_dir_configured": False,
        "candidates_checked": candidate_notes,
    }
    _write_json(runtime_root / "runtime.json", data)
    print("RUNTIME=READY · runtime local de CarpiNova preparado y validado.")
    print(f"Python: {venv_python}")
    print(f"Ejemplo MCP local: {config}")
    print(f"Carpeta projects: {projects.resolve(strict=True)}")
    print(f"Método de dependencias: {method}; ejecución nativa deshabilitada.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepara un runtime MCP aislado de CarpiNova")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--wheelhouse")
    parser.add_argument("--python-exe")
    args = parser.parse_args()
    try:
        return prepare(args)
    except (RuntimeBlocked, OSError, subprocess.TimeoutExpired) as exc:
        repo = Path(args.repo).resolve() if Path(args.repo).exists() else Path(args.repo)
        runtime_root = repo / "work" / "mcp-runtime"
        if runtime_root.exists() and runtime_root.is_dir() and not _path_linked(runtime_root):
            requirements = repo / "requirements-mcp.txt"
            record = {
                "status": "BLOCKED_ENV", "repo": str(repo),
                "requirements_sha256": hashlib.sha256(requirements.read_bytes()).hexdigest() if requirements.is_file() else None,
                "method": "NOT_READY", "error": str(exc)[:1600],
                "native_execution_enabled": "0", "approval_dir_configured": False,
            }
            _write_json(runtime_root / "runtime.json", record)
        print(f"RUNTIME=BLOCKED_ENV · {str(exc)[:500]}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
