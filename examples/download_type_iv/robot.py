# -*- coding: utf-8 -*-
"""Ejemplo de Robot de Descarga Tipo IV para DATAX Platform.

En Tipo IV:
- get_data: Recrea <path>/tmp, descarga los archivos nuevos y NOMBRA cada archivo
  obligatoriamente con la fecha al inicio: 'YYYY-MM-DD_nombre.ext'.
  Retorna la cadena con la ruta del directorio temporal: tmp_path.
"""
import os
import re
import shutil
import traceback
from download_tools import format_date

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000004(Download_Base):
    """Robot de descarga Tipo IV por lote con archivos prefijados por fecha."""

    def get_data(self, main_url: str, path: str, updated_to: str, format: str = "%Y-%m-%d") -> str:
        tmp_dir = os.path.join(path, "tmp")
        try:
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir)
            os.makedirs(tmp_dir, exist_ok=True)

            reference_date = format_date(updated_to, format)

            # En una implementación real:
            # 1. Navegar y descargar archivos nuevos (fecha > reference_date)
            # 2. Guardar en tmp_dir con nomenclatura estricta:
            #    ej: os.path.join(tmp_dir, f"{fecha_iso}_{nombre_archivo}.xlsx")
            # 3. Retornar la ruta del directorio tmp_dir como string

            return tmp_dir
        except Exception as error:
            print(f"Error en get_data: {error}")
            traceback.print_exc()
            return tmp_dir


Robot = D_BO_000000004
