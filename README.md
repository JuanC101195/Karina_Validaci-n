# Validaciones Karina

Valida las pestañas **JP** y **RC** del Excel CONTABILIDAD (descargado del Drive) contra:

| Fuente | Columnas de CONTABILIDAD |
|---|---|
| OpenCorp `informe_recaudo_general` (login automático) | C–H efectivo, I–N multas, Q–V repuestos, Y prontos |
| `CAJA 3.xlsm` (hojas JPMOTO / RICARMOTO) | Z traslado, AA ajustes, AB alquiler, AC motos comité, AD gastos comité, AE retiro comité, AG caja 3, AJ saldo caja 3 |

Por ahora solo **reporta diferencias**; escribir en el Drive queda para cuando el archivo se convierta a Google Sheets.

## Uso

```
pip install -r requirements.txt
copy opencorp_creds.json.example opencorp_creds.json   # y poner email/password reales
python validar.py --caja3 "CAJA 3.xlsm" --contabilidad CONTABILIDAD.xlsx --fecha 2026-10-13
python validar.py --caja3 "CAJA 3.xlsm" --contabilidad CONTABILIDAD.xlsx --desde 2026-10-01 --hasta 2026-10-13
python -m pytest -q
```

## Mapa

- `karina/reglas.py`: mapeo de columnas y reglas puras (se prueban sin archivos).
- `karina/excel_io.py`: lectura de Caja 3 y CONTABILIDAD.
- `karina/validador.py`: login en OpenCorp + validación de una fecha.
- `karina/opencorp_scraper.py`: copia del scraper de Empresa_no_pago.
