---
name: crear-robot-conversion
description: Guía completa para crear un robot de conversión de datos (Excel/PDF) siguiendo los estándares oficiales de DATAX Platform con inspección en attachtments/ y salida en SQLite.
---

# 🔄 Skill: Crear Robot de Conversión

Esta skill guía el desarrollo de un robot de conversión (`robot.py`) que transforma archivos de entrada (Excel o PDF) en un `DataFrame` vertical (*melted*) normalizado, validando sumas y generando una base SQLite para inspección del pasante.

---

## Flujo de Trabajo en 6 Pasos

### Paso 1: Cargar e Inspeccionar el Archivo en `attachtments/`
1. Solicitar al pasante que coloque el archivo de muestra en la carpeta `attachtments/` (ej. `attachtments/2026-07-31_entidades arrendamiento.xls`).
2. Identificar la pestaña objetivo (en libros Excel) o página objetivo (en PDF).
3. Analizar la jerarquía visual con el esquema de colores:
   - **Naranja**: Total General (`nv1` para todas las filas).
   - **Celestes**: Sectores / Categorías mayores (`nv2`).
   - **Verdes**: Entidades o Subsectores (`nv3`).
   - **Amarillos**: Instrumentos / Hojas (`nv4`, `nv5`).

### Paso 2: Consultar Referencias en Git
Si surgen dudas sobre la lógica de extracción o estructuras similares, buscar ramas remotas ya aprobadas:
```bash
git fetch origin
git branch -r
git show origin/<nombre-rama>:robot.py
```

### Paso 3: Configurar Fechas Dinámicas
- Extraer el año y mes de corte dinámicamente del nombre del archivo (`YYYY-MM-DD`).
- Resolver las fechas de cada columna/fila al último día del mes correspondiente (`calendar.monthrange` o `last_day_month`).
- NUNCA quemar fechas fijas estáticas en duro.

### Paso 4: Implementar `robot.py` Usando Celdas Pivote y Máquina de Estados
> [!IMPORTANT]
> **REGLA ESTRICTA DE 2 MÉTODOS**: La clase solo debe tener `extraction()` y `validate_data_results()`.
> No usar `__init__`. Anidar funciones auxiliares dentro de `extraction()` o a nivel de módulo.
>
> ❌ **PROHIBIDO HARDCODEAR LISTAS DE STRINGS**: Nunca escribir listas o diccionarios con los nombres de todas las cuentas o rubros contables.
> ✅ **USAR CELDAS PIVOTE Y NIVELES ESTRUCTURALES**:
> - Extraer títulos de encabezado dinámicamente (`titulo1`: nombre reporte, `titulo2`: corte, `titulo3`: tipo de cambio, `titulo4`: denominación/unidad).
> - Manejar columnas bidimensionales (ej. `nv5`: agrupador `CONSOLIDADO`, `nv6`: moneda `MN`, `ME`, `MV`, `UFV`, `TOTAL`).
> - **Series de Tiempo Multi-Anuales con Acumulados y Variaciones**:
>   - Columnas mensuales regulares: `nv5 = None`, `nv6 = None`.
>   - Columnas de `Cifras acumuladas`: `nv5 = "Cifras acumuladas a julio de cada gestión"`, `nv6 = "2025"` (año de acumulación) y fecha del corte respectivo.
>   - Columnas de `Var %`: `nv5 = "Var % 26/25"`, `nv6 = None` y fecha del último corte.
> - **ORDEN CRÍTICO EN EL BUCLE**: Actualizar el estado jerárquico (`current_nv1`, `current_nv2`, `current_nv3`) **ANTES** de evaluar si la fila tiene datos numéricos. Esto evita perder secciones que no tienen números en su fila de título.
> - Manejar números romanos divididos en columnas A y B (ej. `c1='VIII.'` y `c2='OBLIGACIONES...'` -> concatenar para `nv1`).
> - **Aislamiento de Tablas Resumen**: Si al final de la hoja existen tablas consolidadas (`RESUMEN DE OPERACIONES`), blindar `current_nv1` para evitar que filas hijas con nombres idénticos a secciones previas reseteen la jerarquía.
> - **Reconciliación en 3 Niveles (Amarillos $\rightarrow$ Celestes $\rightarrow$ Verde)**:
>   - Nivel Detalle (Amarillos, `nv4 is not None`): la suma de los rubros individuales iguala al subtotal por moneda/categoría (Celeste, `nv4 is None`).
>   - Nivel Subtotal (Celestes): la suma de los subtotales (MN + ME) iguala al Total General de la sección (Verde, ej. `TOTAL VALOR OPERACIONES`).
>   - Filtrar únicamente fechas de meses regulares (`nv5.isna()`) al validar las reconciliaciones mensuales.
> - Omitir banners de subtotales cruzados como `TOTAL DEPÓSITOS`.


