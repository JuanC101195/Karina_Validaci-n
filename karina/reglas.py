"""
Reglas puras de Validaciones Karina: arman la fila esperada de las pestañas
JP y RC de CONTABILIDAD a partir de las dos fuentes y la comparan con lo
digitado. No leen archivos ni red (se prueban con datos sinteticos).

Fuentes (mapeo verificado con el usuario 2026-10-14 contra 1-13 oct 2026):
- OpenCorp "informe_recaudo_general" (LoadRecaudoGeneral) -> columnas C..V e Y.
- Caja 3 (hojas JPMOTO / RICARMOTO) -> columnas Z..AJ.
"""
import re

HOJAS = ("JP", "RC")

# empresa del informe -> indice del punto (orden de las columnas del Excel)
EMPRESA_A_PUNTO = {
    "FAVIPAN": 0,
    "COMPRA VENTAS": 1,
    "RENTAYA": 2,
    "SERVIEFECTIVO": 3,
    "ALMACEN DE REPUESTOS": 4,  # en el Excel la columna se llama INDIA
    "MOTOHOY": 5,               # MOTOHOY en efectivo, MH en multas/repuestos
}
PUNTOS = ("FAVIPAN", "COMP/V", "RENTAYA", "SERVIEN", "INDIA", "MOTOHOY")

# campo del informe -> columnas de CONTABILIDAD, una por punto
BLOQUES_RECAUDO = {
    "efectivo": ("abono", ("C", "D", "E", "F", "G", "H")),
    "multa": ("multa", ("I", "J", "K", "L", "M", "N")),
    "repuesto": ("repuesto", ("Q", "R", "S", "T", "U", "V")),
}
COL_PRONTO = "Y"

# Columnas de Caja 3 por hoja. Los nombres de las columnas no coinciden
# entre JPMOTO y RICARMOTO (RICARMOTO tiene una columna menos desde la Q),
# por eso se mapean por separado.
CAJA3 = {
    "JP": {
        "hoja": "JPMOTO",
        "ajustes": "E", "pronto": "J", "alquiler": "O", "traslado": "P",
        "gastos": ("K", "L", "M", "AE"),  # MotoHoy, RentaYa, RastreoYa, TIO
        "retiro": "AG",                   # pablo
        "saldo": "I", "saldo_caja3": "AU",
    },
    "RC": {
        "hoja": "RICARMOTO",
        "ajustes": "E", "pronto": "J", "alquiler": "O", "traslado": "P",
        "gastos": ("K", "L", "M", "AD"),  # MotoHoy, RentaYa, RastreoYa, SER
        "retiro": "AF",                   # RICAR
        "saldo": "I", "saldo_caja3": "AT",
    },
}

NOMBRES_COLUMNA = {
    "Y": "PRONTOS PAGO", "Z": "TRASLADO RENTAYA", "AA": "AJUSTES CAJA 3",
    "AB": "ALQUILER", "AC": "MOTOS COMITE", "AD": "GASTOS COMITE",
    "AE": "RETIRO COMITE", "AG": "CAJA 3", "AJ": "SAL CAJA 3",
}
for _bloque, (_campo, _cols) in BLOQUES_RECAUDO.items():
    for _punto, _col in zip(PUNTOS, _cols):
        NOMBRES_COLUMNA[_col] = f"{_bloque} {_punto}"

TOLERANCIA = 0.5  # los valores van en miles; menos de $500 es redondeo


def hoja_de_cobro(cobro):
    """'JP', 'JP1'..'JP11' -> JP; 'Ricar', 'RC1'.. -> RC (el JS del sitio
    traduce Ricar a RC). Cualquier otro cobro devuelve None."""
    cobro = (cobro or "").strip()
    if re.fullmatch(r"JP\d*", cobro):
        return "JP"
    if cobro == "Ricar" or re.fullmatch(r"RC\d*", cobro):
        return "RC"
    return None


def _num(valor):
    try:
        return float(valor or 0)
    except (TypeError, ValueError):
        return None


