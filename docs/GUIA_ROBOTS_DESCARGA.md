# 📘 Guía Oficial de Desarrollo de Robots de Descarga - DATAX Platform

Los robots de descarga en DATAX obtienen archivos fuente de portales web, repositorios o APIs externas y comprueban si existen publicaciones nuevas posteriores a una fecha de referencia (`updated_to`).

Existen **4 Tipos Oficiales de Robots de Descarga**:

---

## 🎯 Resumen Comparativo de los 4 Tipos

| Tipo | Métodos en `Robot` | Flujo Principal | Salida esperada | Test Unitario |
| :--- | :--- | :--- | :--- | :--- |
| **Tipo I** | `get_file_url()`<br>`compare_files()` | El robot extrae URLs del portal. La plataforma DATAX descarga a `tmp/` y el robot inspecciona fechas internas. | `list[dict]` con `tmp_path`, `updated_to`, `download_url` | `test_download_type_i.py` |
| **Tipo II** | `verify_download()`<br>`compare_files()` | El robot descarga físicamente los archivos a `tmp/` (útil con cookies, auth o clicks) y luego filtra novedades. | `list[dict]` con `tmp_path`, `updated_to`, `download_url` | `test_download_type_ii.py` |
| **Tipo III** | `check_new_data()` | **Pipeline unificado**: Scraping/APIs complejas, generación dinámica de Excel/PDF/CSV y validación en un solo paso. | `list[dict]` con `tmp_path`, `updated_to`, `download_url` | `test_download_type_iii.py` |
| **Tipo IV** | `get_data()` | Descarga por lote en `tmp/` con nombres que comienzan obligatoriamente con la fecha ISO `YYYY-MM-DD_...`. | `str` (ruta de la carpeta `tmp/`) | `test_download_type_iv.py` |

---

## 📋 1. Especificación Detallada de Métodos

### 🔹 Tipo I: Descarga Asistida por Plataforma
```python
class D_BO_000000000(Download_Base):
    def get_file_url(self, main_url: str, updated_to: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        """
        Navega al portal y retorna lista de strings con las URLs directas de los archivos.
        Ej: ['https://portal.../doc1.xlsx', 'https://portal.../doc2.xlsx']
        """
        pass

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        """
        Recibe [{'tmp_path': '...', 'download_url': '...'}] descargados por la plataforma.
        Inspecciona el contenido interno o nombre de cada archivo y retorna solo aquellos con fecha > updated_to:
        [{'tmp_path': '...', 'updated_to': 'YYYY-MM-DD', 'download_url': '...'}]
        """
        pass

Robot = D_BO_000000000
```

### 🔹 Tipo II: Descarga por Robot + Comparación Posterior
```python
class D_BO_000000000(Download_Base):
    def verify_download(self, main_url: str, updated_to: str, path: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:
        """
        Recrea <path>/tmp, descarga los archivos y retorna:
        [{'tmp_path': '/path/tmp/archivo.xlsx', 'download_url': 'https://...'}]
        """
        pass

    def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:
        """
        Filtra la lista recibida y retorna aquellos con fecha > updated_to:
        [{'tmp_path': '...', 'updated_to': 'YYYY-MM-DD', 'download_url': '...'}]
        """
        pass

Robot = D_BO_000000000
```

### 🔹 Tipo III: Pipeline Integrado (APIs y Scraping Complejo)
```python
class D_BO_000000000(Download_Base):
    def check_new_data(self, main_url: str, updated_to: str, path: str, key_words: str = None, format: str = "%Y-%m-%d") -> list:
        """
        Recrea <path>/tmp, consulta la API/portal, guarda o genera los archivos y retorna:
        [{'tmp_path': '/path/tmp/archivo.xlsx', 'updated_to': 'YYYY-MM-DD', 'download_url': '...'}]
        """
        pass

Robot = D_BO_000000000
```

### 🔹 Tipo IV: Descarga con Prefijo de Fecha
```python
class D_BO_000000000(Download_Base):
    def get_data(self, main_url: str, path: str, updated_to: str, format: str = "%Y-%m-%d") -> str:
        """
        Recrea <path>/tmp y descarga archivos nuevos nombrados con prefijo:
        YYYY-MM-DD_nombre.ext (ej. 2026-07-31_boletin.pdf).
        Retorna la ruta string de la carpeta temporal: <path>/tmp.
        """
        pass

Robot = D_BO_000000000
```

---

## 🛡️ 2. Herramientas Locales en `download_tools.py`
- `format_date(date_str, format='%Y-%m-%d')`: Normaliza strings a objetos `datetime`.
- `month_to_number(month_name)`: Convierte nombres de meses en español (`"julio"` $\rightarrow$ `7`).
- `text_extract(pdf_path)`: Extrae líneas de texto de un PDF para buscar fechas vía regex.
- `createDirectoryStruct(file_date, base_path, freq)`: Crea árbol de carpetas por periodicidad.

---

## 🧪 3. Pruebas Unitarias
Configura `MAIN_URL` y `UPDATED_TO` en el archivo de prueba correspondiente y ejecuta:
```bash
python -m unittest test_download_type_i.py    # Tipo I
python -m unittest test_download_type_ii.py   # Tipo II
python -m unittest test_download_type_iii.py  # Tipo III
python -m unittest test_download_type_iv.py   # Tipo IV
```
O ejecuta el validador oficial:
```bash
python validate_robot.py
```
