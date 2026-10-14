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
    # efectivo = abono + transf: las transferencias se suman al recaudo del
    # punto (confirmado con el usuario 2026-10-14).
    "efectivo": (("abono", "transf"), ("C", "D", "E", "F", "G", "H")),
    "multa": (("multa",), ("I", "J", "K", "L", "M", "N")),
    "repuesto": (("repuesto",), ("Q", "R", "S", "T", "U", "V")),
}
COL_PRONTO = "Y"

# Columnas de Caja 3 por hoja. Los nombres de las columnas no coinciden
# entre JPMOTO y RICARMOTO (RICARMOTO tiene una columna menos desde la Q),
# por eso se mapean por separado.
CAJA3 = {
    "JP": {
        "hoja": "JPMOTO",
        "ajustes": "E", "ajustes_multas": "F", "pronto": "J", "alquiler": "O", "traslado": "P",
        # Verificado contra AD de los viernes 28-ago..2-oct 2026: SER suma
        # (4-sep +1000, 11-sep +250, 18-sep +98).
        "gastos": ("K", "L", "M", "AE", "AF"),  # MotoHoy, RentaYa, RastreoYa, TIO, SER
        "retiro": "AG",                   # pablo
        "saldo": "I", "saldo_caja3": "AU",
    },
    "RC": {
        "hoja": "RICARMOTO",
        "ajustes": "E", "ajustes_multas": "F", "pronto": "J", "alquiler": "O", "traslado": "P",
        # Verificado igual que JP: ANTONI suma (28-ago +350, 11-sep +32).
        "gastos": ("K", "L", "M", "AC", "AD", "AE"),  # MotoHoy, RentaYa, RastreoYa, ANTONI, SER, TIO
        "retiro": "AF",                   # RICAR
        "saldo": "I", "saldo_caja3": "AT",
    },
}

NOMBRES_COLUMNA = {
    "P": "AJUSTES MULTAS", "Y": "PRONTOS PAGO", "Z": "TRASLADO RENTAYA", "AA": "AJUSTES CAJA 3",
    "AB": "ALQUILER", "AC": "MOTOS COMITE", "AD": "GASTOS COMITE",
    "AE": "RETIRO COMITE", "AG": "CAJA 3", "AJ": "SAL CAJA 3",
}
for _bloque, (_campo, _cols) in BLOQUES_RECAUDO.items():
    for _punto, _col in zip(PUNTOS, _cols):
        NOMBRES_COLUMNA[_col] = f"{_bloque} {_punto}"

# Los valores van en miles; CONTABILIDAD a veces redondea a enteros
# (AD 65131 vs 65131.84 de Caja 3): diferencias de menos de 1 no cuentan
# (confirmado con el usuario 2026-10-14).
TOLERANCIA = 1.0


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
        _sumar_registro(reg, filas[hoja], punto, avisos)
    return filas, avisos


def _sumar_registro(reg, fila, punto, avisos):
    quien = f"{reg.get('COBRO')}/{reg.get('empresa')}"
    destinos = [(campo, cols[punto]) for campos, cols in BLOQUES_RECAUDO.values() for campo in campos]
    destinos.append(("pronto", COL_PRONTO))
    for campo, col in destinos:
        valor = _num(reg.get(campo))
        if valor is None:
            avisos.append(f"Valor ilegible en {campo} ({quien}): {reg.get(campo)!r}")
        else:
            fila[col] += valor


