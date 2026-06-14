# Atajos (opcional). Instala `just` o usa los comandos `uv run ...` directos del README.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

default:
    @just --list

setup:
    uv sync
    uv run pre-commit install

up:
    docker compose up -d db

lint:
    uv run ruff check src tests
    uv run ruff format --check src tests

fmt:
    uv run ruff check --fix src tests
    uv run ruff format src tests

test:
    uv run pytest

migrate:
    uv run avorag db upgrade

serve:
    uv run avorag serve --reload

eval:
    uv run avorag eval data/golden/golden_set.example.jsonl
