---
trigger: always_on
---

# 📘 Estándares Oficiales de Desarrollo - DATAX Platform

Este documento define los estándares obligatorios de arquitectura, código, calidad y control de versiones que deben cumplir todos los robots de **Conversión** y **Descarga** en `data-processing-modules`.

---

## 1. 🔄 Robots de Conversión (`C_...` / `D_..._XX`)

### 1.1. Regla de Oro de la Clase Robot (Estricta)
> [!IMPORTANT]
> **REGLA ESTRICTA DE 2 MÉTODOS**: La clase del reporte (nombrada con el código del reporte, ej. `D_BO_000000051_01`, y referenciada como `Robot = D_BO_...`) debe contener **ÚNICA Y EXCLUSIVAMENTE DOS MÉTODOS**:
> 1. `def extraction(self, file_path: str, key_words: str, template_path: str = "", page_number: int = 1, format: str = "%Y-%m-%d") -> tuple:`
> 2. `def validate_data_results(self, dataframe: pd.DataFrame, decimal_separator: str = ",", TOLERANCE: float = 6.0) -> bool:`
>
> ❌ **PROHIBIDO**:
> - NO definir constructor `__init__`.
> - NO definir métodos auxiliares en `self` (ej. `self._limpiar()`).
> - No crear funciones sueltas innecesarias fuera de las provistas por `conversion_tools.py`. Si se requiere alguna lógica de soporte muy específica, declararla como función anidada dentro de `extraction()`.

### 1.2. Estilo de Código y Criterios de Aceptación para Pull Requests
- **PEP 8**: Cumplir estrictamente con PEP 8 (indentación de 4 espacios, espaciado uniforme, imports ordenados).
- **Inglés en Código**: Nombres de variables internas, docstrings y comentarios dentro del código deben estar redactados en **inglés**.
- **Prohibición de Listas Hardcodeadas y Técnica de Celdas Pivote**:
  - ❌ **ESTRICTAMENTE PROHIBIDO** hardcodear listas o diccionarios exhaustivos de cuentas, rubros o descripciones de texto (ej. listas con cada cuenta del Estado de Resultados o Balance). Si un carácter, tilde o espacio cambia en una publicación futura, el robot se rompe.
  - ✅ **USAR CELDAS PIVOTE Y PATRONES ESTRUCTURALES**:
    - **Celdas Pivote (Anclas)**: Localizar palabras clave indispensables o hitos clave (ej. `ACTIVO`, `PASIVO`, `PATRIMONIO`, o prefijos `(=)`, `(+)`, `(-)`) como puntos de corte o pivotes relativos.
    - **Propiedades del Documento**: Leer sangrías/indentación (`indent_level` o espacios iniciales), estilo tipográfico (`bold`), signos aritméticos iniciales (`(+)`, `(-)`, `(=)`), o numeraciones de cuentas (`100`, `110`, `111`) para determinar la jerarquía automáticamente.
    - Todo texto intermedio debe tomarse directamente de la celda de la hoja, no de strings quemados en el código.
- **Nombre de Clase**: Idéntica al código del reporte asignado (`D_BO_...`). Al final del archivo asignar el alias estándar: `Robot = D_BO_...`.
- **Contrato de Retorno de `extraction()`**: Tupla `(metadata_dict, df_melted)`:
  - `metadata_dict`:
    ```python
    {
        "file_name": os.path.basename(file_path),
        "titles": ["Título 1", "Título 2", ...],  # Cada línea del encabezado como un título
        "page_number": int(page_number)
    }
    ```
  - `df_melted`: Columnas `[nv1, nv2, ..., fecha, valor]`.
- **Validación `validate_data_results()`**:
  - Retorna `False` cuando los datos son válidos (sumas y reconciliaciones contables correctas).
  - Retorna `True` si existe alguna discrepancia o error.
- **Base SQLite de Referencia en `output/`**:
  - Contiene **única y exclusivamente la tabla `data_melted`** con la metadata insertada (`file`, `titulo1`..`tituloN`, `nv1`..`nvN`, `fecha`, `valor`) para inspección limpia del desarrollador.
- **Suite de Pruebas**: Finalizar en `OK` en `test_conversion.py`.

### 1.3. Regla de Jerarquías de Niveles (`nv1` a `nvN`) y Esquema Mental de Colores
Cuando un reporte presenta jerarquías visuales o contables, el mapeo debe seguir el orden maestro:
- **`nv1` (Naranja - Raíz / Total General)**: El concepto o título maestro del reporte (ej. `ACTIVO`, `PASIVO`, etc.). Debe estar presente en **todas las filas**.
- **`nv2` (Celeste - Sector / Agrupador Mayor)**: Los sectores principales (ej. `DISPONIBILIDADES`, `CARTERA`). La fila del Total General lleva `None` en `nv2`.
- **`nv3` (Verde - Entidad o Mercado)**: Las cuentas secundarias o subsectores (ej. `CARTERA VIGENTE`).
- **`nv4` (Amarillo - Instrumento o Entidad)**: Los instrumentos, sub-rubros o entidades financieras.
- **`nv5` (Sub-instrumento específico)**: Se utiliza si existe una subdivisión adicional.

