"""
Llena CONTABILIDAD.xlsx con lo validado: escribe directo en el XML de las
hojas JP y RC y deja intacto todo lo demas (otras pestañas, comentarios de
Google Sheets, vinculos externos, formatos condicionales). No se usa
openpyxl para guardar porque al reescribir el libro completo pierde los
metadatos de comentarios de Sheets (revisado 2026-10-14 en el archivo real).

Que se escribe:
- Fila existente: solo las celdas que no coinciden con lo esperado, y las
  formulas de ACUM (O) / RPTOS (W) si no son las correctas.
- Fila nueva (la fecha no estaba): fecha (=A anterior + dias), todos los
  valores, O/W correctas y las demas formulas (X, AF, AH, AI, AK, AL)
  copiadas de la fila anterior y corridas una fila.
Las formulas se escriben sin valor en cache y el libro queda marcado para
recalcular al abrir (Excel y Sheets lo hacen solos).
"""
import datetime as dt
import io
import re
import zipfile

from lxml import etree
from openpyxl.formula.translate import Translator
from openpyxl.utils import column_index_from_string

from . import excel_io, reglas

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
NS_TIPOS = "http://schemas.openxmlformats.org/package/2006/content-types"
RUTA_WORKBOOK = "xl/workbook.xml"
RUTA_WORKBOOK_RELS = "xl/_rels/workbook.xml.rels"
RUTA_TIPOS = "[Content_Types].xml"
RUTA_CALCCHAIN = "xl/calcChain.xml"
COLUMNAS_FORMULA_COPIADAS = ("X", "AF", "AH", "AI", "AK", "AL")


def _q(tag):
    return f"{{{NS}}}{tag}"


def _col_de(ref):
    return re.match(r"[A-Z]+", ref).group(0)


def _rutas_hojas(z):
    wb = etree.fromstring(z.read(RUTA_WORKBOOK))
    rels = etree.fromstring(z.read(RUTA_WORKBOOK_RELS))
    destino = {r.get("Id"): r.get("Target") for r in rels}
    rutas = {}
    for sh in wb.iter(_q("sheet")):
        t = destino[sh.get(f"{{{NS_REL}}}id")].lstrip("/")
        rutas[sh.get("name")] = t if t.startswith("xl/") else "xl/" + t
    return rutas


class _Hoja:
    """Acceso por fila/celda al sheetData de una hoja, manteniendo el orden."""

    def __init__(self, raiz):
        self.raiz = raiz
        self.datos = raiz.find(_q("sheetData"))
        self.filas = {int(f.get("r")): f for f in self.datos.iter(_q("row"))}

    def fila(self, r, plantilla=None):
        if r in self.filas:
            return self.filas[r]
        nueva = etree.Element(_q("row"), r=str(r))
        if plantilla is not None:
            for atr in ("spans", "ht", "customHeight", "s", "customFormat"):
                if plantilla.get(atr) is not None:
                    nueva.set(atr, plantilla.get(atr))
        siguientes = [n for n in sorted(self.filas) if n > r]
        if siguientes:
            self.filas[siguientes[0]].addprevious(nueva)
        else:
            self.datos.append(nueva)
        self.filas[r] = nueva
        return nueva

    def celda(self, r, col):
        ref = f"{col}{r}"
        fila = self.filas.get(r)
        if fila is None:
            return None
        for c in fila.iter(_q("c")):
            if c.get("r") == ref:
                return c
        return None

    def crear_celda(self, fila_el, r, col):
        ref = f"{col}{r}"
        nueva = etree.Element(_q("c"), r=ref)
        idx = column_index_from_string(col)
        for c in fila_el.iter(_q("c")):
            if column_index_from_string(_col_de(c.get("r"))) > idx:
                c.addprevious(nueva)
                return nueva
        fila_el.append(nueva)
        return nueva


def _formato_numero(v):
    v = round(float(v), 2)
    return str(int(v)) if v == int(v) else repr(v)


def _escribir(hoja, r, col, tipo, valor, estilo_de=None):
    """Escribe valor o formula. Devuelve False si la celda es la maestra de
    una formula compartida con otras celdas (pisarla rompe a las demas)."""
    fila_el = hoja.fila(r, hoja.filas.get(r - 1))
    c = hoja.celda(r, col)
    if c is None:
        c = hoja.crear_celda(fila_el, r, col)
    f = c.find(_q("f"))
    if f is not None and f.get("t") == "shared" and f.get("ref") and f.get("ref") != f"{col}{r}":
        return False
    for hijo in c.getchildren():
        c.remove(hijo)
    c.attrib.pop("t", None)
    if estilo_de is not None:
        base = hoja.celda(estilo_de, col)
        if base is not None and base.get("s") is not None:
            c.set("s", base.get("s"))
    if tipo == "f":
        etree.SubElement(c, _q("f")).text = valor
    else:
        etree.SubElement(c, _q("v")).text = _formato_numero(valor)
    return True


def _normalizar(formula):
    return (formula or "").upper().replace(" ", "").replace("$", "").lstrip("=")


def _formula_previa(escritos, wb_formulas, hoja, r, col):
    """Formula (con '=') de la celda de la fila anterior: la que se acaba de
    escribir en este mismo llenado, o la que ya tenia CONTABILIDAD."""
    previa = escritos.get((hoja, r - 1), {}).get(col)
    if previa is not None:
        return "=" + previa[1] if previa[0] == "f" else None
    v = wb_formulas[hoja][f"{col}{r - 1}"].value
    return v if isinstance(v, str) and v.startswith("=") else None


