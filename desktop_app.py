"""
Lanzador de escritorio nativo (PyWebView + Flask) para Validaciones Karina.

Este archivo inicia el servidor Flask localmente en un puerto dinámico libre
y despliega una ventana nativa de escritorio (Edge WebView2 en Windows).
"""

import sys
import os
import socket
import threading
from pathlib import Path
import webview

# Asegurar que el directorio raíz esté en sys.path cuando se ejecuta congelado (PyInstaller)
if getattr(sys, 'frozen', False):
    bundle_dir = Path(sys._MEIPASS)
    sys.path.insert(0, str(bundle_dir))
else:
    bundle_dir = Path(__file__).resolve().parent

from web_app import app

def find_free_port():
    """Encuentra un puerto TCP libre en localhost para evitar colisiones."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_server(port):
    """Ejecuta el servidor Flask en segundo plano."""
    import logging
    log = logging.getLogger('werkzeug')
    log.setLevel(logging.ERROR)
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)

def parchear_extension_descargas():
    """
    Bug real corregido 2026-10-01 (reportado por el usuario, "falla el .exe
    cuando le doy Descargar TODO"): el dialogo "Guardar" de pywebview en
    Windows (EdgeChrome.on_download_starting) usa el filtro "Todos los
    archivos (*.*)" sin extension por defecto -- si el usuario le cambia
    el nombre (ej. "TODO_COMBINADO monteria"), el archivo queda guardado
    SIN `.xlsx` y Excel no lo reconoce (caso real en Descargas del
    usuario). Se envuelve el handler original para volver a pegar la
    extension del archivo servido si el nombre elegido no la trae.
    """
    try:
        from webview.platforms import edgechromium
    except Exception:
        return  # otra plataforma/backend: no aplica

    original = edgechromium.EdgeChrome.on_download_starting

    def on_download_starting(self, sender, args):
        extension = os.path.splitext(args.ResultFilePath)[1]
        original(self, sender, args)
        if args.Cancel or not extension:
            return
        if not args.ResultFilePath.lower().endswith(extension.lower()):
            args.ResultFilePath = args.ResultFilePath + extension

    edgechromium.EdgeChrome.on_download_starting = on_download_starting


def main():
    port = find_free_port()

    # Iniciar Flask en un hilo demonio en segundo plano
    server_thread = threading.Thread(target=run_server, args=(port,), daemon=True)
    server_thread.start()

    url = f"http://127.0.0.1:{port}"

    # Bug real corregido 2026-09-29 (reportado por el usuario, "no
    # descarga nada" con el .exe ya compilado): pywebview bloquea las
    # descargas por defecto (webview.settings['ALLOW_DOWNLOADS'] es False
    # de fabrica) -- sin esto, cualquier click en un boton "Descargar"
    # (Excel/CSV) no hace nada, sin error visible en consola.
    webview.settings['ALLOW_DOWNLOADS'] = True
    parchear_extension_descargas()

    # Crear la ventana nativa de escritorio con PyWebView
    webview.create_window(
        title="Validaciones Karina",
        url=url,
        width=1280,
        height=850,
        min_size=(960, 640),
        resizable=True,
        confirm_close=False,
        # Bug real corregido 2026-09-30 (reportado por el usuario, "no me
        # deja copiar la placa para pegarla en el CRM"): pywebview
        # desactiva la seleccion de texto por defecto (text_select=False
        # de fabrica) -- sin poder seleccionar texto, Ctrl+C/click derecho
        # no tienen nada que copiar. Mismo tipo de bug que ALLOW_DOWNLOADS.
        text_select=True,
    )

    webview.start(private_mode=False)

if __name__ == "__main__":
    main()