```python
import os
import re
import calendar
import traceback
import pandas as pd
from typing import Tuple

from conversion_tools import to_numeric_datax

try:
    from models.conversion import Conversion_Base
except ImportError:
    Conversion_Base = object


class D_BO_XXXXXXXXX_XX(Conversion_Base):
    def extraction(self, file_path, key_words="", template_path="", page_number=1, format="%Y-%m-%d") -> Tuple[dict, pd.DataFrame]:
        try:
            file_name = os.path.basename(file_path)

            def resolve_report_date(sample_text: str = "") -> str:
                if sample_text:
                    month_map = {
                        "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
                        "julio": 7, "agosto": 8, "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12
                    }
                    m = re.search(r"(\d{1,2})\s+DE\s+([A-Za-z]+)\s+DE\s+(\d{4})", sample_text, re.I)
                    if m:
                        d, mon, y = m.groups()
                        return f"{int(y):04d}-{month_map.get(mon.lower(), 1):02d}-{int(d):02d}"
                m2 = re.search(r"(\d{4})[-_]?(\d{2})", file_name)
                if m2:
                    y, m = int(m2.group(1)), int(m2.group(2))
                    return f"{y:04d}-{m:02d}-{calendar.monthrange(y, m)[1]:02d}"
                today = pd.Timestamp.now()
                return f"{today.year:04d}-{today.month:02d}-{calendar.monthrange(today.year, today.month)[1]:02d}"

            import openpyxl
            wb = openpyxl.load_workbook(file_path, data_only=True)
            sheet = wb[wb.sheetnames[0]]

            titles = []
            header_row_idx = None
            currencies = {}
            group_title = "CONSOLIDADO"
            report_date = None
            exchange_rate_title = None
            denomination_title = None
            title_parts = []

            for r in range(1, min(15, sheet.max_row + 1)):
                c1_str = str(sheet.cell(r, 1).value or "").strip()
                if c1_str:
                    if "CUENTAS MONETARIAS" in c1_str.upper() or c1_str.upper() == "NO BANCOS":
                        title_parts.append(c1_str)
                    elif "CORRESPONDIENTE" in c1_str.upper():
                        if title_parts:
                            titles.append(" ".join(title_parts).strip())
                            title_parts = []
                        titles.append(c1_str)
                        if not report_date:
                            report_date = resolve_report_date(c1_str)
                    elif "TIPO DE CAMBIO" in c1_str.upper():
                        exchange_rate_title = c1_str

                for c in range(1, 12):
                    v = str(sheet.cell(r, c).value or "").strip()
                    if "MILLONES" in v.upper():
                        denomination_title = v
                    if "CONSOLIDADO" in v.upper().replace(" ", ""):
                        group_title = v

                row_vals = [(c, str(sheet.cell(r, c).value or "").strip().upper()) for c in range(1, 12)]
                det = {c: v for c, v in row_vals if v in {"MN", "ME", "MV", "UFV", "TOTAL"}}
                if len(det) >= 3:
                    header_row_idx, currencies = r, det

            if title_parts and not titles:
                titles.append(" ".join(title_parts).strip())
            if exchange_rate_title and exchange_rate_title not in titles:
                titles.append(exchange_rate_title)
            if denomination_title and denomination_title not in titles:
                titles.append(denomination_title)
            if not report_date:
                report_date = resolve_report_date()

            records = []
            current_nv1, current_nv2, current_nv3 = None, None, None
            roman_pattern = re.compile(r"^\s*(I|II|III|IV|V|VI|VII|VIII|IX|X)\.?\s*", re.I)

            for r in range(header_row_idx + 1, sheet.max_row + 1):
                c1, c2, c3 = sheet.cell(r, 1).value, sheet.cell(r, 2).value, sheet.cell(r, 3).value
                s1, s2, s3 = str(c1 or "").strip(), str(c2 or "").strip(), str(c3 or "").strip()
                if not any([s1, s2, s3]) or any(t in s1.upper() for t in ["FUENTE", "ELABORACI", "NOTAS"]) or "TOTAL DEP" in s2.upper():
                    if any(t in s1.upper() for t in ["FUENTE", "ELABORACI", "NOTAS"]):
                        break
                    continue

                # 1. ACTUALIZAR ESTADO ANTES DEL CHEQUEO NUMÉRICO
                if roman_pattern.match(s1):
                    if s2 and re.match(r"^\s*(I|II|III|IV|V|VI|VII|VIII|IX|X)\.?\s*$", s1, re.I):
                        current_nv1 = f"{s1} {s2}"
                    else:
                        current_nv1 = re.sub(r"[ \t]+", " ", s1).strip()
                    current_nv2 = current_nv3 = None
                    nv1, nv2, nv3, nv4 = current_nv1, None, None, None
                elif s2:
                    current_nv2, current_nv3 = s2, None
                    nv1, nv2, nv3, nv4 = current_nv1, current_nv2, None, None
                elif s3:
                    indent = sheet.cell(r, 3).alignment.indent if sheet.cell(r, 3).alignment else 0
                    spaces = len(str(c3)) - len(str(c3).lstrip(" "))
                    if indent >= 1 or spaces >= 1:
                        nv1, nv2, nv3, nv4 = current_nv1, current_nv2, current_nv3, s3
                    else:
                        current_nv3 = s3
                        nv1, nv2, nv3, nv4 = current_nv1, current_nv2, current_nv3, None
                else:
                    continue

                # 2. EVALUAR NUMÉRICOS PARA EMITIR REGISTROS
                raw_nums = [sheet.cell(r, c).value for c in currencies.keys()]
                if not any(isinstance(v, (int, float)) and v is not None for v in raw_nums):
                    continue

                for col_idx, curr in currencies.items():
                    records.append({
                        "nv1": str(nv1) if nv1 else None, "nv2": str(nv2) if nv2 else None,
                        "nv3": str(nv3) if nv3 else None, "nv4": str(nv4) if nv4 else None,
                        "nv5": str(group_title) if group_title else None, "nv6": str(curr) if curr else None,
                        "fecha": str(report_date), "valor": sheet.cell(r, col_idx).value or 0.0
                    })

            df_melted = pd.DataFrame(records)
            df_melted["valor"] = to_numeric_datax(df_melted["valor"], decimal_separator=".")
            for col in ["nv1", "nv2", "nv3", "nv4", "nv5", "nv6", "fecha"]:
                df_melted[col] = df_melted[col].where(df_melted[col].notna(), None)

            return {"file_name": file_name, "titles": titles, "page_number": int(page_number)}, df_melted
        except Exception as err:
            traceback.print_exc()
            return "", pd.DataFrame()

    def validate_data_results(self, dataframe: pd.DataFrame, decimal_separator: str = ",", TOLERANCE: float = 6.0) -> bool:
        try:
            if dataframe is None or dataframe.empty:
                return True
            df = dataframe.copy()
            df["valor_num"] = df["valor"].astype(float) if pd.api.types.is_numeric_dtype(df["valor"]) else to_numeric_datax(df["valor"], decimal_separator)

            # 1. Horizontal: MN + ME + MV + UFV == TOTAL
            for keys, grp in df.groupby(["nv1", "nv2", "nv3", "nv4", "fecha"], dropna=False):
                tot = grp[grp["nv6"] == "TOTAL"]
                comps = grp[grp["nv6"] != "TOTAL"]
                if not tot.empty and not comps.empty and abs(comps["valor_num"].sum() - tot["valor_num"].iloc[0]) > TOLERANCE:
                    return True

            # 2. Vertical: Raíces de sección == suma de capítulos directos
            for (dt, curr, sec), grp in df.groupby(["fecha", "nv6", "nv1"]):
                root = grp[grp["nv2"].isna() & grp["nv3"].isna() & grp["nv4"].isna()]
                chapters = grp[grp["nv2"].notna() & grp["nv3"].isna() & grp["nv4"].isna()]
                if not root.empty and not chapters.empty and abs(chapters["valor_num"].sum() - root["valor_num"].iloc[0]) > TOLERANCE:
                    return True
            return False
        except Exception:
            return True


Robot = D_BO_XXXXXXXXX_XX
```

