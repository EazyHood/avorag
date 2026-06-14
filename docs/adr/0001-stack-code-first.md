# ADR 0001 — Stack code-first (no Dify hospedado)

**Estado:** aceptado · **Fecha:** 2026-06-14

## Contexto
El negocio (Ruta 🅱️) es un SaaS multi-tenant white-label. Dify, pese a ser open-source,
restringe revenderlo como servicio hospedado, lo que generaría deuda de reescritura.

## Decisión
Orquestación **code-first** con Python (FastAPI + SQLAlchemy + pgvector). Dify/Flowise
solo como prototipo desechable interno, nunca como base de producción.

## Consecuencias
- (+) Control total, sin bloqueo de licencia, demostrable como código en el portafolio.
- (+) Mismo motor sirve a web hoy y a WhatsApp después.
- (−) Más código que una herramienta low-code (mitigado: el scaffold ya está hecho).
