"""CLI de AvoRAG. Punto de entrada: `uv run avorag <comando>`."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from avorag.logging import configure_logging

app = typer.Typer(add_completion=False, help="AvoRAG — Asesor Hass (RAG agronómico).")
db_app = typer.Typer(help="Migraciones de base de datos.")
app.add_typer(db_app, name="db")
console = Console()

ROOT = Path(__file__).resolve().parents[3]


def _alembic_config():
    from alembic.config import Config

    ini = ROOT / "alembic.ini"
    migrations = ROOT / "migrations"
    if not ini.exists() or not migrations.exists():
        raise FileNotFoundError(
            f"No encuentro alembic.ini o migrations/ en {ROOT}. "
            "Ejecuta los comandos desde la raíz del repo."
        )
    cfg = Config(str(ini))
    cfg.set_main_option("script_location", str(migrations))
    return cfg


@db_app.command("upgrade")
def db_upgrade(revision: str = "head") -> None:
    """Aplica migraciones (crea extensión pgvector, tablas e índices)."""
    from alembic import command

    configure_logging()
    command.upgrade(_alembic_config(), revision)
    console.print("[green]✓ Base de datos al día[/green]")


@db_app.command("downgrade")
def db_downgrade(revision: str = "-1") -> None:
    """Revierte migraciones."""
    from alembic import command

    command.downgrade(_alembic_config(), revision)
    console.print(f"[yellow]Revertido a {revision}[/yellow]")


@db_app.command("current")
def db_current() -> None:
    """Muestra la revisión actual."""
    from alembic import command

    command.current(_alembic_config(), verbose=True)


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="Ruta al PDF/TXT/MD del corpus."),
    fuente: str = typer.Option(..., "--fuente", help="Nombre oficial citable de la fuente."),
    licencia: str = typer.Option("por-verificar", "--licencia"),
    autoridad: str = typer.Option("oficial-regulador", "--autoridad"),
    pais: str = typer.Option("CO", "--pais", help="País del documento (CO, ES)."),
    cultivo: str = typer.Option("hass", "--cultivo", help="Cultivo del documento."),
    fecha: str | None = typer.Option(None, "--fecha", help="Fecha de publicación."),
    url: str | None = typer.Option(None, "--url", help="Enlace de descarga directa de la fuente."),
    doi: str | None = typer.Option(None, "--doi", help="DOI de la fuente (si tiene)."),
    tenant: str | None = typer.Option(None, "--tenant"),
    contextual: bool = typer.Option(True, "--contextual/--no-contextual"),
    force: bool = typer.Option(False, "--force", help="Re-ingerir aunque ya exista."),
) -> None:
    """Ingesta y vectoriza un documento del corpus."""
    from avorag.ingestion import DocumentMeta, ingest_document

    configure_logging()
    meta = DocumentMeta(
        fuente=fuente,
        licencia=licencia,
        nivel_autoridad=autoridad,
        pais=pais.upper(),
        cultivo=cultivo.lower(),
        fecha_publicacion=fecha,
        url=url,
        doi=doi,
    )
    with console.status(f"Ingiriendo {path.name}…"):
        res = ingest_document(path, meta, tenant=tenant, contextual=contextual, force=force)
    if res.skipped:
        console.print(f"[yellow]Omitido:[/yellow] {res.reason}")
    else:
        msg = f"[green]✓ {res.n_chunks} chunks ingeridos[/green] de «{res.fuente}»"
        if res.contextual_failures:
            msg += f" [yellow](contexto falló en {res.contextual_failures})[/yellow]"
        console.print(msg)


@app.command()
def ask(
    question: str = typer.Argument(..., help="Pregunta agronómica."),
    tenant: str | None = typer.Option(None, "--tenant"),
    country: str | None = typer.Option(None, "--country"),
    soil: str | None = typer.Option(None, "--soil", help="Tipo de suelo (arenoso, arcilloso…)."),
    region: str | None = typer.Option(None, "--region", help="Región/zona de la finca."),
) -> None:
    """Pregunta por consola (respuesta citada)."""
    from avorag.rag import answer

    configure_logging()
    ans = answer(question, tenant=tenant, country=country, soil_type=soil, region=region)
    color = {"verde": "green", "amarillo": "yellow", "rojo": "red"}.get(ans.semaforo.value, "white")
    body = ans.text
    if ans.citations:
        body += "\n\n[bold]Fuentes:[/bold]"
        for i, c in enumerate(ans.citations, start=1):
            pag = f", p.{c.pagina}" if c.pagina else ""
            link = c.doi and f"  doi:{c.doi}" or (c.url and f"  {c.url}") or ""
            body += f"\n  [{i}] {c.fuente}{pag}{link}"
    body += f"\n\n[dim]{ans.disclaimer}[/dim]"
    console.print(
        Panel(body, title=f"[{color}]{ans.semaforo.value.upper()}[/{color}]", border_style=color)
    )
    fa = f" · fidelidad {ans.faithfulness:.2f}" if ans.faithfulness is not None else ""
    console.print(f"[dim]{ans.latency_ms} ms{fa} · {ans.reason or ''}[/dim]")


@app.command()
def serve(
    host: str | None = typer.Option(None, "--host"),
    port: int | None = typer.Option(None, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Levanta la API + UI web."""
    import uvicorn

    from avorag.config import get_settings

    s = get_settings()
    uvicorn.run(
        "avorag.api.app:app",
        host=host or s.api_host,
        port=port or s.api_port,
        reload=reload,
    )


@app.command()
def eval(  # noqa: A001 (nombre del comando, intencional)
    golden: Path = typer.Argument(..., help="Ruta al golden set JSONL."),
    tenant: str | None = typer.Option(None, "--tenant"),
) -> None:
    """Corre el golden set y reporta métricas (gate de calidad)."""
    from avorag.eval import run_eval

    configure_logging()
    _, passed = run_eval(golden, tenant=tenant)
    raise typer.Exit(code=0 if passed else 1)


if __name__ == "__main__":
    app()