def _celdas_fila_nueva(h, hoja, wb_formulas, wb_valores, escritos, fecha):
    r = h["fila"]
    celdas = {col: ("v", v) for col, v in h["esperado"].items() if col not in reglas.ACUMULADOS}
    ant = escritos.get((hoja, r - 1), {}).get("_fecha") or excel_io.fecha_de_fila(wb_valores, hoja, r - 1)
    dias = (fecha - ant).days if ant else 1
    celdas["A"] = ("f", f"A{r - 1}+{dias}")
    for col in COLUMNAS_FORMULA_COPIADAS:
        previa = _formula_previa(escritos, wb_formulas, hoja, r, col)
        if previa:
            celdas[col] = ("f", Translator(previa, origin=f"{col}{r - 1}").translate_formula(f"{col}{r}")[1:])
    return celdas


def _celdas_acumulados(h, hoja, wb_formulas):
    """Formulas de O/W que hay que escribir (solo si no son ya las correctas)."""
    celdas = {}
    if h.get("reinicio") is None:
        return celdas
    r = h["fila"]
    for col in reglas.ACUMULADOS:
        correcta = reglas.formula_acumulado(col, r, h["reinicio"])
        actual = None if h["nueva"] else wb_formulas[hoja][f"{col}{r}"].value
        if _normalizar(actual) != _normalizar(correcta):
            celdas[col] = ("f", correcta)
    return celdas


def _celdas_a_escribir(h, hoja, wb_formulas, wb_valores, escritos, fecha):
    """{col: (tipo, valor)} para una fila de un dia."""
    if h["nueva"]:
        celdas = _celdas_fila_nueva(h, hoja, wb_formulas, wb_valores, escritos, fecha)
    else:
        celdas = {d["columna"]: ("v", d["esperado"]) for d in h["diferencias"]
                  if d["columna"] not in reglas.ACUMULADOS}
    celdas.update(_celdas_acumulados(h, hoja, wb_formulas))
    return celdas


def _marcar_recalculo(z, contenido):
    """fullCalcOnLoad en workbook.xml y fuera calcChain (Excel lo rehace).
    Se edita con lxml, no con expresiones regulares."""
    wb = etree.fromstring(z.read(RUTA_WORKBOOK))
    calc = wb.find(_q("calcPr"))
    if calc is None:
        calc = etree.SubElement(wb, _q("calcPr"))
    calc.set("fullCalcOnLoad", "1")
    contenido[RUTA_WORKBOOK] = etree.tostring(wb, xml_declaration=True, encoding="UTF-8", standalone=True)

    rels = etree.fromstring(z.read(RUTA_WORKBOOK_RELS))
    for rel in rels.findall(f"{{{NS_PKG_REL}}}Relationship"):
        if rel.get("Target", "").endswith("calcChain.xml"):
            rels.remove(rel)
    contenido[RUTA_WORKBOOK_RELS] = etree.tostring(rels, xml_declaration=True, encoding="UTF-8", standalone=True)

    tipos = etree.fromstring(z.read(RUTA_TIPOS))
    for ov in tipos.findall(f"{{{NS_TIPOS}}}Override"):
        if ov.get("PartName") == "/" + RUTA_CALCCHAIN:
            tipos.remove(ov)
    contenido[RUTA_TIPOS] = etree.tostring(tipos, xml_declaration=True, encoding="UTF-8", standalone=True)


def _llenar_dia(dia, hojas, wb_formulas, wb_valores, escritos):
    """Escribe un dia en las hojas; devuelve la lista de cambios."""
    fecha = dt.date.fromisoformat(dia["fecha"]) if isinstance(dia["fecha"], str) else dia["fecha"]
    cambios = []
    for hoja in reglas.HOJAS:
        h = dia["hojas"][hoja]
        if not h["fila"]:
            continue
        celdas = _celdas_a_escribir(h, hoja, wb_formulas, wb_valores, escritos, fecha)
        estilo = h["fila"] - 1 if h["nueva"] else None
        omitidas = [col for col, (tipo, valor) in celdas.items()
                    if not _escribir(hojas[hoja], h["fila"], col, tipo, valor, estilo_de=estilo)]
        escritos[(hoja, h["fila"])] = dict(celdas, _fecha=fecha)
        if celdas:
            cambios.append({
                "fecha": fecha.isoformat(), "hoja": hoja, "fila": h["fila"], "nueva": h["nueva"],
                "celdas": sorted(set(celdas) - set(omitidas), key=column_index_from_string),
                "omitidas": omitidas,
            })
    return cambios


def llenar(xlsx_bytes, dias, wb_formulas, wb_valores):
    """Devuelve (bytes del CONTABILIDAD lleno, lista de cambios por dia/hoja)."""
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    rutas = _rutas_hojas(z)
    hojas = {h: _Hoja(etree.fromstring(z.read(rutas[h]))) for h in reglas.HOJAS}
    escritos, cambios = {}, []
    for dia in dias:
        cambios.extend(_llenar_dia(dia, hojas, wb_formulas, wb_valores, escritos))
    contenido = {
        rutas[h]: etree.tostring(hojas[h].raiz, xml_declaration=True, encoding="UTF-8", standalone=True)
        for h in reglas.HOJAS
    }
    _marcar_recalculo(z, contenido)
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as out:
        for info in z.infolist():
            if info.filename == RUTA_CALCCHAIN:
                continue
            datos = contenido.get(info.filename, z.read(info.filename))
            out.writestr(info, datos, compress_type=zipfile.ZIP_DEFLATED)
    return salida.getvalue(), cambios
