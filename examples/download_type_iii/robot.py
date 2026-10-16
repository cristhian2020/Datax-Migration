# -*- coding: utf-8 -*-
"""Ejemplo de Robot de Descarga Tipo III para DATAX Platform.

En Tipo III:
- check_new_data: Orquestación completa en un único método.
  Limpia <path>/tmp, consulta el portal/API, descarga o genera el archivo y
  valida que la fecha sea mayor a updated_to.
  Retorna [{'tmp_path': ..., 'updated_to': ..., 'download_url': ...}].
"""
import os
import re
import shutil
import traceback
from datetime import datetime
import pandas as pd
import requests
from download_tools import format_date

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000003(Download_Base):
    """Robot de descarga Tipo III para APIs o scraping integrado."""

    def check_new_data(
        self,
        main_url: str,
        updated_to: str,
        path: str,
        key_words: str = None,
        format: str = "%Y-%m-%d",
    ) -> list:
        tmp_dir = os.path.join(path, "tmp")
        try:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            os.makedirs(tmp_dir, exist_ok=True)

            reference_date = format_date(updated_to, format)
            results = []

            # 1. Petición al endpoint / scraping con requests o Playwright
            # 2. Descargar o generar el archivo en tmp_dir
            # 3. Validar fecha_archivo > reference_date
            # target_file = os.path.join(tmp_dir, f"reporte_{latest_date}.xlsx")
            # results.append({
            #     "tmp_path": target_file,
            #     "updated_to": latest_date,
            #     "download_url": main_url,
            # })

            return results
        except Exception as error:
            print(f"Error en check_new_data: {error}")
            traceback.print_exc()
            return []


Robot = D_BO_000000003
