# Seguridad, datos y cumplimiento

## Secretos
- Nunca en git. `.env` está en `.gitignore`; solo se versiona `.env.example`.
- En producción: gestor de secretos (Doppler / cloud secrets manager), separación
  dev/staging/prod, rotación de claves. Nunca claves compartidas entre tenants.
- **Nunca `LOG_LEVEL=DEBUG` en producción:** los SDKs de LLM podrían registrar cabeceras
  con la API key.

> Los controles diferidos a la Ruta 🅱️ (autenticación, rate limiting, aislamiento de
> tenant en BD, etc.) están listados y rastreados en [`DEUDA_TECNICA.md`](DEUDA_TECNICA.md).

## Datos personales (Habeas Data — Ley 1581/2012, Colombia)
Es **lo primero** de la due diligence local. Antes de capturar números de WhatsApp o
datos de parcela:
- Aviso de privacidad + texto de autorización de tratamiento en el opt-in.
- Registro de bases de datos ante la **SIC**.
- Finalidad limitada, canal para ejercer derechos del titular.
- Revisión por abogado colombiano (y europeo para la fase ES/UE).

## Soberanía de datos del productor (diferenciador contractual)
- No se venden ni ceden datos de parcela.
- Aislamiento por tenant (verificado con tests de tenancy en CI — Ruta 🅱️).
- Exportación/borrado certificado al terminar el contrato (offboarding).

## Multi-tenant
La columna `tenant` existe en todas las tablas desde el día 1. En la Ruta 🅱️ se añaden
tests automatizados que prueban que un tenant no puede leer datos de otro.

## Responsabilidad del consejo agronómico
- Posicionamiento: **herramienta de apoyo, NO sustituye al ingeniero agrónomo**.
- Categoría toxicológica I/II → semáforo 🔴 → revisión y firma de profesional (HITL).
- La firma humana es **una capa**, no un escudo único: bajo la Directiva UE 2024/2853 la
  responsabilidad puede recaer en el fabricante. Combinar: trazabilidad a fuente,
  disclaimers en capas, consentimiento, límite de responsabilidad contractual y seguro
  de RC tecnológica. **Validar con abogado.**

## Prompt injection / abuso (Ruta 🅱️)
Sanitización del input del usuario, rate limiting por número/tenant, y el LLM-judge +
geofiltro como segunda barrera.