### 1.4. Reglas de Metadatos y Encabezados (`titles` -> `titulo1`..`tituloN`)
El array `titles` retornado en `metadata_dict` es inyectado por `insert_metadata()` como columnas al inicio de la tabla:
- **`titulo1`**: Título principal del reporte (si está partido en 2 celdas como `CUENTAS MONETARIAS DE ` y `NO BANCOS`, unificarlas limpiamente).
- **`titulo2`**: Subtítulo o fecha de corte (ej. `CORRESPONDIENTE AL 31 DE JULIO DE 2026 p`).
- **`titulo3`**: Tipo de cambio si existe en el encabezado (ej. `Tipo de cambio: 12,15 Bs./USD`).
- **`titulo4`**: Unidad o denominación monetaria (ej. `(En millones de bolivianos)`).
> [!TIP]
> Todos los metadatos relevantes presentes en el encabezado superior del archivo deben capturarse en el orden correcto dentro de la lista `titles`.

### 1.5. Patrón de Máquina de Estados para Jerarquías y Trampas Comunes
> [!CAUTION]
> **REGLA DE ORO DE ESTADO JERÁRQUICO**:
> SIEMPRE actualizar las variables de estado (`current_nv1`, `current_nv2`, `current_nv3`) **ANTES** de evaluar si la fila contiene datos numéricos (`if not has_numeric_data: continue`).
> Si se omite esto, las filas de títulos de sección que NO tienen números en su misma fila (ej. `VIII. OBLIGACIONES CON ENTIDADES CON PART/ESTATAL`) serán ignoradas por el `continue`, haciendo que todas sus filas hijas caigan erróneamente bajo la sección anterior (ej. bajo `VII`).

- **Numerales Romanos Divididos en Columnas A y B**:
  Si la columna 1 contiene únicamente el numeral romano (ej. `VIII.`) y la columna 2 la descripción (ej. `OBLIGACIONES...`), concatenar `f"{col1} {col2}"` para conformar `nv1`, evitando que la descripción se asigne erróneamente a `nv2`.
- **Doble Dimensión en Columnas (Agrupador + Monedas/Métricas)**:
  Cuando las columnas tienen una fila superior de agrupación (ej. `C O N S O L I D A D O`) y una inferior de denominaciones (`MN`, `ME`, `MV`, `UFV`, `TOTAL`):
  - `nv5`: Encabezado agrupador (`C O N S O L I D A D O`).
  - `nv6`: Moneda o denominación (`MN`, `ME`, `MV`, `UFV`, `TOTAL`).
  - El DataFrame resultante debe tener estrictamente las columnas: `[nv1, nv2, ..., fecha, valor]`.
- **Series de Tiempo Multi-Anuales con Acumulados y Variaciones (`Cifras acumuladas` y `Var %`)**:
  - En tablas con años en el encabezado superior (ej. 2024, 2025, 2026) y meses en el inferior:
    - Las columnas mensuales regulares llevan `nv5 = None` y `nv6 = None` con fecha del último día de cada mes (`YYYY-MM-DD`).
    - Las columnas de `Cifras acumuladas a julio de cada gestión` se mapean a su fecha de corte (`YYYY-07-31`), asignando el texto del acumulado en `nv5` y el año en `nv6` (ej. `'2025'`, `'2026'`).
    - Las columnas de variaciones relativas (ej. `Var % 26/25`) llevan `nv5 = "Var % 26/25"`, `nv6 = None` y fecha del último corte (`2026-07-31`).
- **Aislamiento de Secciones Resumen al Final de la Hoja (`RESUMEN DE OPERACIONES`)**:
  - Cuando existan tablas resumen finales con filas que reutilizan nombres de secciones previas (ej. `SISTEMA DE PAGOS DE ALTO VALOR` o `SISTEMA DE PAGOS MINORISTA`), asegurar que la máquina de estados verifique primero si se encuentra dentro de `RESUMEN DE OPERACIONES` para no resetear `current_nv1` ni corromper las jerarquías superiores.
- **Filtrado de Banners de Subtotales Cruzados**:
  Filas como `TOTAL DEPÓSITOS` que agrupan varias secciones romanas (ej. VIII + IX) deben omitirse de la extracción para no distorsionar la jerarquía contable de la sección inmediata anterior.

