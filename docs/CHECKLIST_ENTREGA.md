# ✅ Checklist de Calidad y Entrega - DATAX Platform

Antes de solicitar la revisión de tu Pull Request, asegúrate de cumplir cada uno de los siguientes puntos. Este checklist refleja los estándares obligatorios de producción.

---

## 1. 🏗️ Arquitectura de la Clase Robot
- [ ] La clase `Robot` tiene **EXACTAMENTE 2 MÉTODOS**:
  - `def extraction(self, file_path, key_words="", template_path="", page_number=1, format="%Y-%m-%d") -> tuple:`
  - `def validate_data_results(self, dataframe: pd.DataFrame, decimal_separator: str = ",", TOLERANCE: float = 6.0) -> bool:`
- [ ] **NO tiene `__init__`**.
- [ ] **NO tiene métodos auxiliares con `self`**. (Todas las funciones de apoyo están anidadas dentro de `extraction()` o declaradas a nivel de módulo).

---

## 2. 📊 Jerarquía de Niveles y Estructura Melted
- [ ] **`nv1` (Concepto Maestro / Total General)** está presente en **todas** las filas del DataFrame.
- [ ] **`nv2` (Sectores Mayores)** contiene el sector cuando corresponde, y `None` únicamente en la fila de Total General.
- [ ] **`nv3` (Entidades / Subsectores)** asignado correctamente a las instituciones correspondientes.
- [ ] **`nv4` (Instrumentos)** contiene los nombres limpios de los instrumentos financieros.
- [ ] **`nv5` (Sub-instrumentos)** utilizado cuando hay un nivel adicional de desglose (o `None` si concluye en `nv4`).
- [ ] Columna `fecha` en penúltima posición, formato estricto `YYYY-MM-DD`.
- [ ] Columna `valor` en última posición, tipo numérico (int/float), sin textos `<NA>` ni caracteres especiales.

---

## 3. 📅 Fechas Dinámicas
- [ ] El año y mes de corte se obtienen dinámicamente del nombre del archivo (`YYYY-MM-DD`).
- [ ] Las columnas mensuales se calculan con el último día del mes correspondiente (`calendar.monthrange`).
- [ ] **Cero fechas fijas en duro** en sentencias `return`.

---

## 4. 🧮 Reconciliación Matemática (`validate_data_results`)
- [ ] La función agrupa por `fecha` y valida:
  $$\sum 	ext{Instrumentos Individuales} = 	ext{Total General}$$
- [ ] Tolerancia aplicada (`TOLERANCE=6.0`).
- [ ] **Retorno**: `False` cuando los datos cuadran (éxito), `True` si hay inconsistencia.

---

## 5. 🛡️ Autosuficiencia e Importaciones
- [ ] Importaciones realizadas desde utilidades locales de `data-processing-modules`:
  ```python
  from conversion_tools import to_numeric_datax
  ```
- [ ] No existen dependencias a rutas del servidor interno (`models.conversion.tools...`).

---

## 6. 🧪 Validación Automatizada
- [ ] `python validate_robot.py` se ejecuta y muestra `[PASS]` en todos los puntos.
- [ ] `python -m unittest test_conversion.py` ejecuta y termina en `OK`.

---

## 7. 🚀 Publicación en Git
- [ ] La rama remota asignada `origin/<CODIGO_REPORTE>` fue renombrada a `<nombre>/<CODIGO_REPORTE>`.
- [ ] Solo se agregaron `robot.py` y `test_conversion.py` al commit (sin archivos `.xlsx`, `.pdf` o temporales).
- [ ] Rama subida a GitHub con `git push -u origin <nombre>/<CODIGO_REPORTE>`.
- [ ] Rama genérica antigua eliminada con `git push origin --delete <CODIGO_REPORTE>`.
- [ ] Enlace de Pull Request abierto hacia `main`.
