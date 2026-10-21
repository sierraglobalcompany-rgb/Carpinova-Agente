"""Install CarpiNova's four canonical skill folders for Codex, with opt-in MCP setup.

Run inside a checked-out CarpiNova-Agente clone:
    python scripts/install_codex_skills.py --scope user --with-mcp
Use --scope repo to install inside the current repo only.
Existing divergent skills are NEVER overwritten. Re-run is idempotent.
"""
from __future__ import annotations

import argparse
import filecmp
import os
from pathlib import Path
import re
import shutil
import tempfile
import tomllib

SKILLS = ("maestro-carpintero", "diseno-muebles",
          "tecnicas-constructivas", "seleccion-herrajes")


def _frontmatter_name(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing SKILL.md frontmatter")
    ending = text.find("\n---", 4)
    if ending < 0:
        raise ValueError(f"{path}: unfinished frontmatter")
    header = text[4:ending]
    match = re.search(r"(?m)^name:\s*([a-z0-9-]+)\s*$", header)
    if not match:
        raise ValueError(f"{path}: missing valid skill name")
    return match.group(1)


def _same_tree(a: Path, b: Path) -> bool:
    if not a.is_dir() or not b.is_dir():
        return False
    left = {str(p.relative_to(a)): p for p in a.rglob("*") if p.is_file()}
    right = {str(p.relative_to(b)): p for p in b.rglob("*") if p.is_file()}
    return left.keys() == right.keys() and all(
        left[k].read_bytes() == right[k].read_bytes() for k in left
    )


def install(repo: Path, target: Path) -> dict[str, str]:
    repo = repo.resolve(strict=True)
    source_root = repo / "skills"
    if not source_root.is_dir():
        raise ValueError("Not a CarpiNova-Agente checkout: skills/ missing.")
    candidates = []
    for name in SKILLS:
        src = source_root / name
        manifest = src / "SKILL.md"
        if not manifest.is_file() or _frontmatter_name(manifest) != name:
            raise ValueError(f"Missing or mismatched canonical skill: {name}")
        candidates.append((name, src))
    target.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError("Destination cannot be a symlink.")
    # Inspect ALL destinations first: one conflicting skill cannot leave a
    # half-completed new installation of earlier skills.
    statuses: dict[str, str] = {}
    for name, src in candidates:
        dest = target / name
        if dest.is_symlink():
            status = ("ALREADY_LINKED" if dest.resolve() == src.resolve()
                      else "CONFLICT")
        elif dest.exists():
            status = "ALREADY_IDENTICAL" if _same_tree(src, dest) else "CONFLICT"
        else:
            status = "NEEDS_INSTALL"
        statuses[name] = status
        if status == "CONFLICT":
            raise FileExistsError(
                f"Existing skill differs: {dest}. No overwrite; inspect manually."
            )
    for name, src in candidates:
        if statuses[name] != "NEEDS_INSTALL":
            continue
        dest = target / name
        # Prepare fully before publishing. Never modify the source repository.
        with tempfile.TemporaryDirectory(prefix=".carpinova-skill-", dir=target) as tmp:
            stage = Path(tmp) / name
            shutil.copytree(src, stage, symlinks=False)
            if _frontmatter_name(stage / "SKILL.md") != name or not _same_tree(src, stage):
                raise ValueError(f"Skill copy verification failed: {name}")
            stage.rename(dest)
        statuses[name] = "INSTALLED"
    return statuses


def configure_mcp(repo: Path, config: Path, *, write: bool = True) -> str:
    """Register only CarpiNova MCP in Codex's existing config, preserving all else.

    Source comes from prepare_windows.ps1, never a model-generated command.
    Fail closed on incompatible, unsafe or already divergent configurations.
    """
    repo = repo.resolve(strict=True)
    source = repo / 'work' / 'configuracion-local' / 'codex-config.toml.example'
    if not source.is_file():
        raise FileNotFoundError('Ejecutar scripts/prepare_windows.ps1 primero: falta MCP example.')
    example_bytes = source.read_bytes()
    example_text = example_bytes.decode('utf-8')
    expected = tomllib.loads(example_text)
    if set(expected) != {'mcp_servers'} or set(expected['mcp_servers']) != {'carpinova'}:
        raise ValueError('MCP example contiene secciones inesperadas.')
    data = expected['mcp_servers']['carpinova']
    env = data['env']
    checks = {
        'args': data['args'] == ['-m', 'carpinova_agent.mcp_bridge'],
        'native_execution_disabled': 'CARPINOVA_NATIVE_EXECUTION_ENABLED' not in env,
        'repo_pythonpath': env.get('PYTHONPATH') == str(repo),
        'python_absolute': Path(data['command']).is_absolute(),
        'python_exists': Path(data['command']).is_file(),
        'output_absolute': Path(env['CARPINOVA_OUTPUT_ROOT']).is_absolute(),
        'output_exists': Path(env['CARPINOVA_OUTPUT_ROOT']).is_dir(),
        'approval_absolute': Path(env['CARPINOVA_NATIVE_APPROVAL_DIR']).is_absolute(),
    }
    invalid = [key for key, passed in checks.items() if not passed]
    if invalid:
        # Keep fail-closed: identify the failing invariant without logging
        # the user's paths, credentials or host environment values.
        raise ValueError('MCP example no coincide con el entorno local comprobado: '
                         + ', '.join(invalid))
    if config.is_symlink():
        raise ValueError('Config Codex no puede ser un enlace simbólico.')
    prior = config.read_bytes() if config.exists() else b''
    text = prior.decode('utf-8-sig') if prior else ''
    current = tomllib.loads(text) if text.strip() else {}
    active = current.get('mcp_servers', {}).get('carpinova')
    if active is not None:
        if active == data:
            return 'ALREADY_CONFIGURED'
        raise FileExistsError('Ya existe otro MCP carpinova. No se reemplaza.')
    if text.rstrip().endswith('[mcp_servers]'):
        raise ValueError('Config tiene una sección MCP pendiente; revisar manualmente.')
    addition = ('\n' if text and not text.endswith('\n') else '') + '\n' + example_text.strip() + '\n'
    proposed = text + addition
    parsed = tomllib.loads(proposed)
    if parsed['mcp_servers']['carpinova'] != data:
        raise ValueError('Config MCP generada no coincide con la muestra.')
    if not write:
        return 'READY_TO_CONFIGURE'
    config.parent.mkdir(parents=True, exist_ok=True)
    if config.exists() and config.read_bytes() != prior:
        raise RuntimeError('Config Codex cambió durante la instalación; abortar.')
    if config.exists() and (config.stat().st_mode & 0o222) == 0:
        raise PermissionError('Config Codex es de solo lectura.')
    fd, temp = tempfile.mkstemp(prefix='.carpinova-config-', dir=config.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(proposed.encode('utf-8'))
        # Do not delete another process's config behind its back. Recheck lease.
        if config.exists() and config.read_bytes() != prior:
            raise RuntimeError('Config Codex cambió antes de publicar.')
        os.replace(temp, config)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return 'CONFIGURED'


def main() -> int:
    parser = argparse.ArgumentParser(description="Register four CarpiNova skills in Codex")
    parser.add_argument("--repo", type=Path,
                        default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--scope", choices=("user", "repo"), default="user")
    parser.add_argument("--with-mcp", action="store_true", help="Add generated safe MCP stanza")
    opts = parser.parse_args()
    target = ((Path.home() / ".agents" / "skills") if opts.scope == "user"
              else (opts.repo / ".agents" / "skills"))
    statuses = install(opts.repo, target)
    for name, status in statuses.items():
        print(f"{name}: {status}")
    print(f"CODEX_SKILLS=4; LOCATION={target}")
    if opts.with_mcp:
        result = configure_mcp(opts.repo, Path.home() / ".codex" / "config.toml")
        print(f"CODEX_MCP={result}")
    else:
        print("MCP opt-in: add --with-mcp after Windows preflight.")
    print("Restart Codex; check /skills and MCP tool carpinova_estado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())