### 1.6. Reconciliación Matemática en `validate_data_results()`
> [!IMPORTANT]
> Valida que el aplanamiento sea contable y matemáticamente exacto:
> 1. **Esquema de Reconciliación Jerárquica en Cadena (Amarillos $\rightarrow$ Celestes $\rightarrow$ Verde)**:
>    - **Nivel Detalle (Amarillos, `nv4 is not None`)**: La suma de los rubros individuales bajo una misma moneda/categoría debe igualar exactamente al subtotal de dicha moneda (Celeste, `nv4 is None`).
>    - **Nivel Subtotal (Celestes)**: La suma de los subtotales individuales (ej. MN + ME) debe ser igual al Total General de la sección (Verde, ej. `TOTAL VALOR OPERACIONES`).
>    - **Filtrado Temporal en Validación**: Al realizar sumatorias en `validate_data_results()`, filtrar exclusivamente meses regulares (`df['nv5'].isna()`), asegurando que las columnas acumuladas o de variación porcentual no se mezclen con los flujos mensuales.
> 2. **Reconciliación Horizontal de Monedas**:
>    - Para cada concepto y fecha: $\sum (\text{monedas individuales}) == \text{TOTAL}$ con tolerancia de `TOLERANCE` ($6.0$).
> 3. **Reconciliación Vertical de Secciones**:
>    - Cada raíz de sección (`nv1` con `nv2 is None`) debe ser igual a la suma de sus capítulos o sectores directos (`nv2 is not None & nv3 is None & nv4 is None`).
> 4. **Reconciliación Vertical de Subcuentas**:
>    - Las cuentas secundarias con sangría (`nv4 is not None`, ej. Cartera Vigente, Vencida, Ejecución) deben sumar exactamente a su cuenta padre (`nv3`, ej. Créditos).
> 5. Retornar `False` si la validación es exitosa. Retornar `True` si hay discrepancias.


---

## 2. 📥 Robots de Descarga (`D_...`)

Los robots de descarga interactúan con portales web, repositorios o APIs externas para obtener archivos de datos y comprobar novedades temporales. Existen **4 tipos oficiales de robots de descarga** en DATAX Platform según el flujo de navegación, descarga y filtrado de fechas.

### 2.1. Regla de Nombre de Clase y Alias
- La clase del robot debe llamarse exactamente con el código del reporte (ej. `D_BO_000000289`, `D_BO_000000485`).
- Al final del archivo asignar el alias estándar:
  ```python
  Robot = D_BO_000000289
  ```
- Soporte opcional de clase base:
  ```python
  try:
      from models.download import Download_Base
  except ImportError:
      Download_Base = object
  ```

---

### 2.2. Los 4 Tipos Oficiales de Robots de Descarga

#### 🔹 Tipo I: Descarga Asistida por Plataforma
La plataforma delega al robot la búsqueda de URLs y el filtrado por fecha interna, mientras que la descarga física de los archivos la realiza el orquestador de la plataforma.
- **Métodos requeridos**:
  1. `def get_file_url(self, main_url: str, updated_to: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:`
     - Navega al portal (vía Playwright o Requests) y recolecta las URLs directas de los archivos.
     - Retorna: `list` de URLs strings (`['https://.../reporte1.xlsx', ...]`).
  2. `def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:`
     - Recibe la lista de archivos descargados por la plataforma con estructura:
       `[{'download_url': str, 'tmp_path': str}]`.
     - Inspecciona el contenido de cada archivo (Excel, PDF, o texto) para extraer la fecha real del reporte.
     - Filtra y conserva únicamente los archivos con `fecha_archivo > updated_to`.
     - Retorna lista de diccionarios con llaves exactas:
       `[{'tmp_path': str, 'updated_to': str, 'download_url': str}]` (o `False`/`[]` si no hay novedades).
- **Suite de Pruebas**: `python -m unittest test_download_type_i.py`

#### 🔹 Tipo II: Descarga Controlada por el Robot + Comparación Posterior
El robot maneja tanto la descarga a disco (usando cookies, headers o sesiones especiales) como el posterior análisis de fechas.
- **Métodos requeridos**:
  1. `def verify_download(self, main_url: str, updated_to: str, path: str, key_words: str = "", format: str = "%Y-%m-%d") -> list:`
     - Recrea limpiamente la carpeta temporal `tmp` en `os.path.join(path, 'tmp')`.
     - Navega y descarga los archivos directamente dentro de esa carpeta `tmp`.
     - Retorna: `list[dict]` con llaves exactas `{'tmp_path', 'download_url'}`:
       `[{'tmp_path': '.../tmp/archivo.xlsx', 'download_url': 'https://...'}]`.
  2. `def compare_files(self, files_paths: list, updated_to: str, format: str = "%Y-%m-%d") -> list:`
     - Recibe los `files_paths` generados en `verify_download`.
     - Extrae la fecha interna y conserva los registros con `fecha > updated_to`.
     - Retorna: `list[dict]` con llaves exactas `{'tmp_path', 'updated_to', 'download_url'}`.
