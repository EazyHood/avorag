# Atajos de desarrollo para Windows/PowerShell. Uso: .\scripts\dev.ps1 <tarea>
param([Parameter(Position = 0)][string]$Task = "help")

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

switch ($Task) {
    "setup"   { uv sync; uv run pre-commit install }
    "up"      { docker compose up -d db }
    "lint"    { uv run ruff check src tests; uv run ruff format --check src tests }
    "fmt"     { uv run ruff check --fix src tests; uv run ruff format src tests }
    "test"    { uv run pytest }
    "migrate" { uv run avorag db upgrade }
    "serve"   { uv run avorag serve --reload }
    "eval"    { uv run avorag eval data/golden/golden_set.example.jsonl }
    default   {
        Write-Host "Tareas: setup | up | lint | fmt | test | migrate | serve | eval"
    }
}
