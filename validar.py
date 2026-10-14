"""
CLI de Validaciones Karina.

    python validar.py --caja3 "CAJA 3.xlsm" --contabilidad CONTABILIDAD.xlsx --fecha 2026-10-13
    python validar.py ... --desde 2026-10-01 --hasta 2026-10-13
"""
import argparse
import datetime as dt
import sys

from karina import excel_io, validador


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
        marca = " [comite]" if h["comite"] else ""
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
    args = p.parse_args(argv)

    if args.fecha:
        fechas = [args.fecha]
    elif args.desde and args.hasta:
        n = (args.hasta - args.desde).days
        # Domingos fuera: no hay cobro (OpenCorp responde 'sin').
        fechas = [args.desde + dt.timedelta(d) for d in range(n + 1) if (args.desde + dt.timedelta(d)).weekday() != 6]
    else:
        p.error("use --fecha o --desde/--hasta")

    email, password = validador.cargar_credenciales()
    scraper = validador.conectar(email, password)
    wb_caja3 = excel_io.abrir(args.caja3)
    wb_contab = excel_io.abrir(args.contabilidad)
    for f in fechas:
        registros = validador.recaudo_general(scraper, f)
        imprimir(validador.validar_fecha(f, registros, wb_caja3, wb_contab))
    return 0


if __name__ == "__main__":
    sys.exit(main())
