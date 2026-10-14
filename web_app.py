"""
Interfaz (Flask) de Validaciones Karina. Capa fina: valida el request y
llama a `karina.validador`; las reglas viven en `karina.reglas`.

Flujo: login con las credenciales de OpenCorp (se valida en ese momento
contra OpenCorp) -> subir Caja 3 + CONTABILIDAD -> elegir fecha o rango
-> tabla de diferencias por dia y pestaña.

Uso local:
    python web_app.py
"""
import datetime as dt
import io
import os
import secrets
import sys
import tempfile
from pathlib import Path

from flask import Flask, abort, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_wtf import CSRFProtect
from flask_wtf.csrf import CSRFError

from karina import excel_io, llenado, reglas, reporte, validador
from karina.opencorp_scraper import OpenCorpScraperError


def _base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent


_BASE_DIR = _base_dir()
app = Flask(__name__, template_folder=str(_BASE_DIR / "templates"), static_folder=str(_BASE_DIR / "static"))
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # Caja 3 ~6 MB, CONTABILIDAD ~2 MB
# Igual que en Empresa_no_pago: el token CSRF no vence mientras viva la sesion
# (quien deja la ventana abierta mas de 1 h no debe recibir un 400).
app.config["WTF_CSRF_TIME_LIMIT"] = None
csrf = CSRFProtect(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

# sesion_id -> scraper ya autenticado. Solo en memoria: el password nunca
# va a la cookie ni a disco. Herramienta local de un solo usuario.
SCRAPERS = {}
UPLOAD_DIR = Path(tempfile.mkdtemp(prefix="karina_"))
# token -> libros abiertos, registros de OpenCorp y Excel generado de la
# ultima validacion de la sesion (en memoria; se reemplaza al validar otra vez).
VALIDACIONES = {}
MAX_DIAS = 31
PLANTILLA_LOGIN = "login.html"


def _error_sesion():
    return jsonify({"error": "La sesión caducó. Recarga la página (F5) e inicia sesión de nuevo."}), 401


@app.errorhandler(CSRFError)
def csrf_invalido(e):
    return jsonify({"error": "La sesión caducó. Recarga la página (F5) y vuelve a intentar."}), 400


@app.before_request
def requerir_login():
    if request.endpoint in (None, "login", "static"):
        return
    if session.get("sesion_id") not in SCRAPERS:
        if request.path.startswith("/api/"):
            return _error_sesion()
        return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        if not email or not password:
            return render_template(PLANTILLA_LOGIN, error="Usuario y contraseña son obligatorios.")
        try:
            scraper = validador.conectar(email, password)
        except OpenCorpScraperError as e:
            return render_template(PLANTILLA_LOGIN, error=str(e))
        except Exception as e:  # red caida, OpenCorp fuera de linea
            return render_template(PLANTILLA_LOGIN, error=f"No se pudo conectar con OpenCorp: {e}")
        sesion_id = secrets.token_urlsafe(16)
        SCRAPERS[sesion_id] = scraper
        session["sesion_id"] = sesion_id
        session["usuario"] = email
        return redirect(url_for("index"))
    return render_template(PLANTILLA_LOGIN, error=None)


@app.route("/logout", methods=["GET"])
def logout():
    SCRAPERS.pop(session.get("sesion_id"), None)
    VALIDACIONES.pop(session.get("reporte"), None)
    session.clear()
    return redirect(url_for("login"))


@app.route("/", methods=["GET"])
def index():
    ayer = dt.date.today() - dt.timedelta(days=1)
    if ayer.weekday() == 6:  # domingo no hay cobro
        ayer -= dt.timedelta(days=1)
    return render_template("index.html", usuario=session.get("usuario"), fecha_defecto=ayer.isoformat())


def _guardar(archivo, nombre):
    destino = UPLOAD_DIR / f"{secrets.token_hex(4)}_{nombre}"
    archivo.save(destino)
    return destino


def _fechas(desde, hasta):
    n = (hasta - desde).days
    return [desde + dt.timedelta(d) for d in range(n + 1) if (desde + dt.timedelta(d)).weekday() != 6]


@app.route("/api/validar", methods=["POST"])
def api_validar():
    caja3 = request.files.get("caja3")
    contab = request.files.get("contabilidad")
    if not caja3 or not caja3.filename or not contab or not contab.filename:
        return jsonify({"error": "Sube los dos archivos: Caja 3 y CONTABILIDAD."}), 400
    try:
        desde = dt.date.fromisoformat(request.form["desde"])
        hasta = dt.date.fromisoformat(request.form.get("hasta") or request.form["desde"])
    except (KeyError, ValueError):
        return jsonify({"error": "Fecha inválida."}), 400
    if hasta < desde:
        return jsonify({"error": "La fecha final es anterior a la inicial."}), 400
    if (hasta - desde).days >= MAX_DIAS:
        return jsonify({"error": f"El rango máximo es de {MAX_DIAS} días."}), 400

    rutas = [_guardar(caja3, "caja3.xlsm"), _guardar(contab, "contabilidad.xlsx")]
    try:
        try:
            wb_caja3 = excel_io.abrir(rutas[0])
            wb_contab = excel_io.abrir(rutas[1])
            wb_contab_f = excel_io.abrir_formulas(rutas[1])
        except Exception as e:
            return jsonify({"error": f"No se pudo abrir uno de los Excel: {e}"}), 400
        faltan = [h for h in ("JPMOTO", "RICARMOTO") if h not in wb_caja3.sheetnames]
        faltan += [h for h in ("JP", "RC") if h not in wb_contab.sheetnames]
        if faltan:
            return jsonify({"error": f"Faltan pestañas: {', '.join(faltan)}. ¿Subiste los archivos en el orden correcto?"}), 400

        scraper = SCRAPERS[session["sesion_id"]]
        registros = {}
        for f in _fechas(desde, hasta):
            try:
                registros[f] = validador.recaudo_general(scraper, f)
            except OpenCorpScraperError as e:
                return jsonify({"error": f"OpenCorp respondió con error para {f}: {e}"}), 502
        nombre = f"Validacion_JP_RC_{desde.isoformat()}" + (f"_a_{hasta.isoformat()}" if hasta != desde else "") + ".xlsx"
        # Se guarda lo necesario para recalcular cuando Karina responda el
        # alquiler de los dias de comite, sin volver a subir ni consultar.
        token = secrets.token_urlsafe(12)
        VALIDACIONES.pop(session.get("reporte"), None)
        VALIDACIONES[token] = {
            "libros": (wb_caja3, wb_contab, wb_contab_f),
            "registros": registros,
            "encabezados": excel_io.leer_encabezados(wb_contab, ("JP", "RC")),
            "nombre": nombre,
            # bytes originales: el CONTABILIDAD lleno se arma sobre ellos
            "contabilidad": rutas[1].read_bytes(),
            "nombre_contabilidad": f"CONTABILIDAD_llena_{hasta.isoformat()}.xlsx",
        }
        session["reporte"] = token
        return jsonify(_validar_guardado(token, {}))
    finally:
        for r in rutas:
            try:
                r.unlink()
            except OSError:
                pass


def _validar_guardado(token, respuestas):
    """Corre la validacion con los datos guardados del token y regenera el
    Excel de reporte y el CONTABILIDAD lleno.
    `respuestas` = {"AAAA-MM-DD": {"JP": valor, "RC": valor}}."""
    datos = VALIDACIONES[token]
    wb_caja3, wb_contab, wb_contab_f = datos["libros"]
    fechas = list(datos["registros"])
    resp = {dt.date.fromisoformat(k): v for k, v in respuestas.items()}
    dias = validador.validar_rango(fechas, datos["registros"], wb_caja3, wb_contab, wb_contab_f, resp)
    datos["excel"] = reporte.generar_excel(dias, datos["encabezados"])
    datos["excel_contabilidad"], cambios = llenado.llenar(datos["contabilidad"], dias, wb_contab_f, wb_contab)
    for d in dias:
        d["fecha"] = d["fecha"].isoformat()
    return {
        "dias": dias, "token": token, "cambios": cambios,
        "descarga": url_for("descargar", token=token),
        "descarga_contabilidad": url_for("descargar_contabilidad", token=token),
    }


def _leer_respuestas(cuerpo):
    respuestas = {}
    for fecha, por_hoja in (cuerpo or {}).items():
        dt.date.fromisoformat(fecha)
        respuestas[fecha] = {}
        for hoja, valor in (por_hoja or {}).items():
            if hoja not in ("JP", "RC") or valor in (None, ""):
                continue
            respuestas[fecha][hoja] = reglas.leer_monto(valor)
    return respuestas


@app.route("/api/alquiler-comite/<token>", methods=["POST"])
def api_alquiler_comite(token):
    if token not in VALIDACIONES or session.get("reporte") != token:
        return jsonify({"error": "La validación ya no está disponible. Vuelve a validar."}), 404
    try:
        respuestas = _leer_respuestas((request.get_json(silent=True) or {}).get("respuestas"))
    except (ValueError, TypeError, AttributeError):
        return jsonify({"error": "Valor de alquiler inválido: usa solo números."}), 400
    return jsonify(_validar_guardado(token, respuestas))


@app.route("/descargar-contabilidad/<token>", methods=["GET"])
def descargar_contabilidad(token):
    if token not in VALIDACIONES or session.get("reporte") != token:
        abort(404)
    datos = VALIDACIONES[token]
    return send_file(io.BytesIO(datos["excel_contabilidad"]), as_attachment=True,
                     download_name=datos["nombre_contabilidad"],
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/descargar/<token>", methods=["GET"])
def descargar(token):
    if token not in VALIDACIONES or session.get("reporte") != token:
        abort(404)
    datos = VALIDACIONES[token]
    return send_file(io.BytesIO(datos["excel"]), as_attachment=True, download_name=datos["nombre"],
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


if __name__ == "__main__":
    # Solo desarrollo: debug si KARINA_DEBUG=1 (el .exe usa desktop_app.py).
    app.run(debug=os.environ.get("KARINA_DEBUG") == "1", port=5050)