def agrupar_recaudo(registros):
    """Suma los registros del informe de recaudo general por hoja y columna.

    Devuelve (filas, avisos): filas = {"JP": {col: valor}, "RC": {...}}.
    `prestamo` se ignora: en todos los registros revisados es copia de
    `repuesto` (confirmado 2026-10-14, 10-oct). Registros con un cobro o
    una empresa que no conocemos no se descartan en silencio: van a avisos.
    """
    filas = {h: {} for h in HOJAS}
    for h in HOJAS:
        for _campo, cols in BLOQUES_RECAUDO.values():
            for col in cols:
                filas[h][col] = 0.0
        filas[h][COL_PRONTO] = 0.0
    avisos = []
    for reg in registros:
        hoja = hoja_de_cobro(reg.get("COBRO"))
        punto = EMPRESA_A_PUNTO.get((reg.get("empresa") or "").strip())
        if hoja is None or punto is None:
            avisos.append(f"Registro sin mapear: cobro={reg.get('COBRO')!r} empresa={reg.get('empresa')!r} neto={reg.get('neto')}")
            continue
        for campo, cols in BLOQUES_RECAUDO.values():
            valor = _num(reg.get(campo))
            if valor is None:
                avisos.append(f"Valor ilegible en {campo} ({reg.get('COBRO')}/{reg.get('empresa')}): {reg.get(campo)!r}")
                continue
            filas[hoja][cols[punto]] += valor
        pronto = _num(reg.get("pronto"))
        if pronto is None:
            avisos.append(f"Pronto ilegible ({reg.get('COBRO')}/{reg.get('empresa')}): {reg.get('pronto')!r}")
        else:
            filas[hoja][COL_PRONTO] += pronto
        if _num(reg.get("transf")):
            # El 1-13 oct no hubo transferencias; no sabemos a que columna van.
            avisos.append(f"Transferencia sin columna definida ({reg.get('COBRO')}/{reg.get('empresa')}): {reg.get('transf')} -- no se sumo")
    return filas, avisos


def fila_desde_caja3(valores):
    """Arma las columnas Z..AJ desde una fila de Caja 3.

    `valores` = {"ajustes", "pronto", "alquiler", "traslado", "gastos",
    "retiro", "saldo", "saldo_caja3"} ya numericos (gastos = suma).

    Dia de comite: Caja 3 trae gastos o retiro de comite. Ese dia la
    columna "alquiler" de Caja 3 es la plata de MOTOS COMITE (AC); los
    demas dias es ALQUILER (AB). Verificado 2 y 9 oct 2026 (JP y RC).
    """
    es_comite = bool(valores["gastos"] or valores["retiro"])
    return {
        "Z": valores["traslado"],
        # AA = ajustes de cuotas de Caja 3. Coincide casi todos los dias,
        # pero hay dias en que el Excel tiene otro valor (JP 5-oct -295):
        # pendiente confirmar con el usuario.
        "AA": valores["ajustes"],
        "AB": 0.0 if es_comite else valores["alquiler"],
        "AC": valores["alquiler"] if es_comite else 0.0,
        "AD": valores["gastos"],
        "AE": valores["retiro"],
        "AG": valores["saldo"],
        "AJ": valores["saldo_caja3"],
    }, es_comite


def pronto_caja3_vs_sistema(pronto_caja3, pronto_sistema):
    """El pronto sale de dos fuentes (OpenCorp y Caja 3); si no coinciden
    se avisa en vez de escoger uno."""
    if abs((pronto_caja3 or 0) - (pronto_sistema or 0)) > TOLERANCIA:
        return f"Pronto distinto: sistema={pronto_sistema:,.2f} Caja 3={pronto_caja3:,.2f}"
    return None


def comparar(esperado, actual):
    """Lista las celdas donde lo digitado difiere de lo esperado.

    `actual[col]` = None significa celda vacia. Una celda vacia con valor
    esperado 0 no es diferencia.
    """
    difs = []
    for col, valor_esp in esperado.items():
        valor_act = actual.get(col)
        act = 0.0 if valor_act is None else valor_act
        if abs(act - valor_esp) > TOLERANCIA:
            difs.append({
                "columna": col,
                "concepto": NOMBRES_COLUMNA.get(col, col),
                "excel": valor_act,
                "esperado": round(valor_esp, 2),
                "diferencia": round(act - valor_esp, 2),
            })
    return difs
