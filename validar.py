"""
CLI de Validaciones Karina.

    python validar.py --caja3 "CAJA 3.xlsm" --contabilidad CONTABILIDAD.xlsx --fecha 2026-10-13
    python validar.py ... --desde 2026-10-01 --hasta 2026-10-13 --out validacion.xlsx
"""
import argparse
import datetime as dt
import os
import sys

from karina import excel_io, llenado, reglas, reporte, validador

EXT_XLSX = ".xlsx"
EXT_XLSM = ".xlsm"
# Los Excel solo se leen y escriben dentro de la carpeta del usuario.
CARPETA_BASE = os.path.realpath(os.path.expanduser("~"))


class RutaInvalida(ValueError):
    pass


def _ruta_segura(texto, extensiones, debe_existir):
    """Ruta de un Excel dada por linea de comandos, validada justo antes de
    usarla: se resuelve (sin '..' ni enlaces), debe quedar dentro de la
    carpeta del usuario y tener la extension esperada (SonarCloud
    pythonsecurity:S8707, 2026-10-14)."""
    ruta = os.path.realpath(os.path.expanduser(texto))
    if not ruta.startswith(CARPETA_BASE + os.sep) or os.path.commonpath([CARPETA_BASE, ruta]) != CARPETA_BASE:
        raise RutaInvalida(f"{texto}: debe estar dentro de {CARPETA_BASE}")
    if os.path.splitext(ruta)[1].lower() not in extensiones:
        raise RutaInvalida(f"{texto}: se esperaba {' o '.join(extensiones)}")
    if debe_existir and not os.path.isfile(ruta):
        raise RutaInvalida(f"{texto}: no existe")
    return ruta


def _leer_bytes(texto, extensiones):
    ruta = _ruta_segura(texto, extensiones, True)
    with open(ruta, "rb") as fh:
        return fh.read()


def _escribir_bytes(texto, datos):
    ruta = _ruta_segura(texto, (EXT_XLSX,), False)
    with open(ruta, "wb") as fh:
        fh.write(datos)
    return ruta


def _fecha(texto):
    return dt.date.fromisoformat(texto)


def _fmt(v):
    return "(vacia)" if v is None else f"{v:,.2f}"


def imprimir(res):
    print(f"\n######## {res['fecha']}  ({res['registros']} registros OpenCorp)")
    for hoja, h in res["hojas"].items():
        if h["fila"] is None:
            print(f"== {hoja}: sin fila en CONTABILIDAD")
            continue
        if h.get("nueva"):
            print(f"== {hoja} fila {h['fila']}: FILA NUEVA, se llena completa")
            continue
        marca = " [comite]" if h["comite"] else ""
        if h.get("pregunta_alquiler") and h["pregunta_alquiler"]["pendiente"]:
            marca += f" [AB/AC pendientes: falta --alquiler-comite {res['fecha']}:{hoja}=VALOR, Caja 3 trae {h['pregunta_alquiler']['total']:,.2f}]"
        difs = h["diferencias"]
        print(f"== {hoja} fila {h['fila']}{marca}: " + ("CUADRA TODO" if not difs else f"{len(difs)} diferencias"))
        for d in difs:
            print(f"   {d['columna']:>3} {d['concepto']:<20} Excel={_fmt(d['excel']):>15}  Esperado={d['esperado']:>15,.2f}  dif={d['diferencia']:>+13,.2f}")
    for a in res["avisos"]:
        print(f"   ! {a}")


def _parser():
    p = argparse.ArgumentParser(description="Valida y llena las pestañas JP y RC de CONTABILIDAD con OpenCorp y Caja 3")
    p.add_argument("--caja3", required=True, help="CAJA 3.xlsm (Diskstation)")
    p.add_argument("--contabilidad", required=True, help="CONTABILIDAD.xlsx descargado del Drive")
    p.add_argument("--fecha", type=_fecha)
    p.add_argument("--desde", type=_fecha)
    p.add_argument("--hasta", type=_fecha)
    p.add_argument("--out", help="ruta del Excel de salida con las pestañas JP y RC")
    p.add_argument("--out-contabilidad", help="ruta del CONTABILIDAD lleno (copia del subido con JP/RC escritos)")
    p.add_argument("--alquiler-comite", action="append", default=[], metavar="AAAA-MM-DD:HOJA=VALOR",
                   help="alquiler total del dia de comite (la diferencia con Caja 3 es la inversion en motos); repetible")
    return p


def _fechas(args, p):
    if args.fecha:
        return [args.fecha]
    if not (args.desde and args.hasta):
        p.error("use --fecha o --desde/--hasta")
    n = (args.hasta - args.desde).days
    # Domingos fuera: no hay cobro (OpenCorp responde 'sin').
    return [args.desde + dt.timedelta(d) for d in range(n + 1) if (args.desde + dt.timedelta(d)).weekday() != 6]


def _alquileres(items, p):
    alquileres = {}
    for item in items:
        try:
            fecha, resto = item.split(":", 1)
            hoja, valor = resto.split("=", 1)
            alquileres.setdefault(_fecha(fecha), {})[hoja.strip().upper()] = reglas.leer_monto(valor)
        except ValueError:
            p.error(f"--alquiler-comite invalido: {item!r} (ej. 2026-10-09:JP=0)")
    return alquileres


def _guardar_contabilidad(args, contab_bytes, dias, wb_contab, wb_contab_f):
    if os.path.realpath(args.out_contabilidad) == os.path.realpath(args.contabilidad):
        raise RutaInvalida("--out-contabilidad no puede ser el mismo archivo de --contabilidad")
    datos, cambios = llenado.llenar(contab_bytes, dias, wb_contab_f, wb_contab)
    ruta = _escribir_bytes(args.out_contabilidad, datos)
    for c in cambios:
        nueva = " (nueva)" if c["nueva"] else ""
        print(f"  {c['fecha']} {c['hoja']} fila {c['fila']}{nueva}: {len(c['celdas'])} celdas -> {', '.join(c['celdas'])}")
    print(f"\nCONTABILIDAD lleno: {ruta}")


def main(argv=None):
    p = _parser()
    args = p.parse_args(argv)
    fechas = _fechas(args, p)
    alquileres = _alquileres(args.alquiler_comite, p)
    try:
        caja3_bytes = _leer_bytes(args.caja3, (EXT_XLSM, EXT_XLSX))
        contab_bytes = _leer_bytes(args.contabilidad, (EXT_XLSX,))
    except RutaInvalida as e:
        p.error(str(e))

    email, password = validador.cargar_credenciales()
    scraper = validador.conectar(email, password)
    wb_caja3 = excel_io.abrir_bytes(caja3_bytes)
    wb_contab = excel_io.abrir_bytes(contab_bytes)
    wb_contab_f = excel_io.abrir_bytes(contab_bytes, formulas=True)
    registros = {f: validador.recaudo_general(scraper, f) for f in fechas}
    dias = validador.validar_rango(fechas, registros, wb_caja3, wb_contab, wb_contab_f, alquileres)
    for res in dias:
        imprimir(res)
    try:
        if args.out_contabilidad:
            _guardar_contabilidad(args, contab_bytes, dias, wb_contab, wb_contab_f)
        if args.out:
            encabezados = excel_io.leer_encabezados(wb_contab, ("JP", "RC"))
            ruta = _escribir_bytes(args.out, reporte.generar_excel(dias, encabezados))
            print(f"\nExcel generado: {ruta}")
    except RutaInvalida as e:
        p.error(str(e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
