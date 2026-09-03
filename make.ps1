# PowerShell mirror of the Makefile, because `make` is not installed on the
# Windows development machine. Same target names — keep the two in step.
#
#     .\make.ps1 install
#     .\make.ps1 test
#     .\make.ps1 revision -M "add user table"

param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'install', 'run', 'test', 'test-report', 'lint', 'fmt', 'migrate', 'revision', 'seed-faculty', 'seed', 'reseed')]
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
        'test-report - write docs/test-report.txt, an SDLC artifact'
        'lint      - ruff check'
        'fmt       - ruff format + fix imports'
        'migrate   - alembic upgrade head'
        'revision  - alembic autogenerate, -M "message"'
        'seed-faculty - seed the faculty allow-list into users'
        'seed      - build the demo dataset'
        'reseed    - wipe and rebuild the demo dataset'
        ''
        "interpreter: $py"
    }
    'install'  { Invoke-Py @('-m', 'pip', 'install', '-r', 'requirements.txt') }
    'run'      { Invoke-Py @('-m', 'streamlit', 'run', 'app/main.py') }
    'test'     { Invoke-Py @('-m', 'pytest') }
    'test-report' {
        # The verbose run is checked in, because "the tests pass" is a claim
        # and docs/test-report.txt is the evidence for it.
        & $py -m pytest -o addopts="--strict-markers" -v --tb=short |
            Out-File -FilePath 'docs/test-report.txt' -Encoding utf8
    }
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
    'seed'     { Invoke-Py @('scripts/seed_demo.py') }
    'reseed'   { Invoke-Py @('scripts/seed_demo.py', '--reset') }
}
