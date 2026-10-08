"""
Agente Analizador Inteligente de SQLite para Migración DATAX.
Utiliza Google Gemini API (con descubrimiento dinámico de modelos) y un motor heurístico avanzado de respaldo para:
1. Inspeccionar títulos, jerarquías (nv1..nvN) y distribución numérica de valores en SQLite.
2. Identificar si el reporte tiene métricas o unidades homogéneas o mixtas por fila.
3. Determinar métricas ('tasa', 'precio', 'moneda', 'porcentaje', 'indice', etc.) y unidades ('%', 'BOB', 'USD', 'USD/Tn', 'GBP/Tn', 'EUR/Tn', 'UFV', etc.).
4. Definir el factor de conversión adecuado (1, 1000, 1000000) asegurando que tasas, precios y porcentajes siempre tengan factor 1.
5. Generar las funciones Python get_metric(row) y get_unit(row) optimizadas para el robot de migración.
"""

import os
import re
import json
import sqlite3
import unicodedata
from typing import Dict, Any, List, Tuple
import requests
import pandas as pd


def standardize_col_name(col: str) -> str:
    """Normaliza nombres de columnas a snake_case válido para PostgreSQL (sin espacios ni acentos)."""
    cleaned = re.sub(r'[\t\xa0]+', '', str(col)).strip()
    s = re.sub(r'\s+', '_', cleaned.lower())
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8')
    s = re.sub(r'[^a-z0-9_]', '', s)
    return s


def parse_commodity_price_unit(text: str) -> str:
    """
    Detecta si una cadena representa un precio/cotización por unidad física (Moneda / Unidad).
    Ejemplos:
      'London Futures (£ Sterling/tonne)' -> 'GBP/Tn'
      'New York Futures (Us$/tonne)'     -> 'USD/Tn'
      'Icco Daily Price (Euro/tonne)'    -> 'EUR/Tn'
      'Petroleo WTI (US$/barril)'        -> 'USD/Bbl'
      'Estaño (US$/LF)'                  -> 'USD/lb'
    """
    t = str(text).lower()

    # Si no tiene indicador de división o precio por unidad, no es precio/unidad
    has_slash = "/" in t or " por " in t or " per " in t
    has_price_kw = any(k in t for k in ["price", "precio", "futures", "futuros", "cotizacion", "cotización", "spot"])
    if not (has_slash or has_price_kw):
        return ""

    curr = ""
    if any(k in t for k in ["£", "sterling", "gbp", "libra esterlina"]):
        curr = "GBP"
    elif any(k in t for k in ["euro", "eur", "€"]):
        curr = "EUR"
    elif any(k in t for k in ["us$", "$us", "usd", "dolar", "dólar", "$"]):
        curr = "USD"
    elif any(k in t for k in ["bs", "bob", "boliviano", "bolivianos"]):
        curr = "BOB"
    elif any(k in t for k in ["usc", "centavos", "ctvs", "c$"]):
        curr = "USc"
    elif any(k in t for k in ["ars", "peso argentino"]):
        curr = "ARS"
    elif any(k in t for k in ["brl", "real", "reales"]):
        curr = "BRL"

    phys = ""
    if any(k in t for k in ["tonne", "tonelada", "tm", "ton", "mt"]):
        phys = "Tn"
    elif any(k in t for k in ["kg", "kilo", "kilogramo", "kgs"]):
        phys = "Kg"
    elif any(k in t for k in ["barril", "bbl", "barriles"]):
        phys = "Bbl"
    elif any(k in t for k in ["libra", "lb", "lf", "lbs"]):
        phys = "lb"
    elif any(k in t for k in ["onza", "oz", "ot", "onzas"]):
        phys = "Oz"
    elif any(k in t for k in ["mmbtu", "mbtu"]):
        phys = "MMBTU"
    elif any(k in t for k in ["litro", "litros", "lt", "lts"]):
        phys = "litro"
    elif any(k in t for k in ["quintal", "qq"]):
        phys = "qq"
    elif "mwh" in t:
        phys = "MWh"
    elif "kwh" in t:
        phys = "kWh" 

    if curr and phys:
        return f"{curr}/{phys}"
    return ""


