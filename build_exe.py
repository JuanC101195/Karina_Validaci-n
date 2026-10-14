"""
Script de automatización para compilar Validaciones Karina en un ejecutable (.exe) de escritorio nativo con PyInstaller.

Uso:
    python build_exe.py
"""

import os
import shutil
import sys
from pathlib import Path
import PyInstaller.__main__

def build():
    root_dir = Path(__file__).resolve().parent
    dist_dir = root_dir / "dist"
    build_dir = root_dir / "build"

    print("=======================================================")
    print(" Compilando Validaciones Karina - App de escritorio")
    print("=======================================================")

    # Limpiar compilaciones anteriores si existen
    if dist_dir.exists():
        shutil.rmtree(dist_dir, ignore_errors=True)
    if build_dir.exists():
        shutil.rmtree(build_dir, ignore_errors=True)

    templates_src = str(root_dir / "templates")
    static_src = str(root_dir / "static")

    # Separador de rutas para --add-data (';' en Windows, ':' en Linux/Mac)
    sep = ";" if sys.platform.startswith("win") else ":"

    pyinstaller_args = [
        str(root_dir / "desktop_app.py"),
        "--name=ValidacionesKarina",
        "--onefile",
        "--noconsole",
        f"--add-data={templates_src}{sep}templates",
        f"--add-data={static_src}{sep}static",
        "--hidden-import=karina",
        "--hidden-import=karina.reglas",
        "--hidden-import=karina.excel_io",
        "--hidden-import=karina.validador",
        "--hidden-import=karina.opencorp_scraper",
        "--hidden-import=openpyxl",
        "--hidden-import=clr_loader",
        "--hidden-import=webview",
        "--clean",
    ]

    icon_path = root_dir / "static" / "app_icon.ico"
    if icon_path.exists():
        pyinstaller_args.append(f"--icon={icon_path}")
        print(f"[*] Icono personalizado detectado: {icon_path.name}")

    print("[*] Ejecutando PyInstaller...")
    PyInstaller.__main__.run(pyinstaller_args)

    exe_path = dist_dir / "ValidacionesKarina.exe"
    if exe_path.exists():
        size_mb = exe_path.stat().st_size / (1024 * 1024)
        print("\n=======================================================")
        print(f" ¡Compilación Exitosa!")
        print(f" Ejecutable generado en: {exe_path}")
        print(f" Tamaño: {size_mb:.2f} MB")
        print("=======================================================")
    else:
        print("\n[!] Error: No se encontró el ejecutable en dist/.")

if __name__ == "__main__":
    build()
