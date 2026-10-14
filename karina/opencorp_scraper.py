"""
Módulo de scraping e interacción modular con plataformas web de sucursal (OpenCorp).

Maneja la autenticación automatizada, navegación a endpoints de reportes por sucursal,
y extracción genérica de datos estructurados en JSON de múltiples sub-URLs e informes.
"""

import json
import os
import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import requests


class OpenCorpScraperError(Exception):
    """Excepción base para errores del scraper de la plataforma de sucursal."""
    pass


class OpenCorpScraper:
    def __init__(self, base_url=None, timeout=30):
        """
        Cliente scraper modular para la plataforma de gestión de sucursal.

        :param base_url: URL base de la sucursal (ej. 'https://<sucursal_domain>').
                         Si no se especifica, se lee de la variable de entorno OPENCORP_BASE_URL.
        :param timeout: Tiempo máximo de espera en segundos para solicitudes HTTP.
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

    def _extract_form_inputs(self, soup, form_selector=None):
        """Extrae inputs de un formulario HTML (incluyendo CSRF tokens ocultos)."""
        form = soup.select_one(form_selector) if form_selector else soup.find("form")
        if not form:
            return {}, None

        action = form.get("action")
        inputs = {}
        for inp in form.find_all("input"):
            name = inp.get("name")
            if name:
                inputs[name] = inp.get("value", "")
        return inputs, action

    def login(self, email, password, target_url=None):
        """
        Inicia sesión en la plataforma web de la sucursal.
        """
        start_url = target_url or (f"{self.base_url}/" if self.base_url else None)
        if not start_url:
            raise OpenCorpScraperError("Debe especificar base_url al instanciar OpenCorpScraper o target_url en login().")

        print(f"[*] Accediendo a la plataforma: {start_url}")

        resp = self.session.get(start_url, timeout=self.timeout)
        resp.raise_for_status()

        # Si no teníamos base_url, extraer del origen de la respuesta
        if not self.base_url:
            parsed = urlparse(resp.url)
            self.base_url = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")

        soup = BeautifulSoup(resp.text, "html.parser")

        # Detectar si estamos en la pantalla de login
        is_login_page = ("Iniciar sesión" in resp.text or "Correo electrónico" in resp.text or "password" in resp.text.lower())

        if not is_login_page:
            print("[+] Sesión ya activa o no requiere login.")
            self.is_authenticated = True
            return True

        print("[*] Formulario de login detectado. Preparando autenticación...")

        # Buscar inputs de correo y contraseña
        email_field = None
        password_field = None

        for inp in soup.find_all("input"):
            input_type = inp.get("type", "").lower()
            input_name = inp.get("name", "")
            input_id = inp.get("id", "")
            placeholder = inp.get("placeholder", "").lower()

            if not email_field and (input_type in ["email", "text"] or "correo" in placeholder or "email" in input_name.lower() or "user" in input_name.lower()):
                email_field = input_name or input_id or "email"
            elif not password_field and (input_type == "password" or "contraseña" in placeholder or "pass" in input_name.lower()):
                password_field = input_name or input_id or "password"

        email_field = email_field or "email"
        password_field = password_field or "password"

        form_payload, form_action = self._extract_form_inputs(soup)
        form_payload[email_field] = email
        form_payload[password_field] = password

        # Determinar URL de POST de login
        if form_action:
            login_post_url = urljoin(resp.url, form_action)
        else:
            login_post_url = urljoin(resp.url, "/rastreoya/ingreso")

        print(f"[*] Enviando credenciales a: {login_post_url}")
        login_resp = self.session.post(login_post_url, data=form_payload, timeout=self.timeout)
        login_resp.raise_for_status()

        if "Iniciar sesión" in login_resp.text and "Introduce tu correo" in login_resp.text:
            raise OpenCorpScraperError("Error de autenticación: Usuario o contraseña incorrectos.")

        print("[+] Autenticación exitosa en la plataforma.")
        self.is_authenticated = True
        return True

    def _format_date_yyyy_mm_dd(self, date_str):
        """Convierte fechas DD/MM/YYYY a YYYY-MM-DD si es necesario."""
        if not date_str:
            return ""
        date_str = date_str.strip()
        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str
        match = re.match(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$", date_str)
        if match:
            day, month, year = match.groups()
            return f"{year}-{int(month):02d}-{int(day):02d}"
        return date_str

    def fetch_ajax_report(self, endpoint_path="/rastreoya/vistas/modulo/ajax/buscarNotificacion.php", payload_key="LoadCajaBalance", payload_data=None):
        """
        Consulta genérica a endpoints AJAX del sistema para cualquier reporte o sub-URL.

        :param endpoint_path: Ruta relativa del script AJAX de backend.
        :param payload_key: Clave del POST AJAX (ej. 'LoadCajaBalance', 'LoadNoPagos', etc.).
        :param payload_data: Diccionario con los parámetros de consulta (fecha, sucursal, etc.).
        """
        if not self.is_authenticated:
            raise OpenCorpScraperError("Debe iniciar sesión primero llamando a login()")

        if not self.base_url:
            raise OpenCorpScraperError("URL base de sucursal no configurada. Especifique base_url al instanciar el scraper.")

        ajax_url = f"{self.base_url}/{endpoint_path.lstrip('/')}"
        print(f"[*] Consultando API AJAX ({payload_key}) en: {ajax_url}...")

        try:
            resp = self.session.post(
                ajax_url,
                data={payload_key: json.dumps(payload_data or {})},
                timeout=self.timeout
            )
            resp.raise_for_status()

            # Algunas sedes (ej. Monteria) devuelven el JSON precedido de un
            # BOM UTF-8 y saltos de linea sueltos -- resp.json() truena en
            # ese caso (JSONDecodeError: Unexpected UTF-8 BOM). Se decodifica
            # manualmente con utf-8-sig (descarta el BOM si existe) y se
            # recorta espacios/saltos de linea antes de parsear.
            texto = resp.content.decode("utf-8-sig").strip()
            data = json.loads(texto)
            if isinstance(data, str):
                data = json.loads(data)

            if isinstance(data, dict) and data.get("validacion") in ["ok", "sin"]:
                print(f"[+] Reporte obtenido exitosamente (Validación: {data.get('validacion')}).")
                return data
            elif isinstance(data, (dict, list)):
                return data
            else:
                msg = data.get("mensaje", "Error retornado por la plataforma") if isinstance(data, dict) else str(data)
                raise OpenCorpScraperError(f"Error en respuesta de la plataforma: {msg}")

        except requests.RequestException as e:
            raise OpenCorpScraperError(f"Error de conexión con la API ({ajax_url}): {e}")
        except json.JSONDecodeError as e:
            raise OpenCorpScraperError(f"No se pudo decodificar la respuesta JSON ({ajax_url}): {e}")

    def fetch_caja_balance_json(self, date_str, concesionario="MOTOHOY", empresa_prin="MOTOHOY"):
        """
        Consulta los datos del informe de Cierre e Inicio de Caja (Saldos / Arqueo).
        """
        fecha_formatted = self._format_date_yyyy_mm_dd(date_str)
        post_payload = {
            "CONCESIONARIO": concesionario,
            "empresa_prin": empresa_prin,
            "fecha": fecha_formatted
        }
        return self.fetch_ajax_report(
            endpoint_path="/rastreoya/vistas/modulo/ajax/buscarNotificacion.php",
            payload_key="LoadCajaBalance",
            payload_data=post_payload
        )

    def fetch_empresas_disponibles(self, target_url=None):
        """
        Detecta las empresas disponibles en el selector de la vista (ej. ['MOTOHOY', 'RENTAYA'] en Cartagena,
        o ['MONTERIA'] en Montería).
        """
        if not self.is_authenticated:
            raise OpenCorpScraperError("Debe iniciar sesión primero llamando a login()")

        url = target_url or f"{self.base_url}/rastreoya/recaudo?suburl=informe_clientes_estados"
        try:
            resp = self.session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            select_emp = soup.find("select", {"id": "empresa"}) or soup.find("select", {"name": "empresa"}) or soup.find("select", {"id": "empresa_prin"})
            if select_emp:
                empresas = [op.text.strip() for op in select_emp.find_all("option") if op.text.strip()]
                if empresas:
                    print(f"[+] Empresas detectadas en la sucursal: {empresas}")
                    return empresas
        except Exception as e:
            print(f"[!] No se pudo extraer la lista de empresas dinámicamente ({e}).")

        return ["MOTOHOY"]

    def fetch_estados_operatividad_json(self, empresas=None, concesionario="MOTOHOY"):
        """
        Consulta los estados de operatividad de los clientes (informe_clientes_estados).
        En sucursales con múltiples empresas (ej. Cartagena: MOTOHOY y RENTAYA), consulta todas las
        empresas detectadas y consolida la lista. En sucursales de 1 sola empresa (ej. Montería), realiza 1 sola consulta.

        Bug real corregido 2026-09-25 (reportado por el lider del proyecto,
        "en Cartagena son pocos los estados"): el payload real que manda el
        JS del sitio SIEMPRE fija `empresa_prin` al CONCESIONARIO PRINCIPAL
        de esa sede (en Cartagena, "MOTOHOY"), sin importar cual `empresa`
        se este consultando -- ver la funcion `LoadDataInfo` del HTML real
        de informe_clientes_estados (`let empresa_prin = "MOTOHOY";` esta
        hardcodeado en el handler de busqueda, PERO ese valor es el
        concesionario de Cartagena especificamente). El codigo mandaba
        `empresa_prin` igual a la empresa consultada, lo que hacia que la
        consulta de RENTAYA devolviera datos de MOTOHOY otra vez (703
        registros, TODOS etiquetados "MOTOHOY" en el JSON, RENTAYA nunca
        aparecia). Con el payload correcto, RENTAYA por si sola trae 1511
        registros reales -- mas del doble de MOTOHOY.

        Bug real corregido 2026-09-26 (reportado por el usuario, "no esta
        encontrando los estados de operatividad" en Monteria -- reproducido
        con credenciales reales, la API devolvia "sin" / 0 registros): el
        fix anterior dejo `empresa_prin` HARDCODEADO al texto literal
        "MOTOHOY" para TODAS las sedes, en vez de usar el parametro
        `concesionario` que la funcion ya recibe (y que
        fetch_estados_operatividad_service ya pasa correctamente, ej.
        "MONTERIA" para Monteria, ver nopago.config.CAJA3_SCRAPER) -- asi
        que cualquier sede que no fuera Cartagena mandaba un
        `empresa_prin` que no le corresponde y la API no encontraba nada.
        Ahora se usa `concesionario` (el que le corresponde a CADA sede),
        nunca el texto literal "MOTOHOY".
        """
        if not empresas:
            empresas = self.fetch_empresas_disponibles()

        registros_totales = []
        vistos = set()

        for emp in empresas:
            print(f"[*] Consultando estados de operatividad para la empresa: {emp}...")
            payload = {"empresa": emp, "empresa_prin": concesionario}
            res = self.fetch_ajax_report(
                endpoint_path="/rastreoya/vistas/modulo/ajax/buscarNotificacion.php",
                payload_key="LoadClienXEstado",
                payload_data=payload
            )

            items = res.get("data", []) if isinstance(res, dict) else (res if isinstance(res, list) else [])
            for it in items:
                if isinstance(it, dict):
                    cleaned_item = {k: v for k, v in it.items() if not k.isdigit()}
                    # empresa en la clave de dedup: contrato/placa NO son
                    # necesariamente unicos entre empresas distintas.
                    clave_unica = (cleaned_item.get("empresa"), cleaned_item.get("contrato"), cleaned_item.get("placa"))
                    if clave_unica not in vistos:
                        vistos.add(clave_unica)
                        registros_totales.append(cleaned_item)

        print(f"[+] Total de estados de operatividad recuperados y consolidados: {len(registros_totales)}")
        return {"validacion": "ok", "data": registros_totales}

    def export_estados_operatividad_excel(self, output_path="downloads/Estados_Operatividad.xlsx", empresas=None, concesionario="MOTOHOY"):
        """
        Extrae los estados de operatividad del sistema y los exporta directamente a un archivo Excel (.xlsx).
        """
        data = self.fetch_estados_operatividad_json(empresas=empresas, concesionario=concesionario)
        records = data.get("data", [])

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        try:
            import pandas as pd
            df = pd.DataFrame(records)
            df.to_excel(output_path, index=False)
            print(f"[+] {len(records)} registros exportados a Excel: {output_path}")
            return output_path
        except ImportError:
            json_out = output_path.replace(".xlsx", ".json")
            with open(json_out, "w", encoding="utf-8") as f:
                json.dump(records, f, ensure_ascii=False, indent=2)
            print(f"[!] pandas no instalado. Registros guardados en JSON: {json_out}")
            return json_out

    def fetch_memo_general_json(self, fecha):
        """
        Consulta el "Memo General" (informe_memo_motohoy, payload_key
        LoadRecaudoGeneralMemo) -- cuanto se recibio por efectivo,
        transferencia, multas y repuestos, y consolida la info de cobro,
        para una fecha exacta. Verificado 2026-09-25 contra el sitio real
        (bajando el HTML/JS de informe_memo_motohoy) y contra datos reales
        de Cartagena: a pesar del nombre de la URL ("motohoy"), el reporte
        YA viene consolidado -- una sola consulta trae filas con COBRO
        tanto de JP* como de RC* (los sub-sistemas de Cobro de Cartagena,
        JP/RC, no las empresas MOTOHOY/RENTAYA) -- NO hace falta repetir
        la consulta por empresa como si hace falta en
        fetch_estados_operatividad_json/fetch_nopagos_sistema_json.

        :param fecha: fecha exacta a consultar, formato "YYYY-MM-DD"
            (mismo formato que usa el campo #fecha del formulario real).

        Cada fila trae (nombres de campo reales, confirmados contra el
        JS del sitio -- nunca inventar nombres en ingles "logicos" como
        "cash"/"transfer", el sitio real usa espaniol abreviado):
        COBRO (dueño/ruta, ej. "JP", "RC3"), COBRO_AUX (igual a COBRO, se
        usa para agrupar), USUARIO_DIG, NOMBRE, empresa (ruta especifica,
        ej. "FAVIPAN"), abono (Efectivo), transf (Transferencia), multa
        (Multa), repuesto (Repuesto), repuesto_pron (Pronto repuesto),
        neto (Recaudado), pronto (Pronto saldo). Los totales derivados que
        se ven en pantalla (Cobro, Total repuesto, Total) NO vienen en el
        JSON -- se calculan como transf+abono+pronto,
        repuesto_pron+repuesto, y neto+pronto+repuesto_pron
        respectivamente (ver calcular_memo_general).

        Devuelve {"validacion": "ok"/"sin"/"error", "data": [...], ...}.
        """
        return self.fetch_ajax_report(
            endpoint_path="/rastreoya/vistas/modulo/ajax/buscarNotificacion.php",
            payload_key="LoadRecaudoGeneralMemo",
            payload_data={"fecha": fecha},
        )

    def fetch_nopagos_sistema_json(self, empresas=None, concesionario="MOTOHOY", diacobro="TODO", filpago="TODO"):
        """
        Consulta el reporte de No-Pagos del sistema oficial (plan_nopago).
        En sucursales con multiples empresas (ej. Cartagena: MOTOHOY y
        RENTAYA), consulta TODAS las empresas detectadas y consolida --
        bug real corregido 2026-09-25: antes solo consultaba UNA empresa
        (el `concesionario` fijo de nopago.config.CAJA3_SCRAPER), perdiendo
        completo el otro lado. Verificado con datos reales de Cartagena:
        RENTAYA traia 200 registros con CERO solapamiento de placa contra
        los 287 de MOTOHOY -- el reporte "Sistema Oficial" quedaba con
        menos de la mitad de los datos reales, sin ningun error visible.
        En sucursales de una sola empresa (ej. Monteria), hace 1 sola
        consulta (fetch_empresas_disponibles devuelve solo esa).

        Segundo bug real corregido 2026-09-25 (reportado por el lider del
        proyecto, "en Cartagena hay 530 pero traen 484"): `filpago`
        (el filtro `#filpago` del formulario real) tenia default
        "NOPAGO", que EXCLUYE la categoria "MAYOR2" (etiquetada "GRAVES"
        en el select real). Verificado contra el sitio con las 3
        opciones reales del `<select id="filpago">` (TODO/NOPAGO/MAYOR2):
        NOPAGO solo trae 484 (286 MOTOHOY + 198 RENTAYA), TODO trae 530
        (310 + 220) -- coincide EXACTO con el conteo manual del usuario.
        Default ahora "TODO", igual que `diacobro`.
        """
        if not empresas:
            empresas = self.fetch_empresas_disponibles()

        registros_totales = []
        vistos = set()
        for emp in empresas:
            print(f"[*] Consultando No-Pagos del sistema para la empresa: {emp}...")
            data_emp = self._fetch_nopagos_sistema_json_una_empresa(
                concesionario=emp, diacobro=diacobro, filpago=filpago
            )
            items = data_emp.get("data", []) if isinstance(data_emp, dict) else []
            for it in items:
                if isinstance(it, dict):
                    clave_unica = (it.get("contrato"), it.get("placa"))
                    if clave_unica not in vistos:
                        vistos.add(clave_unica)
                        registros_totales.append(it)

        print(f"[+] Total de No-Pagos del sistema recuperados y consolidados: {len(registros_totales)}")
        return {"validacion": "ok", "data": registros_totales}

    def _fetch_nopagos_sistema_json_una_empresa(self, concesionario="MOTOHOY", diacobro="TODO", filpago="TODO"):
        """Consulta plan_nopago para UNA sola empresa -- ver fetch_nopagos_sistema_json (publica) para el consolidado multi-empresa."""
        compania_obj = {"CONCEPTO": concesionario, "CONCEPTO_AUX": "RENTAYA"}
        try:
            plan_resp = self.session.get(f"{self.base_url}/rastreoya/recaudo?suburl=plan_nopago", timeout=self.timeout)
            if plan_resp.status_code == 200:
                match = re.search(r'const\s+\$compania\s*=\s*(\{.*?\});', plan_resp.text)
                if match:
                    compania_obj = json.loads(match.group(1))
        except Exception:
            pass

        post_payload = {
            "diacobro": diacobro,
            "cobrojr": "TODO",
            "ruta_empresa": concesionario,
            "punto_ruta": "TODO",
            "cobrodor_ruta": "TODO",
            "filpago": filpago,
            "CONCESIONARIO": concesionario,
            "compania": compania_obj
        }

        data = self.fetch_ajax_report(
            endpoint_path="/rastreoya/vistas/modulo/ajax/NoPagos.php",
            payload_key="dtbuNoPagoNew",
            payload_data=post_payload
        )

        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            cleaned = []
            for item in data["data"]:
                if isinstance(item, dict):
                    cleaned.append({k: v for k, v in item.items() if not k.isdigit()})
                else:
                    cleaned.append(item)
            data["data"] = cleaned

        return data

    def export_nopagos_sistema_excel(self, output_path="downloads/NoPagos_Sistema_Oficial.xlsx", concesionario="MOTOHOY"):
        """
        Extrae los No-Pagos oficiales del sistema y los exporta a Excel (.xlsx) mapeando
        las columnas exactamente iguales al archivo de exportación manual de la plataforma web.
        """
        data = self.fetch_nopagos_sistema_json(concesionario=concesionario)
        records = data.get("data", []) if isinstance(data, dict) else []

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

        formatted_records = []
        for r in records:
            if not isinstance(r, dict):
                continue
            placa = str(r.get("placa") or "").strip()
            arrendador = str(r.get("arrendador") or r.get("nomcli") or "").strip()
            conductor_str = f"{placa} - {arrendador}" if placa and arrendador else (placa or arrendador)

            formatted_records.append({
                "Conductor": conductor_str,
                "Barrio": r.get("barrio", ""),
                "Ruta": r.get("ruta", ""),
                "Cobrador": r.get("alerta_cierre") or r.get("cobro") or "",
                "Dia cobro": r.get("dia_canon", ""),
                "Periodo pago": r.get("periodo_pago_id", ""),
                "Deuda": r.get("deuda_cli", 0),
                "# Deuda": r.get("cantinop", 0),
                "Saldo": r.get("saldo", 0),
                "Cuota": r.get("cuota", 0),
                "Comentario": r.get("ultimos_comen") or r.get("ultcomen") or "",
                "Contrato rty": r.get("codigo_rty", ""),
                "Estado problema": r.get("estado_prob", ""),
                "Telefono": r.get("TELULT", ""),
                "Contrato": r.get("contrato", ""),
                "Color": r.get("Color", "rojo"),
                "NuevoSinPagar": r.get("NuevoSinPagar", ""),
                "Incompleto": r.get("Incompleto", "")
            })

        try:
            import pandas as pd
            df = pd.DataFrame(formatted_records)
            try:
                df.to_excel(output_path, index=False)
                print(f"[+] {len(formatted_records)} registros exportados a Excel oficial: {output_path}")
                return output_path
            except PermissionError:
                alt_path = output_path.replace(".xlsx", "_nuevo.xlsx")
                df.to_excel(alt_path, index=False)
                print(f"[!] El archivo '{output_path}' está abierto en Excel. Guardado en: {alt_path}")
                return alt_path
        except ImportError:
            json_fallback = output_path.replace(".xlsx", ".json")
            with open(json_fallback, "w", encoding="utf-8") as f:
                json.dump(formatted_records, f, ensure_ascii=False, indent=2)
            print(f"[!] pandas no disponible. Registros guardados en JSON: {json_fallback}")
            return json_fallback

    def fetch_report_pdf(self, report_url, date_str, empresa="MOTOHOY", output_path=None):
        """
        Obtiene los datos del informe y los guarda en disco en formato JSON.
        """
        json_data = self.fetch_caja_balance_json(date_str, concesionario=empresa, empresa_prin=empresa)
        fecha_fmt = self._format_date_yyyy_mm_dd(date_str)
        os.makedirs("downloads", exist_ok=True)
        json_out_path = output_path.replace(".pdf", ".json") if output_path and output_path.endswith(".pdf") else (output_path or f"downloads/caja_balance_{fecha_fmt}.json")

        with open(json_out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)

        print(f"[+] Datos JSON del informe guardados en: {json_out_path}")
        return json_data, json_out_path
