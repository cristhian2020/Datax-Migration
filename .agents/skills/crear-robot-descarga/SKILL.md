---
name: crear-robot-descarga
description: Guía completa y acelerada para implementar robots de descarga de los 4 tipos oficiales (Tipo I, II, III, IV) en DATAX Platform con Playwright, Requests y BeautifulSoup.
---

# 📥 Skill: Crear Robot de Descarga (Tipos I, II, III y IV)

Esta skill guía el desarrollo integral de robots de descarga en `data-processing-modules`. Los robots de descarga interactúan con portales web, repositorios o APIs externas para obtener archivos fuente e identificar novedades temporales.

---

## 🎯 1. Matriz de Decisión: ¿Qué Tipo de Robot Elegir?

| Tipo | Métodos Requeridos | Cuándo Usarlo | Test Unitario |
| :--- | :--- | :--- | :--- |
| **Tipo I** | `get_file_url()`<br>`compare_files()` | El portal tiene links directos a archivos (`.xlsx`, `.pdf`, `.zip`). La plataforma DATAX descarga físicamente los archivos y el robot inspecciona su contenido interno para validar la fecha. | `test_download_type_i.py` |
| **Tipo II** | `verify_download()`<br>`compare_files()` | El robot necesita descargar físicamente los archivos (por sesiones, cookies, payloads POST o descargas por click en navegador) y luego filtra novedades en `compare_files()`. | `test_download_type_ii.py` |
| **Tipo III** | `check_new_data()` | **El más versátil y común**: APIs REST, endpoints históricos con rangos de fechas (ej. cotizaciones BCB), paginaciones complejas o cuando la descarga y validación ocurren en un solo ciclo. | `test_download_type_iii.py` |
| **Tipo IV** | `get_data()` | Descarga en lote donde todos los archivos nuevos se guardan en `tmp/` con prefijo de fecha estricto `YYYY-MM-DD_...`. Retorna la ruta del directorio temporal. | `test_download_type_iv.py` |

---

## 🏗️ 2. Arquitectura General y Convención de Nombres

1. **Nombre de Clase y Alias**:
   ```python
   try:
       from models.download import Download_Base
   except ImportError:
       Download_Base = object

   class D_BO_000000481(Download_Base):
       # Métodos del tipo elegido
       pass

   Robot = D_BO_000000481  # Alias obligatorio para el test harness
   ```

2. **Recreación Limpia de `tmp/`**:
   Siempre que el robot guarde archivos locales, debe limpiar la carpeta `tmp/`:
   ```python
   tmp_dir = os.path.join(path, "tmp")
   if os.path.exists(tmp_dir):
       shutil.rmtree(tmp_dir)
   os.makedirs(tmp_dir, exist_ok=True)
   ```

3. **Criterio de Novedad Temporal**:
   - Condición estricta: `fecha_archivo > updated_to`.
   - Formato estándar de fecha: `YYYY-MM-DD`.

---

## 💻 3. Plantillas de Código por Tipo

### 🔹 Plantilla Tipo I (Descarga Asistida por Plataforma)
```python
import os
import re
import traceback
from playwright.sync_api import sync_playwright
from download_tools import format_date, month_to_number

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000000(Download_Base):

    def get_file_url(self, main_url: str, updated_to: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        """Recolecta URLs directas de descarga desde el portal."""
        try:
            urls = []
            with sync_playwright() as pl:
                browser = pl.chromium.launch(headless=True)
                page = browser.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
                page.goto(main_url, wait_until="load", timeout=60000)

                # Extraer enlaces que apunten a archivos
                links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                browser.close()

            file_pattern = re.compile(r"\.(xlsx|xls|pdf|zip)(\?|$)", re.IGNORECASE)
            for link in links:
                if file_pattern.search(link) and link not in urls:
                    urls.append(link)

            return urls
        except Exception as e:
            print(f"Error al obtener URLs: {e}")
            traceback.print_exc()
            return []

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        """
        Recibe [{'tmp_path': '...', 'download_url': '...'}] descargados por la plataforma.
        Filtra aquellos cuya fecha interna sea estrictamente posterior a updated_to.
        """
        try:
            reference_date = format_date(updated_to, format)
            verified = []

            for item in files_paths:
                file_path = item["tmp_path"]
                
                # Extraer fecha interna (ejemplo desde nombre o contenido)
                # m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(file_path))
                # ...
                file_date = ... # objeto datetime

                if file_date and file_date > reference_date:
                    verified.append({
                        "tmp_path": file_path,
                        "updated_to": file_date.strftime(format),
                        "download_url": item["download_url"]
                    })

            return verified if verified else False
        except Exception as e:
            print(f"Error en compare_files: {e}")
            return False

Robot = D_BO_000000000
```

---