def extract_sqlite_summary_for_agent(sqlite_path: str) -> Dict[str, Any]:
    """
    Extrae un resumen estadístico, categórico y muestral completo del SQLite para alimentar al Agente IA.
    Garantiza CERO omisiones al extraer categorías completas mediante SELECT DISTINCT sobre toda la tabla.
    """
    if not os.path.exists(sqlite_path):
        return {"error": f"Archivo no encontrado: {sqlite_path}"}

    with sqlite3.connect(sqlite_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('columns_to_review', 'sqlite_sequence');")
        tables = [r[0] for r in cursor.fetchall()]
        if not tables:
            return {"error": "No se encontraron tablas válidas en el archivo SQLite."}

        table_name = tables[0]
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        pragma_cols = [row[1] for row in cursor.fetchall()]

        df_sample = pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT 200;', conn)
        total_rows_res = cursor.execute(f'SELECT COUNT(*) FROM "{table_name}";').fetchone()
        total_rows = total_rows_res[0] if total_rows_res else len(df_sample)

        cols_raw = [c for c in pragma_cols if str(c).lower().strip() != 'file']
        cols_std = [standardize_col_name(c) for c in cols_raw]
        col_map = dict(zip(cols_std, cols_raw))

        title_cols = [c for c in cols_std if c.startswith('titulo')]
        nv_cols = [c for c in cols_std if c.startswith('nv')]
        aux_cols = [c for c in cols_std if c not in title_cols and c not in nv_cols and c not in ['fecha', 'valor', 'file', 'id']]

        # 1. Títulos completos inspeccionados de toda la tabla
        titles_dict = {}
        for tc in title_cols:
            raw_c = col_map.get(tc, tc)
            try:
                cursor.execute(f'SELECT DISTINCT "{raw_c}" FROM "{table_name}" WHERE "{raw_c}" IS NOT NULL LIMIT 10;')
                u_vals = [str(r[0]).strip() for r in cursor.fetchall() if str(r[0]).strip()]
                if u_vals:
                    titles_dict[tc] = u_vals
            except Exception:
                pass

        # 2. TODAS las categorías inspeccionadas de toda la tabla (SELECT DISTINCT sin límite de 500 filas)
        categories_summary = {}
        for col in nv_cols + aux_cols:
            raw_c = col_map.get(col, col)
            try:
                cursor.execute(f'SELECT DISTINCT "{raw_c}" FROM "{table_name}" WHERE "{raw_c}" IS NOT NULL LIMIT 100;')
                vals = [str(r[0]).strip() for r in cursor.fetchall() if str(r[0]).strip()]
                if vals:
                    categories_summary[col] = vals
            except Exception:
                pass

    df_sample.columns = [standardize_col_name(c) if str(c).lower().strip() != 'file' else 'file' for c in df_sample.columns]

    numeric_stats = {}
    if "valor" in df_sample.columns:
        s_val = pd.to_numeric(df_sample["valor"].astype(str).str.replace(",", "").str.strip(), errors="coerce").dropna()
        if not s_val.empty:
            numeric_stats = {
                "count_numeric": int(len(s_val)),
                "min": float(s_val.min()),
                "max": float(s_val.max()),
                "median": float(s_val.median()),
                "has_decimals": bool((s_val % 1 != 0).any()),
                "values_under_100_pct": float((s_val <= 100).mean() * 100)
            }

    sample_rows = []
    if not df_sample.empty:
        sample_subset = df_sample.drop(columns=[c for c in ["file"] if c in df_sample.columns])
        sample_rows = sample_subset.head(8).to_dict(orient="records")

    # Pre-detección de unidades de precio por unidad física en toda la base de datos
    pre_detected_price_units = {}
    for col, vals in categories_summary.items():
        for v in vals:
            pu = parse_commodity_price_unit(v)
            if pu:
                pre_detected_price_units[v] = pu

    return {
        "table_name": table_name,
        "total_rows": total_rows,
        "all_columns": cols_std,
        "title_columns": title_cols,
        "nv_columns": nv_cols,
        "aux_columns": aux_cols,
        "titles": titles_dict,
        "categories_summary": categories_summary,
        "pre_detected_price_units": pre_detected_price_units,
        "numeric_stats": numeric_stats,
        "sample_rows": sample_rows
    }


def get_available_gemini_models(api_key: str) -> List[Tuple[str, str]]:
    """
    Descubre dinámicamente los modelos Gemini disponibles para la API key del usuario
    mediante ListModels (probando v1beta y v1).
    """
    clean_key = api_key.strip()
    discovered = []

    for ver in ["v1beta", "v1"]:
        try:
            url = f"https://generativelanguage.googleapis.com/{ver}/models?key={clean_key}"
            resp = requests.get(url, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                for m in data.get("models", []):
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        m_name = m.get("name", "").replace("models/", "").strip()
                        if "gemini" in m_name.lower():
                            discovered.append((ver, m_name))
                if discovered:
                    def sort_key(item):
                        name = item[1].lower()
                        if "2.0-flash" in name:
                            return 0
                        if "1.5-flash" in name:
                            return 1
                        if "flash" in name:
                            return 2
                        if "pro" in name:
                            return 3
                        return 4
                    discovered.sort(key=sort_key)
                    return discovered
        except Exception:
            pass

    return [
        ("v1beta", "gemini-2.0-flash"),
        ("v1beta", "gemini-2.0-flash-001"),
        ("v1beta", "gemini-1.5-flash-latest"),
        ("v1beta", "gemini-1.5-flash-002"),
        ("v1beta", "gemini-1.5-flash"),
        ("v1", "gemini-1.5-flash"),
        ("v1beta", "gemini-1.5-pro-latest"),
        ("v1beta", "gemini-1.5-pro"),
        ("v1", "gemini-1.5-pro"),
        ("v1beta", "gemini-pro"),
        ("v1", "gemini-pro"),
    ]


def analyze_with_gemini_api(
    sqlite_summary: Dict[str, Any],
    api_key: str,
    model_name: str = ""
) -> Dict[str, Any]:
    """
    Envía la estructura analítica del SQLite a Google Gemini API para clasificar
    con precisión métricas, unidades, factores y generar el código de mapeo.
    """
    prompt = f"""Eres el Arquitecto Líder de Datos de DATAX Platform.
Tu misión es analizar la estructura y datos de un reporte financiero/económico extraído en SQLite para configurar su Migración a PostgreSQL según los Estándares Oficiales DATAX V2.

### Contexto del Reporte extraído de SQLite:
- Tabla: {sqlite_summary.get('table_name')}
- Columnas: {sqlite_summary.get('all_columns')}
- Títulos: {json.dumps(sqlite_summary.get('titles', {}), ensure_ascii=False)}
- Categorías y Jerarquías presentes (100% de la tabla): {json.dumps(sqlite_summary.get('categories_summary', {}), ensure_ascii=False)}
- Pistas de Precios por Unidad Física pre-detectados: {json.dumps(sqlite_summary.get('pre_detected_price_units', {}), ensure_ascii=False)}
- Estadísticas de 'valor': {json.dumps(sqlite_summary.get('numeric_stats', {}), ensure_ascii=False)}
- Muestra de filas: {json.dumps(sqlite_summary.get('sample_rows', []), ensure_ascii=False)}

### Ejemplos Canónicos de Aprendizaje Oficial (Few-Shot Reference DATAX):
1. Commodities y Futuros Multimoneda (ej. Cacao - Robot 43):
   - Categorías: ["London Futures (£ Sterling/tonne)", "New York Futures (Us$/tonne)", "Icco Daily Price (Us$/tonne)", "Icco Daily Price (Euro/tonne)"]
   - Solución obligatoria DATAX:
     * is_mixed: true
     * base_metric: "precio" (¡NUNCA "moneda" ni "volumen"!)
     * base_unit: "GBP/Tn" (o la primera del reporte)
     * conversion_factor: 1.0
     * get_unit_code:
       def get_unit(row) -> str:
           combined = ' '.join([str(v) for v in row.values if pd.notna(v)]).lower()
           if 'euro' in combined or 'eur' in combined:
               return 'EUR/Tn'
           if '£' in combined or 'sterling' in combined:
               return 'GBP/Tn'
           if any(k in combined for k in ['us$', '$us', 'usd']):
               return 'USD/Tn'
           return 'USD/Tn'
     * get_metric_code:
       def get_metric(row) -> str:
           return 'precio'

2. Tasas de Interés (ej. Tasas Activas / Pasivas - Robot 484):
   - Títulos: "TASAS ACTIVAS EFECTIVAS", Categorías: ["Moneda Nacional", "Moneda Extranjera"]
   - Solución obligatoria DATAX: base_metric: "tasa", base_unit: "%", conversion_factor: 1.0, is_mixed: false.

3. Balances Monetarios Multimoneda (ej. Deuda Pública - Robot 270):
   - Categorías: ["Sector Público - MN", "Sector Privado - ME", "Bonos - UFV"]
   - Solución obligatoria DATAX: base_metric: "moneda", base_unit: "BOB", is_mixed: true, factor: 1000.0.
     get_unit devuelve 'BOB' para MN, 'USD' para ME, 'UFV' para UFV.

4. Balances Financieros con Coeficientes, Ratios o Porcentajes (ej. Ponderación de Activos y Suficiencia Patrimonial - Robot 321):
   - Categorías: ["Activos Ponderados por Riesgo", "Capital Primario Inicial", "Coeficiente de Adecuación Patrimonial", "Coeficiente de Ponderación del Activo", "Coeficiente de Inversión en Activos FIJOS... (Limite Max. 100%)"]
   - Solución obligatoria DATAX:
     * is_mixed: true (¡OBLIGATORIAMENTE true! JAMÁS unificar todo a moneda porque los coeficientes/ratios no son dinero).
     * base_metric: "moneda"
     * base_unit: "BOB"
     * conversion_factor: 1.0 (¡OBLIGATORIAMENTE 1.0! Jamás multiplicar por miles o millones un balance donde conviven coeficientes o porcentajes).
     * get_metric_code:
       def get_metric(row) -> str:
           nv1 = str(row.get('nv1', '')).lower()
           if 'coeficiente' in nv1 or 'ratio' in nv1:
               return 'porcentaje'
           return 'moneda'
     * get_unit_code:
       def get_unit(row) -> str:
           nv1 = str(row.get('nv1', '')).lower()
           if 'coeficiente' in nv1 or 'ratio' in nv1:
               return '%'
           return 'BOB'

### Reglas Oficiales de DATAX V2:
1. 'metrica' (character varying 255):
   - 'precio': Cotizaciones internacionales, futuros o commodities por unidad física (ej. USD/Tn, GBP/Tn, EUR/Tn, USD/Bbl, USc/lb). En estos reportes la métrica DEBE SER 'precio' (¡NUNCA 'moneda' ni 'volumen'!), la unidad DEBE SER la razón combinada Moneda/Unidad y el factor SIEMPRE ES 1.0.
   - 'tasa': Tasas de interés anuales, encaje o rendimiento. Unidad: '%', Factor: 1.0.
   - 'moneda': Montos dinerarios absolutos (saldos, depósitos, activos). Unidades: 'BOB', 'USD', 'UFV'. Factor: 1, 1000 o 1000000.
   - 'porcentaje': Participaciones porcentuales, ponderaciones (%). Unidad: '%', Factor: 1.0.
   - 'tipo_cambio': Cotizaciones de divisas (BOB/USD, BOB/UFV). Factor: 1.0.
   - 'volumen': Cantidades físicas puras sin dinero en el numerador (ej. 1500 Tn).
   - 'indice': Índices base 100.
   - 'ratio': Coeficientes o multiplicadores ('veces').

2. Filas Mixtas ('is_mixed'):
   - PROHIBICIÓN ESTRICTA DE UNIFORMAR A MONEDA EN BALANCES CON COEFICIENTES O RATIOS:
     Si en un reporte financiero conviven cuentas de balance dinerarias con conceptos como 'COEFICIENTE', 'RATIO', 'PONDERACIÓN', 'LÍMITE' o '%', el reporte ES OBLIGATORIAMENTE MIXTO (is_mixed = true). La IA NUNCA debe decir 'como la mayoría son montos monetarios, todo debe ser BOB'. Asignar BOB a un Coeficiente de Adecuación Patrimonial de 13.92% es un error inadmisible en DATAX. Debe discriminar get_metric ('porcentaje'/'ratio' vs 'moneda'), get_unit ('%' vs 'BOB'), y el conversion_factor DEBE SER estrictamente 1.0.

   - Si conviven diferentes unidades físicas o monedas (ej. GBP/Tn, USD/Tn, EUR/Tn), is_mixed=true.
   - get_unit(row) DEBE tener una regla explícita para CADA moneda/unidad presente en la tabla. NUNCA mapees 'Euro' a 'USD'.
   - ¡ADVERTENCIA CRÍTICA!: 'ICCO' es la Organización Internacional del Cacao, NO es una moneda. ICCO publica precios TANTO en Dólares (Us$/tonne) como en Euros (Euro/tonne). Por tanto, NUNCA clasifiques una fila como 'USD' basándote en la palabra 'icco'. Debes clasificar como 'EUR/Tn' si dice 'euro'/'eur'/'€', y como 'USD/Tn' si dice 'us$'/'$us'/'usd'.

Responde ÚNICA Y EXCLUSIVAMENTE un objeto JSON válido (sin texto antes ni después) con la siguiente estructura exacta:
{{
  "is_mixed": boolean,
  "base_metric": string,
  "base_unit": string,
  "conversion_factor": number,
  "explanation": "Explicación técnica concisa (en español) de por qué se asignó esta métrica, unidad y factor, detallando cómo se detectó en títulos y valores.",
  "get_metric_code": "def get_metric(row) -> str:\n    return 'precio'",
  "get_unit_code": "def get_unit(row) -> str:\n    ..."
}}
"""

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "responseMimeType": "application/json"
        }
    }

    clean_key = api_key.strip()
    available_models = get_available_gemini_models(clean_key)
    if model_name:
        available_models.insert(0, ("v1beta", model_name))

    last_error = ""

    for ver, m_id in available_models:
        url = f"https://generativelanguage.googleapis.com/{ver}/models/{m_id}:generateContent?key={clean_key}"
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=20)
            if resp.status_code == 400 and "responseMimeType" in resp.text:
                fallback_payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1}
                }
                resp = requests.post(url, headers=headers, json=fallback_payload, timeout=20)

            if resp.status_code == 200:
                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if candidates:
                    raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "").strip()
                    if raw_text.startswith("```json"):
                        raw_text = raw_text[7:]
                    if raw_text.startswith("```"):
                        raw_text = raw_text[3:]
                    if raw_text.endswith("```"):
                        raw_text = raw_text[:-3]
                    raw_text = raw_text.strip()

                    parsed = json.loads(raw_text)
                    parsed["source"] = f"gemini_agent ({m_id})"
                    return parsed
            else:
                last_error = f"{ver}/{m_id}: HTTP {resp.status_code} - {resp.text[:180]}"
                continue
        except Exception as ex:
            last_error = f"{ver}/{m_id}: {str(ex)}"
            continue

    return {"error": f"No se pudo consultar la API de Gemini con los modelos disponibles. Detalle: {last_error}"}


