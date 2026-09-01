# PowerShell mirror of the Makefile, because `make` is not installed on the
# Windows development machine. Same target names — keep the two in step.
#
#     .\make.ps1 install
#     .\make.ps1 test
#     .\make.ps1 revision -M "add user table"

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'install', 'run', 'test', 'lint', 'fmt', 'migrate', 'revision', 'seed-faculty', 'seed')]
    [string]$Target = 'help',

    [string]$M
)

$ErrorActionPreference = 'Stop'

# Prefer the project venv when it exists, so a target never silently runs
# against the crowded global interpreter.
$venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$py = if (Test-Path $venvPython) { $venvPython } else { 'python' }

function Invoke-Py {
    param([string[]]$Arguments)
    & $py @Arguments
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

switch ($Target) {
    'help' {
        'install   - install requirements.txt'
        'run       - start the Streamlit app'
        'test      - run pytest'
        'lint      - ruff check'
        'fmt       - ruff format + fix imports'
        'migrate   - alembic upgrade head'
        'revision  - alembic autogenerate, -M "message"'
        'seed-faculty - seed the faculty allow-list into users'
        'seed      - demo dataset (arrives in Phase 7)'
        ''
        "interpreter: $py"
    }
    'install'  { Invoke-Py @('-m', 'pip', 'install', '-r', 'requirements.txt') }
    'run'      { Invoke-Py @('-m', 'streamlit', 'run', 'app/main.py') }
    'test'     { Invoke-Py @('-m', 'pytest') }
    'lint'     { Invoke-Py @('-m', 'ruff', 'check', 'core', 'app', 'tests', 'alembic', 'scripts') }
    'fmt' {
        Invoke-Py @('-m', 'ruff', 'check', '--fix', 'core', 'app', 'tests', 'alembic', 'scripts')
        Invoke-Py @('-m', 'ruff', 'format', 'core', 'app', 'tests', 'alembic', 'scripts')
    }
    'migrate'  { Invoke-Py @('-m', 'alembic', 'upgrade', 'head') }
    'revision' {
        if ([string]::IsNullOrWhiteSpace($M)) {
            Write-Error 'Usage: .\make.ps1 revision -M "what changed"'
        }
        Invoke-Py @('-m', 'alembic', 'revision', '--autogenerate', '-m', $M)
    }
    'seed-faculty' { Invoke-Py @('scripts/seed_faculty.py') }
    'seed'     { 'scripts/seed_demo.py arrives in Phase 7 (see CLAUDE.md section 10).' }
}
