# Reproducible Windows preflight for CarpiNova-Agente (no installation of CAD).
# Keep client configs under ignored work/, NEVER edit users' IDE settings.
[CmdletBinding()]
param([string]$OutputRoot = "")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"

$repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$work = Join-Path $repo "work"
$venv = Join-Path $repo ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $repo "requirements-mcp.txt"
$projects = Join-Path $work "muebles"
$config = Join-Path $work "configuracion-local"
# Host approvals must be outside the repo and review output. Native execution
# remains disabled unless the owner explicitly opts in later.
if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "Windows necesita LOCALAPPDATA para aprobaciones externas."
}
$approvals = [System.IO.Path]::GetFullPath(
    (Join-Path $env:LOCALAPPDATA "CarpiNova\native-approvals")
)
if ($approvals.StartsWith($repo + [System.IO.Path]::DirectorySeparatorChar,
                          [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Las aprobaciones deben estar fuera del repositorio."
}
if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
    throw "Falta requirements-mcp.txt; clonar el repositorio completo."
}
if (-not (Test-Path -LiteralPath $work)) {
    New-Item -ItemType Directory -Path $work | Out-Null
}
if (-not (Test-Path -LiteralPath $projects)) {
    New-Item -ItemType Directory -Path $projects | Out-Null
}
if (-not (Test-Path -LiteralPath $approvals)) {
    New-Item -ItemType Directory -Path $approvals -Force | Out-Null
}
if (-not (Test-Path -LiteralPath $approvals -PathType Container)) {
    throw "Las aprobaciones requieren un directorio del operador."
}
if (-not $OutputRoot) {
    $OutputRoot = Join-Path $work ("preflight-" + (Get-Date -Format "yyyyMMdd-HHmmss"))
}
$OutputRoot = [System.IO.Path]::GetFullPath($OutputRoot)
if (Test-Path -LiteralPath $OutputRoot) {
    if (-not (Test-Path -LiteralPath $OutputRoot -PathType Container) -or
        @(Get-ChildItem -LiteralPath $OutputRoot -Force).Count -gt 0) {
        throw "El preflight exige carpeta nueva o vacia, sin sobrescritura."
    }
}
& python -c 'import sys; assert sys.version_info[:2] == (3, 12), "Python 3.12 required"'
if ($LASTEXITCODE -ne 0) { throw "Se necesita Python 3.12 en PATH." }
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    & python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Error creando .venv." }
}
& $python -c 'import sys; assert sys.version_info[:2] == (3, 12)'
if ($LASTEXITCODE -ne 0) { throw "La .venv no usa Python 3.12." }

Push-Location $repo
try {
    & $python -m pip install -r $requirements
    if ($LASTEXITCODE -ne 0) { throw "Falló instalación de dependencias MCP." }
    & $python -m unittest discover -s tests -q
    if ($LASTEXITCODE -ne 0) { throw "Tests fallaron: no declarar listo." }
    & $python (Join-Path $repo "scripts\verify_local_mcp.py") --output-root $OutputRoot
    if ($LASTEXITCODE -ne 0) { throw "Prueba real MCP falló." }
} finally {
    Pop-Location
}
$reportPath = Join-Path $OutputRoot "mcp-preflight-report.json"
if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
    throw "Falta reporte MCP."
}
$report = Get-Content -LiteralPath $reportPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($report.status -ne "MCP_LOCAL_PROTOCOL_PASS" -or
    $report.tools.Count -ne 6 -or $report.projects.Count -ne 2 -or
    $report.fabrication_authority -ne $false -or
    $report.pc_owner_session_certified -ne $false) {
    throw "Reporte de prueba inconsistente."
}

