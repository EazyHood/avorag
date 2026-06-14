# Runbook operativo

## Puesta en marcha (local, gratis)
```powershell
uv sync
ollama pull bge-m3
ollama pull qwen2.5:7b-instruct
Copy-Item .env.example .env        # ajustar DATABASE_URL
uv run avorag db upgrade
uv run avorag ingest data/corpus/<archivo>.pdf --fuente "<Nombre>"
uv run avorag serve
```

## Base de datos
- **Neon/Supabase (recomendado):** crea proyecto, copia el connection string a
  `DATABASE_URL` (formato `postgresql+psycopg://...`). pgvector viene disponible.
- **Docker local:** `docker compose up -d db` (usa el `docker-compose.yml`).
- Migraciones: `uv run avorag db upgrade` / `db downgrade` / `db current`.

## Actualización del corpus (blue-green)
1. Ingerir/actualizar documentos en un índice nuevo (o tenant de staging).
2. Correr el golden set: `uv run avorag eval data/golden/golden_set.example.jsonl`.
3. Si el gate **pasa**, promover; si **falla**, no promover (rollback inmediato).
4. Registrar `corpus_version`.

## Vigencia de registros ICA (tarea recurrente — asignada y costeada)
Los registros/etiquetas ICA caducan. Mensual/trimestral: revisar y marcar chunks
caducados (`meta.vigencia = "caducado"`) para que el geofiltro los excluya del retrieval.

## Incidentes
- **El bot responde mal/peligroso:** revisar `queries` (audit trail), identificar el
  chunk/fuente, corregir corpus, re-evaluar golden set antes de promover.
- **Dosis inventada reportada:** confirmar con `doses_grounded`; si el guardarraíl falló,
  añadir caso al golden set (subconjunto de dosis) como regresión.
- **Provider caído (Ollama/Claude):** reintentos con backoff ya integrados; si persiste,
  cambiar `LLM_PROVIDER` de respaldo en `.env` y reiniciar.

## Backups (Ruta 🅱️)
Postgres gestionado con PITR y réplica. Probar la **restauración** periódicamente
(un backup no probado no es un backup). Definir RPO/RTO antes de prometer SLA.
