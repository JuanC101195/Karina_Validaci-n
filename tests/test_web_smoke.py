import pytest

import web_app
from karina.opencorp_scraper import OpenCorpScraperError


@pytest.fixture
def cliente(monkeypatch):
    web_app.app.config["WTF_CSRF_ENABLED"] = False
    web_app.SCRAPERS.clear()
    return web_app.app.test_client()


def test_sin_login_redirige(cliente):
    assert cliente.get("/").status_code == 302
    assert cliente.post("/api/validar").status_code == 401


def test_login_invalido_muestra_error(cliente, monkeypatch):
    def falla(email, password):
        raise OpenCorpScraperError("Usuario o contraseña incorrectos.")
    monkeypatch.setattr(web_app.validador, "conectar", falla)
    r = cliente.post("/login", data={"usuario": "a@b.co", "password": "x"})
    assert r.status_code == 200
    assert 'incorrectos' in r.get_data(as_text=True)


def test_login_valido_y_validar_sin_archivos(cliente, monkeypatch):
    monkeypatch.setattr(web_app.validador, "conectar", lambda e, p: object())
    assert cliente.post("/login", data={"usuario": "a@b.co", "password": "x"}).status_code == 302
    assert cliente.get("/").status_code == 200
    r = cliente.post("/api/validar", data={"desde": "2026-10-13"})
    assert r.status_code == 400
    assert 'dos archivos' in r.get_json()['error']


def test_alquiler_comite_con_token_ajeno(cliente, monkeypatch):
    monkeypatch.setattr(web_app.validador, "conectar", lambda e, p: object())
    cliente.post("/login", data={"usuario": "a@b.co", "password": "x"})
    r = cliente.post("/api/alquiler-comite/otro", json={"respuestas": {}})
    assert r.status_code == 404