def leer_monto(texto):
    """Monto digitado por Karina, en formato colombiano o plano.

    "15.980" y "15980" -> 15980; "1.234,5" -> 1234.5; "155,5" y "155.5" ->
    155.5. Un punto seguido de grupos de exactamente 3 digitos es separador
    de miles (los montos van en miles con 1-2 decimales, nunca 3).
    Lanza ValueError si no es un numero.
    """
    s = str(texto).strip().replace("$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    return float(s)


def separar_alquiler(total_caja3, es_comite, alquiler_comite):
    """Reparte la columna "alquiler" de Caja 3 entre ALQUILER (AB) y MOTOS
    COMITE (AC).

    Sin comite todo es alquiler. El dia del comite, Caja 3 trae en esa
    columna el alquiler MAS la inversion en motos (se monta el sabado en la
    tarde con la fecha del comite) y ninguna columna los separa -- por eso
    se le pregunta a Karina el alquiler total y la diferencia es la
    inversion (confirmado con el usuario 2026-10-14; mismo patron que las
    motos de realquiler en Empresa_no_pago).

    Devuelve (ab, ac, pendiente): pendiente=True si falta la respuesta.
    """
    if not es_comite or not total_caja3:
        return total_caja3, 0.0, False
    if alquiler_comite is None:
        return None, None, True
    return alquiler_comite, total_caja3 - alquiler_comite, False


def fila_desde_caja3(valores, alquiler_comite=None):
    """Arma las columnas Z..AJ desde una fila de Caja 3.

    `valores` = {"ajustes", "ajustes_multas", "pronto", "alquiler", "traslado", "gastos",
    "retiro", "saldo", "saldo_caja3"} ya numericos (gastos = suma).
    `alquiler_comite` = alquiler total que digita Karina el dia del comite.

    Dia de comite: Caja 3 trae gastos o retiro de comite (todos los
    viernes, verificado ago-oct 2026). Devuelve (columnas, es_comite,
    pendiente); si pendiente, AB/AC no van en columnas.
    """
    es_comite = bool(valores["gastos"] or valores["retiro"])
    ab, ac, pendiente = separar_alquiler(valores["alquiler"], es_comite, alquiler_comite)
    cols = {
        # P = ajustes de multas y AA = ajustes de cuotas, columnas F y E de
        # Caja 3 (confirmado con el usuario 2026-10-14).
        "P": valores["ajustes_multas"],
        "Z": valores["traslado"],
        "AA": valores["ajustes"],
        "AD": valores["gastos"],
        "AE": valores["retiro"],
        "AG": valores["saldo"],
        "AJ": valores["saldo_caja3"],
    }
    if not pendiente:
        cols["AB"], cols["AC"] = ab, ac
    return cols, es_comite, pendiente


def pronto_caja3_vs_sistema(pronto_caja3, pronto_sistema):
    """Y (prontos) se valida contra OpenCorp; si Caja 3 dice otra cosa se
    alerta (confirmado con el usuario 2026-10-14)."""
    if abs((pronto_caja3 or 0) - (pronto_sistema or 0)) > TOLERANCIA:
        return f"ALERTA prontos: OpenCorp={pronto_sistema:,.2f} pero Caja 3={pronto_caja3:,.2f} (Y se valida contra OpenCorp)"
    return None


# Acumulados de la semana (se reinician el dia siguiente al comite).
# Formula correcta confirmada con el usuario 2026-10-14:
#   ACUM  O = SUMA(I:N, P) + O anterior   (todas las multas, INDIA y MH incluidas, + ajustes)
#   RPTOS W = SUMA(Q:V)    + W anterior   (todos los repuestos, INDIA y MH incluidas)
# Bug real encontrado 2026-10-14 (JP/RC): la plantilla semanal tenia una
# formula distinta por dia (I:L, I:M, +M+N...) y dejaba INDIA/MH por fuera.
ACUMULADOS = {
    "O": {"suma": ("I", "J", "K", "L", "M", "N", "P"), "rango": "SUM(I{r}:N{r},P{r})"},
    "W": {"suma": ("Q", "R", "S", "T", "U", "V"), "rango": "SUM(Q{r}:V{r})"},
}
NOMBRES_COLUMNA["O"] = "ACUM MULTAS"
NOMBRES_COLUMNA["W"] = "ACUM REPUESTOS"


def es_reinicio(formula, col, fila):
    """El dia de reinicio la formula no suma el acumulado de la fila anterior."""
    return f"{col}{fila - 1}" not in (formula or "").upper().replace("$", "")


def acumulado_esperado(col, esperado, ajustes_p, anterior, reinicio):
    """Valor que deberia tener O o W. `esperado` trae I..N / Q..V y P
    calculados; `ajustes_p` (P digitado) solo se usa si no hay Caja 3."""
    total = 0.0
    for c in ACUMULADOS[col]["suma"]:
        total += esperado.get("P", ajustes_p) if c == "P" else esperado.get(c, 0.0)
    return total if reinicio else total + (anterior or 0.0)


def revisar_formula_acumulado(col, formula, fila):
    """Avisos sobre la formula de O/W: que tenga la forma correcta y que no
    esconda numeros escritos a mano (ej. '...+W475-155.5')."""
    avisos = []
    if not isinstance(formula, str) or not formula.startswith("="):
        return [f"{col}{fila}: no es formula (valor fijo {formula!r}); debe ser ={ACUMULADOS[col]['rango'].format(r='')}…"]
    f = formula.upper().replace(" ", "").replace("$", "").replace("SUMA(", "SUM(").replace(";", ",")
    base = "=" + ACUMULADOS[col]["rango"].format(r=fila)
    correcta = base if es_reinicio(formula, col, fila) else f"{base}+{col}{fila - 1}"
    if f != correcta:
        avisos.append(f"{col}{fila}: formula {formula} distinta de la correcta {correcta}")
    sin_celdas = re.sub(r"[A-Z]{1,3}\d+", "", f)
    numeros = re.findall(r"[-+*/]\s*\d+(?:\.\d+)?", sin_celdas)
    if numeros:
        avisos.append(f"{col}{fila}: la formula tiene numeros escritos a mano ({' '.join(numeros)})")
    return avisos


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
