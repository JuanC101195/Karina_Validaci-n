"""
Lectura de los dos Excel de entrada: Caja 3 (.xlsm del Diskstation) y
CONTABILIDAD (.xlsx descargado del Drive). Se leen con data_only=True:
importa el valor que Excel/Sheets ya calculo, no la formula.
"""
import datetime as dt

import openpyxl
from openpyxl.utils import column_index_from_string

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
        "pronto": leer(cfg["pronto"]),
        "alquiler": leer(cfg["alquiler"]),
        "traslado": leer(cfg["traslado"]),
        "gastos": sum(leer(c) for c in cfg["gastos"]),
        "retiro": leer(cfg["retiro"]),
        "saldo": leer(cfg["saldo"]),
        "saldo_caja3": leer(cfg["saldo_caja3"]),
    }


def leer_contabilidad(wb, hoja, fecha, columnas, avisos):
    """Valores digitados en la pestaña JP/RC para la fecha.

    Devuelve (fila, {col: valor o None}); None = celda vacia.
    """
    ws = wb[hoja]
    filas = _buscar_fila(ws, COL_FECHA_CONTABILIDAD, fecha, desde=FILA_INICIO_CONTABILIDAD)
    if not filas:
        avisos.append(f"CONTABILIDAD ({hoja}) no tiene fila para {fecha}")
        return None, {}
    fila = filas[0]
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