# Produce local configuration EXAMPLES, never modify real IDE settings.
if (-not (Test-Path -LiteralPath $config)) {
    New-Item -ItemType Directory -Path $config | Out-Null
}
function Escape-Toml([string]$value) {
    return $value.Replace('\', '\\').Replace('"', '\"')
}
$tp = Escape-Toml $python
$tr = Escape-Toml $repo
$to = Escape-Toml $projects
$ta = Escape-Toml $approvals
$codex = @"
[mcp_servers.carpinova]
command = "$tp"
args = ["-m", "carpinova_agent.mcp_bridge"]
startup_timeout_sec = 20
tool_timeout_sec = 60

[mcp_servers.carpinova.env]
PYTHONPATH = "$tr"
CARPINOVA_OUTPUT_ROOT = "$to"
CARPINOVA_NATIVE_APPROVAL_DIR = "$ta"
"@
$antigravity = @{
    mcpServers = @{
        carpinova = @{
            command = $python
            args = @("-m", "carpinova_agent.mcp_bridge")
            env = @{
                PYTHONPATH = $repo
                CARPINOVA_OUTPUT_ROOT = $projects
                CARPINOVA_NATIVE_APPROVAL_DIR = $approvals
            }
        }
    }
} | ConvertTo-Json -Depth 8
$utf8 = New-Object System.Text.UTF8Encoding($false)
$codexFile = Join-Path $config "codex-config.toml.example"
$antigravityFile = Join-Path $config "antigravity-mcp.json.example"
[System.IO.File]::WriteAllText($codexFile, $codex, $utf8)
[System.IO.File]::WriteAllText($antigravityFile, $antigravity, $utf8)
# Verify both client examples are PARSEABLE, exact-path configurations.
$verify = "import json,pathlib,sys,tomllib; c=tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8')); a=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8')); x=c['mcp_servers']['carpinova']; y=a['mcpServers']['carpinova']; assert x['command']==y['command']==sys.argv[3]; assert x['env']['PYTHONPATH']==y['env']['PYTHONPATH']==sys.argv[4]; assert x['env']['CARPINOVA_OUTPUT_ROOT']==y['env']['CARPINOVA_OUTPUT_ROOT']==sys.argv[5]; assert x['env']['CARPINOVA_NATIVE_APPROVAL_DIR']==y['env']['CARPINOVA_NATIVE_APPROVAL_DIR']==sys.argv[6]; assert x['args']==y['args']==['-m','carpinova_agent.mcp_bridge']; assert 'CARPINOVA_NATIVE_EXECUTION_ENABLED' not in x['env'] and 'CARPINOVA_NATIVE_EXECUTION_ENABLED' not in y['env']"
& $python -c $verify $codexFile $antigravityFile $python $repo $projects $approvals
if ($LASTEXITCODE -ne 0) { throw "Una configuración MCP generada es inválida." }

# Integration smoke: use the REAL Windows-generated TOML to exercise the same
# Codex installer, but only under this disposable CI/preflight output folder.
# Never write to ~/.codex or ~/.agents here.
$installer = Join-Path $repo "scripts\install_codex_skills.py"
$codexSmoke = @'
import importlib.util
from pathlib import Path
import sys
import tomllib

installer = Path(sys.argv[1]).resolve(strict=True)
repo = Path(sys.argv[2]).resolve(strict=True)
out = Path(sys.argv[3]).resolve(strict=True)
spec = importlib.util.spec_from_file_location("carpinova_codex_installer", installer)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

isolated = out / "codex-install-smoke"
isolated.mkdir()
skills_dir = isolated / "skills"
installed = module.install(repo, skills_dir)
assert len(installed) == 4
assert set(installed.values()) == {"INSTALLED"}
again = module.install(repo, skills_dir)
assert set(again.values()) == {"ALREADY_IDENTICAL"}

config = isolated / "codex-config.toml"
config.write_text(
    'model = "example-no-user-change"\n'
    '[mcp_servers.other]\n'
    'url = "https://example.invalid/mcp"\n',
    encoding="utf-8",
)
baseline = config.read_bytes()
assert module.configure_mcp(repo, config, write=False) == "READY_TO_CONFIGURE"
assert config.read_bytes() == baseline
assert module.configure_mcp(repo, config) == "CONFIGURED"
result = tomllib.loads(config.read_text(encoding="utf-8"))
source = repo / "work" / "configuracion-local" / "codex-config.toml.example"
expected = tomllib.loads(source.read_text(encoding="utf-8"))
assert result["model"] == "example-no-user-change"
assert result["mcp_servers"]["other"]["url"] == "https://example.invalid/mcp"
assert result["mcp_servers"]["carpinova"] == expected["mcp_servers"]["carpinova"]
assert "CARPINOVA_NATIVE_EXECUTION_ENABLED" not in result["mcp_servers"]["carpinova"]["env"]
snapshot = config.read_bytes()
assert module.configure_mcp(repo, config) == "ALREADY_CONFIGURED"
assert config.read_bytes() == snapshot
print("CODEX_REAL_WINDOWS_CONFIG_SMOKE=PASS; FOUR_SKILLS=PASS; MCP=PASS; USER_HOME_UNTOUCHED=YES")
'@
# PowerShell on Windows re-quotes arguments sent to native executables.
# A disposable .py file preserves source quotes without changes to user HOME.
$codexSmokeScript = Join-Path $OutputRoot "codex-install-smoke-runner.py"
[System.IO.File]::WriteAllText($codexSmokeScript, $codexSmoke, $utf8)
& $python $codexSmokeScript $installer $repo $OutputRoot
if ($LASTEXITCODE -ne 0) { throw "Instalador Codex con TOML Windows real falló." }
# Preserve the actual resolved dependency graph as local rebuild evidence.
$packages = @(& $python -m pip freeze)
if ($LASTEXITCODE -ne 0) { throw "No se pudieron registrar versiones instaladas." }
[System.IO.File]::WriteAllLines((Join-Path $OutputRoot "resolved-packages-windows.txt"), [string[]]$packages, $utf8)
Write-Host "MCP_CLIENT_CONFIGS=PASS; TWO_FORMATS=PASS; HOST_APPROVAL_DIR=CONFIGURED; NATIVE_EXECUTION=DISABLED"
Write-Host "CARPINOVA_WINDOWS_PREFLIGHT=PASS; SIX_TOOLS=PASS; FABRICATION_AUTHORITY=NO"
Write-Host "Evidence: $reportPath"
Write-Host "Review IDE config examples: $config"
Write-Host "Host approval directory (protect from agent writes): $approvals"
Write-Host "OWNER_IDE_SESSION=NOT_CERTIFIED; WINDOWS_NATIVE_CAD=NOT_CERTIFIED"