---

### 🏛️ Patrón Especial: Subastas de Títulos y Letras (PDFs con pdfplumber)
Para reportes de subastas de bonos y letras del BCB/TGN (ej. `D_BO_000000038_01`, `D_BO_000000039_01`, `D_BO_000000040_01`):

1. **Jerarquía Oficial de 8 Niveles (`nv1` a `nv8`)**:
   - `nv1`: Moneda (`MN`, `ME`, `UFV`).
   - `nv2`: Serie del instrumento (ej. `BTNC00522639`, `LBN000132639`, `LRNR00392639`).
   - `nv3`: Plazo normalizado (ej. `f"{dias} días"`).
   - `nv4`: Semana / Año de la subasta (ej. `2026-39`, derivado del título `SUBASTA ... 39 / 2026`).
   - `nv5`: Emisor (`TGN`, `BCB`).
   - `nv6`: Registro individual (`1`, `2`, ..., `N`) o `TOTAL` para la fila de cierre.
   - `nv7`: Motivo de rechazo (`N` si fue aceptado, o códigos `DPF`, `ED`, `DPM`; `TOTAL` en la fila de cierre).
   - `nv8`: Nombre de la métrica (`Monto Ofertado`, `Monto Demandado`, `T.R. %`, `T.D. %`, `T.E.A %`, `Monto Adjudicado`, `TRN %`).
   - `fecha`: Fecha de subasta extraída del texto (`Fecha: DD/MM/YYYY`) o del nombre del archivo.
   - `valor`: Número flotante parseado con `to_numeric_datax(serie, decimal_separator=",")`.

