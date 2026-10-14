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


def validar_fecha(fecha, registros, wb_caja3, wb_contabilidad, wb_contabilidad_formulas=None,
                  alquiler_comite=None, previo=None):
    """Valida (y prepara el llenado de) una fecha con los registros de OpenCorp.

    `wb_contabilidad_formulas` (el mismo libro sin data_only) habilita los
    acumulados O/W. `alquiler_comite` = {"JP": valor, "RC": valor} (ver
    reglas.separar_alquiler). `previo` = resultado["hojas"] del dia anterior
    del mismo rango: encadena la fila y los acumulados cuando el dia anterior
    tambien se esta llenando.

    Si la fecha no tiene fila en CONTABILIDAD (fila borrada o aun no creada)
    se asigna la siguiente a la ultima fecha anterior, si esta vacia: el
    programa la llena (confirmado con el usuario 2026-10-14: la finalidad es
    llenar, no solo comparar).

    Devuelve {"fecha", "registros", "avisos", "hojas": {"JP": {...}, "RC": {...}}}.
    """
    avisos = []
    recaudo, avisos_recaudo = reglas.agrupar_recaudo(registros)
    avisos.extend(avisos_recaudo)
    resultado = {"fecha": fecha, "registros": len(registros), "avisos": avisos, "hojas": {}}
    alquiler_comite = alquiler_comite or {}
    previo = previo or {}
    for hoja in reglas.HOJAS:
        esperado = dict(recaudo[hoja])
        es_comite, pregunta = _aplicar_caja3(wb_caja3, hoja, fecha, esperado, alquiler_comite.get(hoja), avisos)
        ant = previo.get(hoja) or {}
        fila, nueva = _ubicar_fila(wb_contabilidad, hoja, fecha, ant, avisos)
        reinicio = None
        if fila and wb_contabilidad_formulas is not None:
            reinicio = _reinicia_acumulado(wb_contabilidad, wb_caja3, hoja, fila, ant)
            _aplicar_acumulados(wb_contabilidad, wb_contabilidad_formulas, hoja, fila, nueva, reinicio, ant, esperado, avisos)
        actual = excel_io.leer_fila_contabilidad(wb_contabilidad, hoja, fila, esperado.keys(), avisos) if fila else {}
        resultado["hojas"][hoja] = {
            "fila": fila,
            "nueva": nueva,
            "reinicio": reinicio,
            "comite": es_comite,
            "pregunta_alquiler": pregunta,
            "esperado": esperado,
            "diferencias": [] if nueva or not fila else reglas.comparar(esperado, actual),
        }
    return resultado


def _aplicar_caja3(wb_caja3, hoja, fecha, esperado, respuesta, avisos):
    """Agrega a `esperado` las columnas de Caja 3. Devuelve (es_comite, pregunta)."""
    caja3 = excel_io.leer_caja3(wb_caja3, hoja, fecha, avisos) if wb_caja3 else None
    if caja3 is None:
        return False, None
    cols_caja3, es_comite, pendiente = reglas.fila_desde_caja3(caja3, respuesta)
    esperado.update(cols_caja3)
    pregunta = None
    if es_comite and caja3["alquiler"]:
        pregunta = {"total": caja3["alquiler"], "respuesta": respuesta, "pendiente": pendiente}
        if respuesta is not None and not 0 <= respuesta <= caja3["alquiler"]:
            avisos.append(f"{hoja}: el alquiler digitado ({respuesta:,.2f}) no esta entre 0 y el total de Caja 3 ({caja3['alquiler']:,.2f})")
    aviso = reglas.pronto_caja3_vs_sistema(caja3["pronto"], esperado[reglas.COL_PRONTO])
    if aviso:
        avisos.append(f"{hoja}: {aviso}")
    return es_comite, pregunta


def _aplicar_acumulados(wb_contab, wb_formulas, hoja, fila, nueva, reinicio, ant, esperado, avisos):
    """Calcula O/W esperados. El acumulado de ayer: si ayer tambien se esta
    llenando en este rango, el valor correcto calculado; si no, el de
    CONTABILIDAD."""
    acum = excel_io.leer_acumulados(wb_contab, wb_formulas, hoja, fila, avisos)
    encadena = ant.get("fila") == fila - 1
    for col in reglas.ACUMULADOS:
        info = acum[col]
        anterior = ant["esperado"][col] if encadena and col in ant.get("esperado", {}) else info["anterior"]
        esperado[col] = reglas.acumulado_esperado(col, esperado, acum["P"], anterior, reinicio)
        if not nueva:
            avisos.extend(f"{hoja}: {a}" for a in reglas.revisar_formula_acumulado(col, info["formula"], fila, reinicio))


def _ubicar_fila(wb, hoja, fecha, ant, avisos):
    """(fila, nueva). nueva=True: la fecha no esta y se usa la fila vacia
    que sigue a la ultima fecha anterior."""
    fila = excel_io.fila_contabilidad(wb, hoja, fecha)
    if fila:
        return fila, False
    base = ant.get("fila") or excel_io.ultima_fila_antes(wb, hoja, fecha)
    if base and excel_io.fila_vacia(wb, hoja, base + 1):
        avisos.append(f"{hoja}: CONTABILIDAD no tiene fila para {fecha}; se llena la fila {base + 1}")
        return base + 1, True
    avisos.append(f"CONTABILIDAD ({hoja}) no tiene fila para {fecha} y no hay una fila vacia donde crearla")
    return None, False


def _reinicia_acumulado(wb_contab, wb_caja3, hoja, fila, ant):
    """ACUM/RPTOS se reinician el dia siguiente al comite (todos los viernes):
    se mira si el dia de la fila anterior fue comite en Caja 3."""
    if ant.get("fila") == fila - 1:
        return bool(ant.get("comite"))
    fecha_ant = excel_io.fecha_de_fila(wb_contab, hoja, fila - 1)
    if fecha_ant is None or wb_caja3 is None:
        return False
    c3 = excel_io.leer_caja3(wb_caja3, hoja, fecha_ant, [])
    return bool(c3 and (c3["gastos"] or c3["retiro"]))


def validar_rango(fechas, registros_por_fecha, wb_caja3, wb_contab, wb_contab_f, respuestas=None):
    """Valida varias fechas en orden, encadenando filas y acumulados.
    `respuestas` = {fecha: {"JP": alquiler, "RC": alquiler}}."""
    respuestas = respuestas or {}
    dias, previo = [], None
    for f in fechas:
        res = validar_fecha(f, registros_por_fecha[f], wb_caja3, wb_contab, wb_contab_f,
                            alquiler_comite=respuestas.get(f), previo=previo)
        dias.append(res)
        previo = res["hojas"]
    return dias
