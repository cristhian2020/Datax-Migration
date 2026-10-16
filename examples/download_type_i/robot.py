# -*- coding: utf-8 -*-
"""Ejemplo de Robot de Descarga Tipo I para DATAX Platform.

En Tipo I:
- get_file_url: Retorna lista de URLs de descarga disponibles en el portal.
- compare_files: La plataforma ya descargó los archivos en tmp/. El robot inspecciona
  el contenido interno (Excel, PDF) y retorna solo aquellos con fecha > updated_to.
"""
import os
import re
import traceback
from playwright.sync_api import sync_playwright
from download_tools import format_date, month_to_number

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000001(Download_Base):
    """Robot de descarga Tipo I con Playwright y validación de fecha interna."""

    def get_file_url(self, main_url: str, updated_to: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        try:
            urls = []
            with sync_playwright() as pl:
                browser = pl.chromium.launch(headless=True)
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page.goto(main_url, wait_until="load", timeout=60000)
                links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                browser.close()

            file_pattern = re.compile(r"\.(xlsx|xls|pdf|zip)(\?|$)", re.IGNORECASE)
            for href in links:
                if file_pattern.search(href) and href not in urls:
                    urls.append(href)

            return urls
        except Exception as error:
            print(f"Error al obtener URLs: {error}")
            traceback.print_exc()
            return []

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        try:
            reference_date = format_date(updated_to, format)
            verified_files = []

            for item in files_paths:
                file_path = item["tmp_path"]
                filename = os.path.basename(file_path)

                # Estrategia 1: Fecha en nombre de archivo (ej. YYYY-MM-DD o DDMMYY)
                match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
                if match:
                    file_date = format_date(match.group(1), "%Y-%m-%d")
                else:
                    file_date = None

                if file_date and file_date > reference_date:
                    verified_files.append({
                        "tmp_path": file_path,
                        "updated_to": file_date.strftime(format),
                        "download_url": item["download_url"],
                    })

            return verified_files if verified_files else False
        except Exception as error:
            print(f"Error en compare_files: {error}")
            return False


Robot = D_BO_000000001
