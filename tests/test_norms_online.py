"""Normas versionadas: fallback al default, lectura de BD por scope, y seed idempotente."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from avorag.online import norms


class _FakeSession:
    def __init__(self, *, scalar=None, scalars=None):
        self._scalar = scalar
        self._scalars = scalars or []
        self.added: list = []

    def scalar(self, _stmt):
        return self._scalar

    def scalars(self, _stmt):
        return self._scalars

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        pass


def test_defaults_bien_formados():
    keys = {d["norm_key"] for d in norms.DEFAULT_NORMS}
    assert {"foliar_suficiencia", "ms_objetivo", "ce_umbral_portainjerto", "gdd_t_base", "encalado"} <= keys
    for d in norms.DEFAULT_NORMS:
        assert d["norm_version"] and isinstance(d["params"], dict)


def test_get_norm_fallback_al_default_si_no_hay_db():
    # session None ⇒ no consulta BD ⇒ default.
    n = norms.get_norm(None, "ms_objetivo")
    assert n["source"] == "default" and n["params"]["exportacion"] == 23.0


def test_get_norm_fallback_si_db_vacia():
    n = norms.get_norm(_FakeSession(scalars=[]), "gdd_t_base")
    assert n["source"] == "default" and n["params"]["t_base"] == 10.0


def test_get_norm_lee_de_db_si_hay_fila():
    fila = SimpleNamespace(
        norm_key="gdd_t_base", norm_version="2026-09-01", scope={"cultivo": "hass"},
        params={"t_base": 9.0}, fuente="calibrada Antioquia", vigente=True,
    )
    n = norms.get_norm(_FakeSession(scalars=[fila]), "gdd_t_base", scope={"cultivo": "hass"})
    assert n["source"] == "db" and n["params"]["t_base"] == 9.0 and n["norm_version"] == "2026-09-01"


def test_get_norm_desconocida_lanza_keyerror():
    with pytest.raises(KeyError):
        norms.get_norm(None, "no_existe")


def test_seed_inserta_todas_si_vacio():
    s = _FakeSession(scalar=None)
    n = norms.seed_norms(s)
    assert n == len(norms.DEFAULT_NORMS) and len(s.added) == n


def test_seed_idempotente_si_ya_existen():
    s = _FakeSession(scalar=object())  # todas existen
    assert norms.seed_norms(s) == 0 and s.added == []
