"""Subsistemas del MODO ONLINE de AvoRAG (ver docs/ARQUITECTURA_ONLINE.md).

Espacio de nombres reservado para el código que SOLO aplica al modo online (feeds en vivo,
capabilities, HITL, orquestación de modelo fuerte + juez independiente). Se mantiene separado del
núcleo compartido (agro_calc/guardrails/pipeline/models/config/schemas) para no colisionar con el
trabajo paralelo del modo offline en el mismo repositorio.
"""