def _flatten_titles(titles_dict: dict) -> str:
    parts = []
    for v in (titles_dict or {}).values():
        if isinstance(v, (list, tuple, set)):
            parts.extend([str(x) for x in v if x])
        elif v:
            parts.append(str(v))
    return " ".join(parts).lower()


def analyze_with_heuristic_engine(sqlite_summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Motor heurístico avanzado de respaldo (100% offline).
    Inspecciona títulos, niveles y valores con reglas semánticas y estadísticas.
    """
    titles_dict = sqlite_summary.get("titles", {})
    categories = sqlite_summary.get("categories_summary", {})
    num_stats = sqlite_summary.get("numeric_stats", {})

    all_title_text = _flatten_titles(titles_dict)
    all_cat_text = " ".join([" ".join(v) for v in categories.values()]).lower()

    # Detección de escala monetaria
    factor = 1.0
    if "millones" in all_title_text:
        factor = 1000000.0
    elif "miles" in all_title_text:
        factor = 1000.0

    # 1. ¿Son precios de commodities o cotizaciones por unidad física (ej. USD/Tn, GBP/Tn, EUR/Tn, USD/Bbl, etc.)?
    price_units_detected = {}
    for col, vals in categories.items():
        for v in vals:
            parsed_u = parse_commodity_price_unit(v)
            if parsed_u:
                price_units_detected[v] = parsed_u

    is_price_keyword = any(k in all_title_text or k in all_cat_text for k in [
        "futures", "futuros", "daily price", "price", "precio", "precios", "spot", "icco", "cacao", "cocoa", "wti", "brent"
    ])
    has_slash_unit = any(k in all_cat_text for k in ["/tonne", "/tonelada", "/barril", "/bbl", "/lb", "/kg", "/mwh"])

    if price_units_detected or (is_price_keyword and has_slash_unit):
        unique_units = list(dict.fromkeys(price_units_detected.values()))
        is_mixed_prices = len(unique_units) > 1
        base_unit = unique_units[0] if unique_units else "USD/Tn"

        explanation = (
            f"El reporte corresponde a Precios Internacionales / Cotizaciones de Futuros de Commodities ({', '.join(unique_units) if unique_units else base_unit}). "
            "Al tratarse de cotizaciones de mercado expresadas por unidad de peso o volumen físico (ej. GBP/Tn, USD/Tn, EUR/Tn), "
            "la métrica oficial según el estándar DATAX es 'precio', la unidad de medida es la razón combinada Moneda/Unidad "
            "y el factor de conversión es estrictamente 1.0 (no se multiplica por miles ni millones)."
        )

        if is_mixed_prices:
            metric_code = "def get_metric(row) -> str:\n    return 'precio'"

            # Función get_unit con discriminación exacta por cada categoría
            unit_code_lines = [
                "def get_unit(row) -> str:",
                "    combined = ' '.join([str(v) for v in row.values if pd.notna(v)]).lower()",
            ]
            for raw_val, parsed_u in price_units_detected.items():
                unit_code_lines.append(f"    if '{raw_val.lower()}' in combined:\n        return '{parsed_u}'")
            unit_code_lines.append("    if any(k in combined for k in ['£', 'sterling', 'gbp']):\n        return 'GBP/Tn'")
            unit_code_lines.append("    if any(k in combined for k in ['euro', 'eur', '€']):\n        return 'EUR/Tn'")
            unit_code_lines.append("    if any(k in combined for k in ['us$', '$us', 'usd', 'dolar', 'dólar']):\n        return 'USD/Tn'")
            unit_code_lines.append(f"    return '{base_unit}'")

            return {
                "is_mixed": True,
                "base_metric": "precio",
                "base_unit": base_unit,
                "conversion_factor": 1.0,
                "explanation": explanation,
                "get_metric_code": metric_code,
                "get_unit_code": "\n".join(unit_code_lines),
                "source": "heuristic_fallback"
            }
        else:
            return {
                "is_mixed": False,
                "base_metric": "precio",
                "base_unit": base_unit,
                "conversion_factor": 1.0,
                "explanation": explanation,
                "get_metric_code": "def get_metric(row) -> str:\n    return 'precio'",
                "get_unit_code": f"def get_unit(row) -> str:\n    return '{base_unit}'",
                "source": "heuristic_fallback"
            }

    # 2. ¿Es tasa de interés?
    is_rate_report = (
        any(k in all_title_text for k in ["tasas activas", "tasas pasivas", "tasa de interes", "tasas de interés", "rendimiento"]) or
        ("tasa" in all_title_text and num_stats.get("max", 999) <= 100)
    )

    if is_rate_report:
        explanation = (
            "El reporte corresponde a Tasas de Interés (identificado en títulos oficiales). "
            "A pesar de que existan categorías como 'Moneda Nacional', 'UFV' o 'MVDOL', "
            "los valores representan el porcentaje de rendimiento o interés cobrado/pagado. "
            "Por estándar DATAX, la métrica es 'tasa', la unidad es '%' y el factor de conversión es 1.0."
        )
        return {
            "is_mixed": False,
            "base_metric": "tasa",
            "base_unit": "%",
            "conversion_factor": 1.0,
            "explanation": explanation,
            "get_metric_code": "def get_metric(row) -> str:\n    return 'tasa'",
            "get_unit_code": "def get_unit(row) -> str:\n    return '%'",
            "source": "heuristic_fallback"
        }

    # 3. ¿Es porcentaje o participación?
    if "%" in all_title_text or "porcentaje" in all_title_text or "participacion" in all_title_text:
        return {
            "is_mixed": False,
            "base_metric": "porcentaje",
            "base_unit": "%",
            "conversion_factor": 1.0,
            "explanation": "El reporte mide variaciones o participaciones porcentuales. Métrica: 'porcentaje', Unidad: '%', Factor: 1.0.",
            "get_metric_code": "def get_metric(row) -> str:\n    return 'porcentaje'",
            "get_unit_code": "def get_unit(row) -> str:\n    return '%'",
            "source": "heuristic_fallback"
        }

    # 4. ¿Es tipo de cambio?
    if "tipo de cambio" in all_title_text or "cotizacion" in all_title_text or "cotización" in all_title_text:
        unit = "BOB/UFV" if "ufv" in all_title_text else "BOB/USD"
        return {
            "is_mixed": False,
            "base_metric": "tipo_cambio",
            "base_unit": unit,
            "conversion_factor": 1.0,
            "explanation": f"El reporte refleja tipos de cambio o cotizaciones de divisas. Métrica: 'tipo_cambio', Unidad: '{unit}', Factor: 1.0.",
            "get_metric_code": "def get_metric(row) -> str:\n    return 'tipo_cambio'",
            "get_unit_code": f"def get_unit(row) -> str:\n    return '{unit}'",
            "source": "heuristic_fallback"
        }

    # 5. Monedas y posibles filas mixtas
    detected_currencies = set()
    has_mixed_pct = False
    has_mixed_coef = False
    for col, vals in categories.items():
        for v in vals:
            vu = v.upper()
            words = set(re.split(r'[\\s/()]+', vu))
            if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in vu:
                detected_currencies.add("BOB")
            if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in vu:
                detected_currencies.add("USD")
            if "UFV" in words:
                detected_currencies.add("UFV")
            if "%" in vu or "PARTICIPACI" in vu or "TASA" in vu or "PORCENTAJE" in vu:
                has_mixed_pct = True
            if any(k in vu for k in ["COEFICIENTE", "RATIO", "PONDERACI", "SUFICIENCIA", "LIMITE", "LÍMITE"]):
                has_mixed_coef = True

    if has_mixed_coef or has_mixed_pct:
        factor = 1.0

    is_mixed = len(detected_currencies) > 1 or has_mixed_pct or has_mixed_coef
    base_unit = "USD" if ("USD" in detected_currencies and "BOB" not in detected_currencies) else "BOB"

    if is_mixed:
        explanation = (
            f"Se detectaron múltiples monedas o categorías mixtas en las jerarquías: {sorted(list(detected_currencies))}. "
            "Se implementa mapeo dinámico fila por fila para asignar la unidad correcta (BOB, USD, UFV, %) según el texto de cada registro."
        )
        metric_code = """def get_metric(row) -> str:
    combined = " ".join([str(v).upper() for v in row.values if pd.notna(v)])
    if any(k in combined for k in ["COEFICIENTE", "RATIO", "PONDERACI", "%", "PARTICIPACI", "PORCENTAJE"]):
        return "porcentaje"
    if "TASA" in combined or "RENDIMIENTO" in combined:
        return "tasa"
    if "TIPO DE CAMBIO" in combined or "COTIZACION" in combined:
        return "tipo_cambio"
    return "moneda" """

        unit_code = """def get_unit(row) -> str:
    combined = " ".join([str(v).upper() for v in row.values if pd.notna(v)])
    if any(k in combined for k in ["COEFICIENTE", "RATIO", "PONDERACI", "%", "PARTICIPACI", "PORCENTAJE"]):
        return "%"
    words = set(re.split(r'[\\s/()]+', combined))
    if "UFV" in words:
        return "UFV"
    if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in combined:
        return "USD"
    if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in combined:
        return "BOB"
    return "BOB" """

        return {
            "is_mixed": True,
            "base_metric": "moneda",
            "base_unit": base_unit,
            "conversion_factor": factor,
            "explanation": explanation,
            "get_metric_code": metric_code,
            "get_unit_code": unit_code,
            "source": "heuristic_fallback"
        }

    return {
        "is_mixed": False,
        "base_metric": "moneda",
        "base_unit": base_unit,
        "conversion_factor": factor,
        "explanation": f"Reporte monetario homogéneo en {base_unit}. Factor de conversión detectado: {factor:g}.",
        "get_metric_code": "def get_metric(row) -> str:\n    return 'moneda'",
        "get_unit_code": f"def get_unit(row) -> str:\n    return '{base_unit}'",
        "source": "heuristic_fallback"
    }



def validate_and_sanitize_agent_result(
    parsed: Dict[str, Any],
    sqlite_summary: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Capa de salvaguarda y validación de estándares DATAX V2 sobre las respuestas
    de Gemini o motores de IA. Corrige inconsistencias conocidas (ej. clasificar
    precios de commodities como 'moneda' en lugar de 'precio', omitir la unidad física
    en el denominador, o clasificar tasas como moneda).
    """
    categories = sqlite_summary.get("categories_summary", {})
    all_title_text = _flatten_titles(sqlite_summary.get("titles", {}))

    # 1. Detectar unidades de precios de commodities / materias primas
    price_units_detected = sqlite_summary.get("pre_detected_price_units", {})
    if not price_units_detected:
        for col, vals in categories.items():
            for v in vals:
                parsed_u = parse_commodity_price_unit(v)
                if parsed_u:
                    price_units_detected[v] = parsed_u

    is_commodity_report = bool(price_units_detected) or any(
        k in all_title_text for k in ["futures", "futuros", "daily price", "cacao", "cocoa", "wti", "brent", "petroleo", "petróleo"]
    )

    if price_units_detected or is_commodity_report:
        first_unit = list(price_units_detected.values())[0] if price_units_detected else "USD/Tn"

        # Corrección métrica a 'precio'
        if parsed.get("base_metric") in ["moneda", "volumen"]:
            parsed["base_metric"] = "precio"
            if "explanation" in parsed:
                parsed["explanation"] += " (Ajuste oficial DATAX: La métrica se estableció como 'precio' al ser cotizaciones/futuros por unidad de peso o volumen)."

        # Corrección unidad métrica si falta denominador
        curr_base_unit = parsed.get("base_unit", "")
        if curr_base_unit in ["GBP", "USD", "EUR", "BOB", "Tn", "Kg", "Bbl", "moneda", ""]:
            parsed["base_unit"] = first_unit

        # Factor siempre 1.0 para precios
        parsed["conversion_factor"] = 1.0

        # Verificación estricta de get_unit_code:
        unit_code = parsed.get("get_unit_code", "")
        has_euro_cat = any("EUR" in u for u in price_units_detected.values())
        has_gbp_cat = any("GBP" in u for u in price_units_detected.values())
        has_usd_cat = any("USD" in u for u in price_units_detected.values())

        needs_unit_code_fix = (
            not any("/" in line for line in unit_code.splitlines() if "return" in line)
            or (has_euro_cat and "EUR/Tn" not in unit_code)
            or (has_gbp_cat and "GBP/Tn" not in unit_code)
            or (has_usd_cat and "USD/Tn" not in unit_code)
        )

        if needs_unit_code_fix and price_units_detected:
            lines = [
                "def get_unit(row) -> str:",
                "    combined = ' '.join([str(v) for v in row.values if pd.notna(v)]).lower()"
            ]
            # Mapeo exacto por categoría primero:
            for raw_v, u in price_units_detected.items():
                clean_v = raw_v.lower().replace("'", "\\'")
                lines.append(f"    if '{clean_v}' in combined:")
                lines.append(f"        return '{u}'")
            # Reglas generales por palabras clave:
            lines.append("    if any(k in combined for k in ['euro', 'eur', '€']):")
            lines.append("        return 'EUR/Tn'")
            lines.append("    if any(k in combined for k in ['£', 'sterling', 'gbp']):")
            lines.append("        return 'GBP/Tn'")
            lines.append("    if any(k in combined for k in ['us$', '$us', 'usd', 'dolar', 'dólar']):")
            lines.append("        return 'USD/Tn'")
            lines.append(f"    return '{first_unit}'")
            parsed["get_unit_code"] = "\n".join(lines)
            parsed["get_metric_code"] = "def get_metric(row) -> str:\n    return 'precio'"
            parsed["is_mixed"] = len(set(price_units_detected.values())) > 1

    # 3. Salvaguarda Oficial DATAX para Balances con Coeficientes / Ratios / Porcentajes (ej. Robot 321)
    has_coef_or_ratio = False
    for col, vals in categories.items():
        for v in vals:
            vu = v.upper()
            if any(k in vu for k in ["COEFICIENTE", "RATIO", "PONDERACION", "PONDERACIÓN", "SUFICIENCIA PATRIMONIAL", "ADECUACION PATRIMONIAL", "ADECUACIÓN PATRIMONIAL", "LIMITE MAX", "LÍMITE MAX"]):
                has_coef_or_ratio = True
                break
        if has_coef_or_ratio:
            break

    if has_coef_or_ratio:
        # En ningún caso puede ser homogéneo en moneda pura si conviven coeficientes
        parsed["is_mixed"] = True
        parsed["conversion_factor"] = 1.0  # Coeficientes jamás se multiplican por miles ni millones
        if parsed.get("base_metric") != "moneda":
            parsed["base_metric"] = "moneda"
        if not parsed.get("base_unit"):
            parsed["base_unit"] = "BOB"

        unit_code = parsed.get("get_unit_code", "")
        metric_code = parsed.get("get_metric_code", "")

        # Si el código de unidad devuelto por la IA no contempla coeficientes o devuelve siempre una constante:
        # Para evitar colisiones con títulos del documento ('Ponderación') o buckets de riesgo ('Activo con Riesgo de 10%'):
        parsed["get_unit_code"] = """def get_unit(row) -> str:
    nv1 = str(row.get('nv1', '')).lower()
    if 'coeficiente' in nv1 or 'ratio' in nv1:
        return '%'
    # Monedas en niveles jerárquicos
    nv_all = ' '.join([str(row.get(c, '')).lower() for c in ['nv1', 'nv2', 'nv3', 'nv4', 'nv5'] if pd.notna(row.get(c))])
    words = set(re.split(r'[\\s/()]+', nv_all))
    if 'ufv' in words:
        return 'UFV'
    if any(k in nv_all for k in ['usd', 'dolar', 'dólar', 'me', 'moneda extranjera']):
        return 'USD'
    return 'BOB'"""

        parsed["get_metric_code"] = """def get_metric(row) -> str:
    nv1 = str(row.get('nv1', '')).lower()
    if 'coeficiente' in nv1 or 'ratio' in nv1:
        return 'porcentaje'
    return 'moneda'"""

        if "explanation" in parsed and "coeficiente" not in parsed["explanation"].lower():
            parsed["explanation"] += (
                " (Ajuste oficial DATAX: Se detectaron coeficientes y porcentajes de ponderación/suficiencia coexistiendo con saldos monetarios. "
                "Por norma DATAX V2, el reporte es estrictamente mixto (`is_mixed: true`) para no clasificar coeficientes numéricos como montos en BOB)."
            )

    # 2. Salvaguarda para TASAS DE INTERÉS
    elif any(k in all_title_text for k in ["tasas de interes", "tasas de interés", "tasas activas", "tasas pasivas"]):
        if parsed.get("base_metric") in ["moneda", "porcentaje", ""]:
            parsed["base_metric"] = "tasa"
        parsed["base_unit"] = "%"
        parsed["conversion_factor"] = 1.0
        parsed["is_mixed"] = False
        parsed["get_metric_code"] = "def get_metric(row) -> str:\n    return 'tasa'"
        parsed["get_unit_code"] = "def get_unit(row) -> str:\n    return '%'"

    return parsed


def run_agent_sqlite_analysis(
    sqlite_path: str,
    api_key: str = "",
    model_name: str = ""
) -> Dict[str, Any]:
    """
    Función principal ejecutora:
    Extrae resumen del SQLite y ejecuta Gemini API con auto-descubrimiento de modelos.
    Si no hay API key o hay error de red/cuota, utiliza el motor heurístico avanzado de respaldo.
    """
    summary = extract_sqlite_summary_for_agent(sqlite_path)
    if "error" in summary:
        return summary

    if api_key and api_key.strip():
        gemini_res = analyze_with_gemini_api(summary, api_key=api_key.strip(), model_name=model_name)
        if "error" not in gemini_res:
            gemini_res = validate_and_sanitize_agent_result(gemini_res, summary)
            gemini_res["sqlite_summary"] = summary
            return gemini_res
        else:
            fallback_res = analyze_with_heuristic_engine(summary)
            fallback_res = validate_and_sanitize_agent_result(fallback_res, summary)
            fallback_res["agent_warning"] = f"Aviso del Agente IA: Falló la llamada a Gemini ({gemini_res.get('error')}). Se aplicó el análisis heurístico avanzado de respaldo."
            fallback_res["sqlite_summary"] = summary
            return fallback_res

    heur_res = analyze_with_heuristic_engine(summary)
    heur_res = validate_and_sanitize_agent_result(heur_res, summary)
    heur_res["sqlite_summary"] = summary
    return heur_res
