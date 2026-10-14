"""
Orquesta una validacion: para una fecha consulta OpenCorp, lee Caja 3 y
CONTABILIDAD, arma la fila esperada de JP y RC y lista las diferencias.
"""
import json
from pathlib import Path

from . import excel_io, reglas
from .opencorp_scraper import OpenCorpScraper

BASE_URL = "https://app.opencorp.co:543"
URL_INFORME = f"{BASE_URL}/rastreoya/recaudo?suburl=informe_recaudo_general"
CREDS_FILE = Path(__file__).resolve().parent.parent / "opencorp_creds.json"


def cargar_credenciales(path=CREDS_FILE):
    with open(path, encoding="utf-8") as f:
        creds = json.load(f)
    return creds["email"], creds["password"]


def conectar(email, password):
    scraper = OpenCorpScraper(base_url=BASE_URL)
    scraper.login(email, password, target_url=URL_INFORME)
    return scraper


def recaudo_general(scraper, fecha):
    """Registros del informe de recaudo general del dia (lista de dicts).
    'sin' = no hubo movimientos (domingo/festivo): lista vacia."""
    resp = scraper.fetch_ajax_report(
        endpoint_path="/rastreoya/vistas/modulo/ajax/buscarNotificacion.php",
        payload_key="LoadRecaudoGeneral",
        payload_data={"fecha": fecha.isoformat()},
    )
    return resp.get("data") or []


def validar_fecha(fecha, registros, wb_caja3, wb_contabilidad):
    """Valida una fecha con los registros de OpenCorp ya descargados.

    Devuelve {"fecha", "avisos", "hojas": {"JP": {...}, "RC": {...}}}.
    """
    avisos = []
    recaudo, avisos_recaudo = reglas.agrupar_recaudo(registros)
    avisos.extend(avisos_recaudo)
    resultado = {"fecha": fecha, "registros": len(registros), "avisos": avisos, "hojas": {}}
    for hoja in reglas.HOJAS:
        esperado = dict(recaudo[hoja])
        es_comite = False
        caja3 = excel_io.leer_caja3(wb_caja3, hoja, fecha, avisos) if wb_caja3 else None
        if caja3 is not None:
            cols_caja3, es_comite = reglas.fila_desde_caja3(caja3)
            esperado.update(cols_caja3)
            aviso = reglas.pronto_caja3_vs_sistema(caja3["pronto"], esperado[reglas.COL_PRONTO])
            if aviso:
                avisos.append(f"{hoja}: {aviso}")
        fila, actual = excel_io.leer_contabilidad(wb_contabilidad, hoja, fecha, esperado.keys(), avisos)
        resultado["hojas"][hoja] = {
            "fila": fila,
            "comite": es_comite,
            "esperado": esperado,
            "diferencias": reglas.comparar(esperado, actual) if fila else [],
        }
    return resultado
