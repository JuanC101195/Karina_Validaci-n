"""
Cliente de OpenCorp: login y consultas AJAX de informes.

Recortado del scraper de Empresa_no_pago (2026-10-14): esta app solo usa
login() y fetch_ajax_report(); el resto de funciones de No Pagos se quitaron.
"""

import json
import os
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import requests

ENDPOINT_NOTIFICACIONES = "/rastreoya/vistas/modulo/ajax/buscarNotificacion.php"
RUTA_LOGIN = "/rastreoya/ingreso"


class OpenCorpScraperError(Exception):
    """Error del cliente de OpenCorp."""


class OpenCorpScraper:
    def __init__(self, base_url=None, timeout=30):
        """
        :param base_url: URL base de la sucursal. Si no se da, se lee de
            la variable de entorno OPENCORP_BASE_URL.
        :param timeout: segundos maximos de espera por solicitud HTTP.
        """
        env_url = os.environ.get("OPENCORP_BASE_URL", "").strip()
        self.base_url = (base_url or env_url).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
        })
        self.is_authenticated = False

    @staticmethod
    def _extract_form_inputs(soup):
        """Inputs del formulario (incluye tokens CSRF ocultos) y su action."""
        form = soup.find("form")
        if not form:
            return {}, None
        inputs = {inp.get("name"): inp.get("value", "") for inp in form.find_all("input") if inp.get("name")}
        return inputs, form.get("action")

    @staticmethod
    def _campos_login(soup):
        """Nombre de los campos de correo y contrasena del formulario."""
        email_field = password_field = None
        for inp in soup.find_all("input"):
            tipo = inp.get("type", "").lower()
            nombre = inp.get("name", "")
            placeholder = inp.get("placeholder", "").lower()
            clave = nombre or inp.get("id", "")
            es_email = tipo in ("email", "text") or "correo" in placeholder or any(k in nombre.lower() for k in ("email", "user"))
            es_pass = tipo == "password" or "contraseña" in placeholder or "pass" in nombre.lower()
            if not email_field and es_email:
                email_field = clave or "email"
            elif not password_field and es_pass:
                password_field = clave or "password"
        return email_field or "email", password_field or "password"

    @staticmethod
    def _es_pagina_login(texto):
        return "Iniciar sesión" in texto or "Correo electrónico" in texto or "password" in texto.lower()

    def login(self, email, password, target_url=None):
        """Inicia sesion en OpenCorp. Lanza OpenCorpScraperError si falla."""
        start_url = target_url or (f"{self.base_url}/" if self.base_url else None)
        if not start_url:
            raise OpenCorpScraperError("Debe especificar base_url o target_url para iniciar sesión.")

        resp = self.session.get(start_url, timeout=self.timeout)
        resp.raise_for_status()
        if not self.base_url:
            parsed = urlparse(resp.url)
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"

        if not self._es_pagina_login(resp.text):
            self.is_authenticated = True
            return True

        soup = BeautifulSoup(resp.text, "html.parser")
        email_field, password_field = self._campos_login(soup)
        payload, action = self._extract_form_inputs(soup)
        payload[email_field] = email
        payload[password_field] = password
        login_post_url = urljoin(resp.url, action or RUTA_LOGIN)

        login_resp = self.session.post(login_post_url, data=payload, timeout=self.timeout)
        login_resp.raise_for_status()
        if "Iniciar sesión" in login_resp.text and "Introduce tu correo" in login_resp.text:
            raise OpenCorpScraperError("Error de autenticación: Usuario o contraseña incorrectos.")
        self.is_authenticated = True
        return True

    def fetch_ajax_report(self, endpoint_path=ENDPOINT_NOTIFICACIONES, payload_key="LoadCajaBalance", payload_data=None):
        """POST AJAX generico: {payload_key: json(payload_data)} -> dict/list."""
        if not self.is_authenticated:
            raise OpenCorpScraperError("Debe iniciar sesión primero llamando a login()")
        if not self.base_url:
            raise OpenCorpScraperError("URL base de sucursal no configurada.")

        ajax_url = f"{self.base_url}/{endpoint_path.lstrip('/')}"
        try:
            resp = self.session.post(ajax_url, data={payload_key: json.dumps(payload_data or {})}, timeout=self.timeout)
            resp.raise_for_status()
            # Algunas sedes devuelven el JSON con BOM UTF-8 y saltos de linea
            # sueltos (heredado de Empresa_no_pago): se limpia antes de parsear.
            data = json.loads(resp.content.decode("utf-8-sig").strip())
            if isinstance(data, str):
                data = json.loads(data)
        except requests.RequestException as e:
            raise OpenCorpScraperError(f"Error de conexión con la API ({ajax_url}): {e}") from e
        except json.JSONDecodeError as e:
            raise OpenCorpScraperError(f"No se pudo decodificar la respuesta JSON ({ajax_url}): {e}") from e

        if isinstance(data, dict) and data.get("validacion") not in (None, "ok", "sin"):
            raise OpenCorpScraperError(f"Error en respuesta de la plataforma: {data.get('mensaje', data.get('validacion'))}")
        if isinstance(data, (dict, list)):
            return data
        raise OpenCorpScraperError(f"Respuesta inesperada de la plataforma: {data!r}")