2. **Extracción Dinámica de Tasas**:
   - Bonos TGN suelen incluir 1 tasa (`TRE` -> `T.R. %`).
   - Letras BCB y Letras Rescatables incluyen hasta 3 tasas (`TRE` -> `T.R. %`, `TD` -> `T.D. %`, `TEA` -> `T.E.A %`).
   - Dividir la línea limpia de tokens (`clean_line.split()`) para detectar si contiene 1 o 3 tasas numéricas antes del monto adjudicado.

3. **Reconciliaciones en `validate_data_results()`**:
   - $\sum_{\text{reg} \neq \text{'TOTAL'}} (\text{Monto Demandado}) == \text{Monto Demandado}(\text{'TOTAL'})$.
   - $\sum_{\text{reg} \neq \text{'TOTAL'}} (\text{Monto Adjudicado}) == \text{Monto Adjudicado}(\text{'TOTAL'})$.
   - $\text{Monto Adjudicado TOTAL} \le \text{Monto Ofertado} + \text{TOLERANCE}$.

---

### 🌐 Patrón Especial: Matrices País-Fecha con Cifras Preliminares (ej. Remesas, Comercio Exterior)
Para reportes de matrices de países por series mensuales/anuales (ej. `D_BO_000000265_01` - Remesas de Trabajadores según País de Origen):

1. **Jerarquía y Estructura Oficial**:
   - `nv1`: Nombre del país de origen/destino (`Alemania`, `Argentina`, ..., `Otros`) o concepto total (`Remesas`). Normalizar columnas encabezadas como `TOTAL` al nombre del concepto general (`Remesas`).
   - `nv2`: Etiqueta preliminar o temporal. Debe ser `None` para meses regulares, o el string del año preliminar (ej. `'2025p'`, `'2026p'`) para filas de corte anual acumulado.
   - `fecha`: Fecha fin de mes en formato ISO `YYYY-MM-DD`.
     - Para meses regulares (celdas `datetime` o strings `YYYY-MES` / `MES-YY`): calcular el último día del mes vía `calendar.monthrange(year, month)[1]`.
     - Para cifras preliminares anuales (`YYYYp`):
       - Si el año coincide con el año corriente en curso: pre-escanear la hoja para obtener la fecha mensual máxima (`max_monthly_date`, ej. `2026-07-31`) y asignar esa fecha exacta.
       - Si es un año previo cerrado: asignar el último día del año (`f"{year}-12-31"`).
   - `valor`: Cifra numérica procesada con `to_numeric_datax(serie, decimal_separator=",")`.

2. **Detección Dinámica de Columnas**:
   - Localizar dinámicamente la fila de encabezados buscando el primer país pivote (ej. `Alemania`) y el final (`Remesas` o `Total`).
   - Identificar dinámicamente la columna de fechas/meses previa a los países (nombres como `migrar`, `mes`, `fecha`, `año`).
   - Soportar hojas individuales o múltiples pestañas consolidables deduplicando por `["nv1", "nv2", "fecha"]`.

3. **Reconciliación Contable en `validate_data_results()`**:
   - Para cada fecha y grupo `nv2` (`groupby(['fecha', 'nv2'])`):
     - La suma de todos los países individuales más `Otros` debe ser exactamente igual al total `Remesas`:
       $$\sum_{\text{nv1} \neq \text{'Remesas'}} (\text{valor}) == \text{Remesas (Total)}$$
     - Tolerancia estándar: `TOLERANCE = 6.0`.

### Paso 5: Validar y Generar Base SQLite para Inspección
1. Ejecutar las pruebas unitarias y el validador oficial:
   ```bash
   python -m unittest test_conversion.py
   python validate_robot.py --type conversion
   ```
2. `test_conversion.py` toma automáticamente el archivo colocado en `attachtments/` y exporta los datos a:
   `output/<CODIGO_REPORTE>.sqlite`
3. Solicitar o guiar al pasante para que examine la tabla `data_melted` en el archivo SQLite generado y verifique que la estructura, niveles y valores sean los esperados.

### Paso 6: Ajustes y Publicación en Git
- Si hay inconsistencias o errores de validación, aplicar correcciones y volver a generar el SQLite.
- Cuando todo esté correcto y aprobado por el pasante, activar la skill `subir-al-git` para publicar la rama en GitHub.