### 🔹 Plantilla Tipo II (Descarga Controlada por Robot + Comparación)
```python
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


class D_BO_000000000(Download_Base):

    def verify_download(self, main_url: str, updated_to: str, path: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        """Descarga archivos a <path>/tmp y retorna [{'tmp_path': ..., 'download_url': ...}]."""
        tmp_dir = os.path.join(path, "tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        downloaded = []
        try:
            # 1. Obtener URLs o realizar navegación
            # 2. Descargar cada archivo en tmp_dir
            # local_file = os.path.join(tmp_dir, filename)
            # downloaded.append({'tmp_path': local_file, 'download_url': url})
            return downloaded
        except Exception as e:
            print(f"Error en verify_download: {e}")
            return []

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        """Filtra archivos de verify_download y retorna [{'tmp_path', 'updated_to', 'download_url'}]."""
        ref_date = format_date(updated_to, format)
        results = []
        for item in files_paths:
            # Extraer fecha interna
            file_date = ...
            if file_date and file_date > ref_date:
                item_copy = dict(item)
                item_copy["updated_to"] = file_date.strftime(format)
                results.append(item_copy)
        return results if results else False

Robot = D_BO_000000000
```

---

### 🔹 Plantilla Tipo III (Pipeline Integrado / APIs / Scraping Avanzado)
```python
import os
import re
import shutil
from datetime import datetime
import pandas as pd
import requests
from download_tools import format_date, month_to_number

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000000(Download_Base):

    def check_new_data(self, main_url: str, updated_to: str, path: str, key_words: str = None, format: str = "%Y-%m-%d") -> list:
        """
        Orquesta consulta a API / scraping, descarga/generación y validación de fecha.
        Retorna: [{'tmp_path': ..., 'updated_to': ..., 'download_url': ...}]
        """
        tmp_dir = os.path.join(path, "tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        try:
            ref_date = format_date(updated_to, format)
            results = []

            # 1. Consultar endpoint o navegar con Playwright
            # 2. Guardar archivos que superen ref_date
            # target_file = os.path.join(tmp_dir, "archivo.xlsx")
            # results.append({
            #     "tmp_path": target_file,
            #     "updated_to": latest_date.strftime(format),
            #     "download_url": main_url
            # })

            return results
        except Exception as e:
            print(f"Error en check_new_data: {e}")
            return []

Robot = D_BO_000000000
```

---

### 🔹 Plantilla Tipo IV (Descarga con Prefijo de Fecha `YYYY-MM-DD_...`)
```python
import os
import shutil
import re
from download_tools import format_date

try:
    from models.download import Download_Base
except ImportError:
    Download_Base = object


class D_BO_000000000(Download_Base):

    def get_data(self, main_url: str, path: str, updated_to: str, format: str = "%Y-%m-%d") -> str:
        """
        Descarga archivos nuevos a <path>/tmp nombrándolos con prefijo 'YYYY-MM-DD_...'.
        Retorna la ruta string de la carpeta temporal: <path>/tmp.
        """
        tmp_dir = os.path.join(path, "tmp")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir)
        os.makedirs(tmp_dir, exist_ok=True)

        ref_date = format_date(updated_to, format)

        # Cada archivo descargado DEBE llamarse: f"{file_date_iso}_{nombre_archivo}.ext"
        # Ejemplo: os.path.join(tmp_dir, f"2026-07-31_reporte.xlsx")

        return tmp_dir

Robot = D_BO_000000000
```

---

## ⚡ 4. Técnicas y Patrones Clave de Descarga

### A. Extraer Fechas de Archivos Excel sin cargar la hoja entera
```python
from openpyxl import load_workbook

wb = load_workbook(file_path, read_only=True, data_only=True)
ws = wb.active
for row in ws.iter_rows(min_row=1, max_row=15, max_col=10, values_only=True):
    for val in row:
        if val:
            # Buscar patrones con regex o isinstance(val, datetime)
            pass
wb.close()
```

### B. Extraer Fechas en Español desde PDFs
```python
from download_tools import text_extract, month_to_number

lines = text_extract(pdf_path)
for line in lines:
    m = re.search(r"(\d{1,2})\s+de\s+([A-Za-z]+)\s+de\s+(\d{4})", line, re.IGNORECASE)
    if m:
        day = int(m.group(1))
        month = month_to_number(m.group(2).lower())
        year = int(m.group(3))
        # Fecha obtenida
```

### C. Manejo de Archivos ZIP
Si el portal publica archivos `.zip`:
```python
import zipfile

with zipfile.ZipFile(zip_path, 'r') as archive:
    excel_candidates = [n for n in archive.namelist() if n.lower().endswith(('.xlsx', '.xls'))]
    if excel_candidates:
        target = os.path.join(os.path.dirname(zip_path), os.path.basename(excel_candidates[0]))
        with archive.open(excel_candidates[0]) as src, open(target, 'wb') as dst:
            dst.write(src.read())
        # Ahora trabajar con target
```

---

## 🧪 5. Pruebas Locales

1. Configurar en el archivo de prueba correspondiente:
   - `MAIN_URL = 'https://portal.ejemplo.gob.bo/reportes'`
   - `UPDATED_TO = '2025-12-31'` (fecha de referencia para forzar la detección de archivos nuevos).

2. Ejecutar la prueba:
   ```bash
   # Tipo I:
   python -m unittest test_download_type_i.py

   # Tipo II:
   python -m unittest test_download_type_ii.py

   # Tipo III:
   python -m unittest test_download_type_iii.py

   # Tipo IV:
   python -m unittest test_download_type_iv.py
   ```

3. Ejecutar el validador oficial:
   ```bash
   python validate_robot.py
   ```
