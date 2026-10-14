"""
Lectura de los dos Excel de entrada: Caja 3 (.xlsm del Diskstation) y
CONTABILIDAD (.xlsx descargado del Drive). Se leen con data_only=True:
importa el valor que Excel/Sheets ya calculo, no la formula.
"""
import datetime as dt
import io

import openpyxl
from openpyxl.utils import column_index_from_string, get_column_letter

from .reglas import CAJA3

COL_FECHA_CAJA3 = 3        # C
COL_FECHA_CONTABILIDAD = 1  # A
FILA_INICIO_CONTABILIDAD = 5


def abrir(path):
    # read_only=False: se necesita acceso por celda; los archivos son de 5-60 MB
    return openpyxl.load_workbook(path, data_only=True)


def _celda(ws, fila, col):
    return ws.cell(fila, column_index_from_string(col)).value


def _numero(ws, fila, col, avisos, origen):
    """Celda vacia = 0 (asi se usa en ambos libros). Texto o error de
    formula (#REF!) NO se convierte en 0: va a avisos."""
    valor = _celda(ws, fila, col)
    if valor is None or valor == "":
        return 0.0
    if isinstance(valor, (int, float)):
        return float(valor)
    avisos.append(f"{origen} {col}{fila}: valor no numerico {valor!r}, se toma 0")
    return 0.0


def _buscar_fila(ws, col_fecha, fecha, desde=1):
    objetivo = dt.datetime.combine(fecha, dt.time())
    filas = [r for r in range(desde, ws.max_row + 1) if ws.cell(r, col_fecha).value == objetivo]
    return filas


def leer_caja3(wb, hoja, fecha, avisos):
    """Valores de Caja 3 del dia para la hoja JP o RC, o None si no hay fila."""
    cfg = CAJA3[hoja]
    ws = wb[cfg["hoja"]]
    filas = _buscar_fila(ws, COL_FECHA_CAJA3, fecha)
    if not filas:
        avisos.append(f"Caja 3 ({cfg['hoja']}) no tiene fila para {fecha}")
        return None
    if len(filas) > 1:
        avisos.append(f"Caja 3 ({cfg['hoja']}) tiene {len(filas)} filas para {fecha}; se usa la ultima ({filas[-1]})")
    fila = filas[-1]
    origen = f"Caja 3 {cfg['hoja']}"
    leer = lambda col: _numero(ws, fila, col, avisos, origen)
    return {
        "ajustes": leer(cfg["ajustes"]),
        "ajustes_multas": leer(cfg["ajustes_multas"]),
        "pronto": leer(cfg["pronto"]),
        "alquiler": leer(cfg["alquiler"]),
        "traslado": leer(cfg["traslado"]),
        "gastos": sum(leer(c) for c in cfg["gastos"]),
        "retiro": leer(cfg["retiro"]),
        "saldo": leer(cfg["saldo"]),
        "saldo_caja3": leer(cfg["saldo_caja3"]),
    }


def leer_encabezados(wb, hojas, ultima_col="AJ"):
    """Filas 2 y 3 de cada pestaña (grupo y nombre de columna), para que el
    Excel de salida tenga los mismos titulos que CONTABILIDAD."""
    salida = {}
    for hoja in hojas:
        ws = wb[hoja]
        n = column_index_from_string(ultima_col)
        fila2, fila3 = {}, {}
        for c in range(1, n + 1):
            # get_column_letter y no cell.column_letter: los titulos de grupo
            # (RECAUDOS EFECTIVOS, MULTAS...) son celdas combinadas.
            col = get_column_letter(c)
            fila2[col] = ws.cell(2, c).value
            fila3[col] = ws.cell(3, c).value
        salida[hoja] = (fila2, fila3)
    return salida


def abrir_bytes(datos, formulas=False):
    """Abre un Excel ya leido en memoria (formulas=True: sin data_only)."""
    return openpyxl.load_workbook(io.BytesIO(datos), data_only=not formulas)


def abrir_formulas(path):
    """Mismo libro sin data_only: para leer las formulas de O/W."""
    return openpyxl.load_workbook(path)


def leer_acumulados(wb_valores, wb_formulas, hoja, fila, avisos):
    """Insumos para recalcular ACUM (O) y RPTOS (W) de una fila:
    acumulado del dia anterior, ajuste P y formula actual de cada columna."""
    wv, wf = wb_valores[hoja], wb_formulas[hoja]
    origen = f"CONTABILIDAD {hoja}"
    datos = {"P": _numero(wv, fila, "P", avisos, origen)}
    for col in ("O", "W"):
        datos[col] = {
            "anterior": _numero(wv, fila - 1, col, avisos, origen) if fila - 1 >= FILA_INICIO_CONTABILIDAD else 0.0,
            "formula": wf[f"{col}{fila}"].value,
        }
    return datos


def fila_contabilidad(wb, hoja, fecha):
    filas = _buscar_fila(wb[hoja], COL_FECHA_CONTABILIDAD, fecha, desde=FILA_INICIO_CONTABILIDAD)
    return filas[0] if filas else None


def leer_fila_contabilidad(wb, hoja, fila, columnas, avisos):
    """Valores digitados en una fila de JP/RC: {col: valor o None}; None = vacia."""
    ws = wb[hoja]
    valores = {}
    for col in columnas:
        v = _celda(ws, fila, col)
        if v is None or v == "":
            valores[col] = None
        elif isinstance(v, (int, float)):
            valores[col] = float(v)
        else:
            avisos.append(f"CONTABILIDAD {hoja} {col}{fila}: valor no numerico {v!r}")
            valores[col] = None
    return valores


def fecha_de_fila(wb, hoja, fila):
    v = wb[hoja].cell(fila, COL_FECHA_CONTABILIDAD).value
    return v.date() if isinstance(v, dt.datetime) else None


def ultima_fila_antes(wb, hoja, fecha):
    """Fila de la ultima fecha anterior a `fecha` (None si no hay)."""
    ws = wb[hoja]
    objetivo = dt.datetime.combine(fecha, dt.time())
    mejor = None
    for r in range(FILA_INICIO_CONTABILIDAD, ws.max_row + 1):
        v = ws.cell(r, COL_FECHA_CONTABILIDAD).value
        if isinstance(v, dt.datetime) and v < objetivo:
            mejor = r
    return mejor


def fila_vacia(wb, hoja, fila):
    ws = wb[hoja]
    return all(ws.cell(fila, c).value in (None, "") for c in range(1, 37))


def leer_contabilidad(wb, hoja, fecha, columnas, avisos):
    """Valores digitados en la pestaña JP/RC para la fecha.

    Devuelve (fila, {col: valor o None}); None = celda vacia.
    """
    ws = wb[hoja]
    fila = fila_contabilidad(wb, hoja, fecha)
    if fila is None:
        avisos.append(f"CONTABILIDAD ({hoja}) no tiene fila para {fecha}")
        return None, {}
    valores = {}
    for col in columnas:
        v = _celda(ws, fila, col)
        if v is None or v == "":
            valores[col] = None
        elif isinstance(v, (int, float)):
            valores[col] = float(v)
        else:
            avisos.append(f"CONTABILIDAD {hoja} {col}{fila}: valor no numerico {v!r}")
            valores[col] = None
    return fila, valores
