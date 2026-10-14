"""
CLI de Validaciones Karina.

    python validar.py --caja3 "CAJA 3.xlsm" --contabilidad CONTABILIDAD.xlsx --fecha 2026-10-13
    python validar.py ... --desde 2026-10-01 --hasta 2026-10-13 --out validacion.xlsx
"""
import argparse
import datetime as dt
import sys

from karina import excel_io, llenado, reglas, reporte, validador


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


def main(argv=None):
    p = argparse.ArgumentParser(description="Valida las pestañas JP y RC de CONTABILIDAD contra OpenCorp y Caja 3")
    p.add_argument("--caja3", required=True, help="CAJA 3.xlsm (Diskstation)")
    p.add_argument("--contabilidad", required=True, help="CONTABILIDAD.xlsx descargado del Drive")
    p.add_argument("--fecha", type=_fecha)
    p.add_argument("--desde", type=_fecha)
    p.add_argument("--hasta", type=_fecha)
    p.add_argument("--out", help="ruta del Excel de salida con las pestañas JP y RC")
    p.add_argument("--out-contabilidad", help="ruta del CONTABILIDAD lleno (copia del subido con JP/RC escritos)")
    p.add_argument("--alquiler-comite", action="append", default=[], metavar="AAAA-MM-DD:HOJA=VALOR",
                   help="alquiler total del dia de comite (la diferencia con Caja 3 es la inversion en motos); repetible")
    args = p.parse_args(argv)

    if args.fecha:
        fechas = [args.fecha]
    elif args.desde and args.hasta:
        n = (args.hasta - args.desde).days
        # Domingos fuera: no hay cobro (OpenCorp responde 'sin').
        fechas = [args.desde + dt.timedelta(d) for d in range(n + 1) if (args.desde + dt.timedelta(d)).weekday() != 6]
    else:
        p.error("use --fecha o --desde/--hasta")

    alquileres = {}
    for item in args.alquiler_comite:
        try:
            fecha, resto = item.split(":", 1)
            hoja, valor = resto.split("=", 1)
            alquileres.setdefault(_fecha(fecha), {})[hoja.strip().upper()] = reglas.leer_monto(valor)
        except ValueError:
            p.error(f"--alquiler-comite invalido: {item!r} (ej. 2026-10-09:JP=0)")

    email, password = validador.cargar_credenciales()
    scraper = validador.conectar(email, password)
    wb_caja3 = excel_io.abrir(args.caja3)
    wb_contab = excel_io.abrir(args.contabilidad)
    wb_contab_f = excel_io.abrir_formulas(args.contabilidad)
    registros = {f: validador.recaudo_general(scraper, f) for f in fechas}
    dias = validador.validar_rango(fechas, registros, wb_caja3, wb_contab, wb_contab_f, alquileres)
    for res in dias:
        imprimir(res)
    if args.out_contabilidad:
        with open(args.contabilidad, "rb") as fh:
            datos, cambios = llenado.llenar(fh.read(), dias, wb_contab_f, wb_contab)
        with open(args.out_contabilidad, "wb") as fh:
            fh.write(datos)
        for c in cambios:
            print(f"  {c['fecha']} {c['hoja']} fila {c['fila']}{' (nueva)' if c['nueva'] else ''}: {len(c['celdas'])} celdas -> {', '.join(c['celdas'])}")
        print(f"\nCONTABILIDAD lleno: {args.out_contabilidad}")
    if args.out:
        encabezados = excel_io.leer_encabezados(wb_contab, ("JP", "RC"))
        with open(args.out, "wb") as fh:
            fh.write(reporte.generar_excel(dias, encabezados))
        print(f"\nExcel generado: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
