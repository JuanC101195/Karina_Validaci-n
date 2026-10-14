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

## App de escritorio

```
pip install -r requirements-exe.txt
python web_app.py        # desarrollo, http://127.0.0.1:5050
python build_exe.py      # genera dist/ValidacionesKarina.exe
```

Flujo: login con las credenciales de OpenCorp (se validan en ese momento), subir Caja 3 y CONTABILIDAD (la app lo LLENA: crea la fila del día si falta y corrige JP/RC; descarga "CONTABILIDAD llena", editando solo esas dos pestañas), elegir el rango de fechas, responder el alquiler total de los días de comité (Caja 3 trae alquiler + inversión en motos juntos), ver las diferencias por día y pestaña y descargar el Excel con las pestañas JP y RC (mismas columnas que CONTABILIDAD; las celdas en rojo no coinciden con lo digitado y tienen una nota con el valor que había; las columnas de fórmula quedan vacías). Los domingos se saltan y el rango máximo es de 31 días.

## Mapa

- `karina/reglas.py`: mapeo de columnas y reglas puras (se prueban sin archivos).
- `karina/excel_io.py`: lectura de Caja 3 y CONTABILIDAD.
- `karina/validador.py`: login en OpenCorp + validación de una fecha.
- `karina/reporte.py`: Excel de salida JP/RC.
- `karina/llenado.py`: escribe en CONTABILIDAD.xlsx editando solo el XML de JP/RC (conserva comentarios de Sheets y vínculos).
- `karina/opencorp_scraper.py`: copia del scraper de Empresa_no_pago.
- `web_app.py` (Flask) + `desktop_app.py` (PyWebView) + `build_exe.py` (PyInstaller): misma base que Empresa_no_pago.
