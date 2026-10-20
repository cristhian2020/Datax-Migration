# -*- coding: utf-8 -*-
"""Ejemplo de Robot de Descarga Tipo II para DATAX Platform.

En Tipo II:
- verify_download: El robot descarga físicamente los archivos a <path>/tmp y retorna
  [{'tmp_path': ..., 'download_url': ...}].
- compare_files: Inspecciona los archivos descargados y retorna solo aquellos con fecha > updated_to.
"""
import os
import re
import shutil
import urllib.request
import traceback
from download_tools import format_date

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000002(Download_Base):
    """Robot de descarga Tipo II con descarga directa y posterior comparación."""

    def verify_download(self, main_url: str, updated_to: str, path: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        tmp_dir = os.path.join(path, "tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        downloaded_items = []
        try:
            # En un caso real: obtener lista de URLs y descargarlas en tmp_dir
            # Aquí ejemplificamos con un archivo simulado o descarga HTTP simple
            return downloaded_items
        except Exception as error:
            print(f"Error en verify_download: {error}")
            traceback.print_exc()
            return []

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        try:
            reference_date = format_date(updated_to, format)
            valid_files = []

            for item in files_paths:
                file_path = item["tmp_path"]
                filename = os.path.basename(file_path)

                match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
                file_date = format_date(match.group(1), "%Y-%m-%d") if match else None

                if file_date and file_date > reference_date:
                    enriched = dict(item)
                    enriched["updated_to"] = file_date.strftime(format)
                    valid_files.append(enriched)

            return valid_files if valid_files else False
        except Exception as error:
            print(f"Error en compare_files: {error}")
            return False


Robot = D_BO_000000002