- **Suite de Pruebas**: `python -m unittest test_download_type_ii.py`

#### 🔹 Tipo III: Pipeline Integrado (Recomendado para APIs y Scraping Complejo)
Orquestación completa en un único método. Ideal para portales con parámetros dinámicos, paginaciones complejas, APIs REST o endpoints históricos donde la consulta y la descarga ocurren en conjunto.
- **Método requerido**:
  - `def check_new_data(self, main_url: str, updated_to: str, path: str, key_words: str = None, format: str = "%Y-%m-%d") -> list:`
    - Recrea limpiamente la carpeta temporal `os.path.join(path, "tmp")`.
    - Consulta la API o portal, descarga o genera el archivo (Excel, PDF, CSV) directamente en `tmp`.
    - Valida que la fecha de corte sea estrictamente posterior a `updated_to` (`fecha > updated_to`).
    - Retorna directamente la lista de diccionarios con llaves exactas:
      `[{'tmp_path': str, 'updated_to': str, 'download_url': str}]` (o `[]` si no hay novedades).
- **Suite de Pruebas**: `python -m unittest test_download_type_iii.py`

#### 🔹 Tipo IV: Descarga por Lote a Carpeta con Prefijo de Fecha
Utilizado cuando los archivos deben persistirse en disco organizados y la plataforma procesa la carpeta mediante inspección de nombres.
- **Método requerido**:
  - `def get_data(self, main_url: str, path: str, updated_to: str, format: str = "%Y-%m-%d") -> str:`
    - Recrea limpiamente la carpeta temporal `tmp_path = os.path.join(path, 'tmp')`.
    - Descarga los archivos nuevos en `tmp_path`.
    - **Regla estricta de nomenclatura**: Cada archivo guardado debe comenzar con la fecha en formato ISO `YYYY-MM-DD` (patrón regex `r'^\d{4}-\d{2}-\d{2}'`), ej: `2026-07-31_resumen_operaciones.xlsx`.
    - Retorna el path del directorio temporal como string: `tmp_path`.
- **Suite de Pruebas**: `python -m unittest test_download_type_iv.py`

---

### 2.3. Reglas Transversales de Calidad para Descarga
1. **Limpieza Rigurosa de `tmp/`**: Todo método que guarde archivos locales debe recrear `tmp` desde cero para evitar archivos residuales:
   ```python
   tmp_dir = os.path.join(path, "tmp")
   if os.path.exists(tmp_dir):
       shutil.rmtree(tmp_dir)
   os.makedirs(tmp_dir, exist_ok=True)
   ```
2. **Criterio Estricto de Fecha Novedosa (`>` updated_to)**:
   - Los archivos retornados deben tener fecha estrictamente **mayor** a `updated_to` (`file_date > reference_date`). Nunca retornar archivos con fecha igual o menor.
3. **Manejo Seguro de Playwright**:
   - Usar siempre modo headless: `pl.chromium.launch(headless=True)`.
   - Establecer `User-Agent` moderno de escritorio.
   - Envolver siempre la sesión en bloques `try...finally` asegurando `browser.close()`.
4. **Extracción Robusta de Fechas Internas**:
   - Para Excel: Usar `openpyxl` en modo `read_only=True` o `pd.read_excel` sobre las primeras 10-15 filas.
   - Para PDF: Usar `text_extract` de `download_tools.py` para buscar fechas por regex.
   - Para meses en español: Utilizar `month_to_number` de `download_tools.py`.
5. **Mapeo de Llaves Exactas en Diccionarios**:
   - Cada diccionario de salida debe contener única y exactamente:
     - `tmp_path`: Ruta local absoluta o relativa del archivo.
     - `updated_to`: Fecha del archivo en formato `YYYY-MM-DD`.
     - `download_url`: URL de origen desde la cual se descargó.

---

## 3. 🛡️ Autosuficiencia y Aprendizaje en `data-processing-modules`
- Los desarrolladores en este repositorio **NO requieren ni tienen acceso a `data-processing-platform-dev`** ni bases de datos de red interna.
- Todo el código debe importar herramientas locales:
  ```python
  from conversion_tools import to_numeric_datax
  from download_tools import createDirectoryStruct
  ```
- Para estudiar robots aprobados y resolver dudas, consultar las ramas remotas del repositorio:
  ```bash
  git fetch origin
  git branch -r
  git show origin/<nombre-rama>:robot.py
  ```
