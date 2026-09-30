from core.agent_analyzer import parse_commodity_price_unit
import unicodedata
"""Lógica de generación y preparación de robots y DAGs de migración (PostgreSQL / Airflow V2)."""

import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text



def standardize_col_name(col: str) -> str:
    """Normaliza nombres de columnas a snake_case valido para PostgreSQL (sin espacios ni acentos)."""
    cleaned = re.sub(r'[\t\xa0]+', '', str(col)).strip()
    s = re.sub(r'\s+', '_', cleaned.lower())
    s = unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode('utf-8')
    s = re.sub(r'[^a-z0-9_]', '', s)
    return s

def scan_conversion_outputs(repo_path: str) -> List[Dict]:
    """Escanea models/conversion/ en busca de familias y archivos .sqlite generados listos para migrar."""
    conv_dir = os.path.join(repo_path, "models", "conversion")
    if not os.path.isdir(conv_dir):
        return []

    families = []
    for item in sorted(os.listdir(conv_dir)):
        item_path = os.path.join(conv_dir, item)
        if not os.path.isdir(item_path):
            continue

        match = re.search(r"(C_[A-Z]{2}_\d{9})", item)
        if not match:
            continue

        parent_code = match.group(1)
        migration_parent = parent_code.replace("C_", "M_")
        reports = []

        for f in sorted(os.listdir(item_path)):
            fpath = os.path.join(item_path, f)
            if not os.path.isfile(fpath):
                continue
            lower = f.lower()
            if lower.endswith(".sqlite"):
                rep_match = re.search(r"(D_[A-Z]{2}_\d{9}_\d{2})", f)
                rep_code = rep_match.group(1) if rep_match else os.path.splitext(f)[0]
                py_file = os.path.join(item_path, f"{rep_code}.py")
                reports.append({
                    "code": rep_code,
                    "sqlite_file": fpath,
                    "has_conversion_py": os.path.isfile(py_file)
                })

        if reports:
            families.append({
                "parent_code": parent_code,
                "migration_parent": migration_parent,
                "folder": item_path,
                "reports": reports
            })

    return families


def get_migration_db_info(report_code: str, engine) -> Optional[Dict]:
    """Obtiene metadatos del reporte desde la tabla report de platform_db."""
    query = text(
        "SELECT id_report, code, name, storage_table, conversion_factor, "
        "decimal_separator, load_scope, migrated_to "
        "FROM report WHERE code = :code LIMIT 1;"
    )
    try:
        with engine.connect() as conn:
            result = conn.execute(query, {"code": report_code}).fetchone()
            if not result:
                return None
            return {
                "id_report": result[0],
                "code": result[1],
                "name": result[2],
                "storage_table": result[3],
                "conversion_factor": result[4],
                "decimal_separator": result[5],
                "load_scope": result[6],
                "migrated_to": result[7]
            }
    except Exception as e:
        print(f"Error al consultar report en platform_db: {e}")
        return None


def inspect_sqlite_structure(sqlite_path: str, table_name: str = "", extra_text: str = "") -> Dict:
    """Inspecciona la tabla SQLite para obtener columnas, muestras y sugerir metricas y unidades."""
    with sqlite3.connect(sqlite_path) as conn:
        cursor = conn.cursor()
        if not table_name:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('columns_to_review', 'sqlite_sequence');")
            tables = [r[0] for r in cursor.fetchall()]
            table_name = tables[0] if tables else ""
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        pragma_cols = [row[1] for row in cursor.fetchall()]
        df = pd.read_sql_query(f'SELECT * FROM "{table_name}";', conn)

    df.columns = [standardize_col_name(c) if str(c).lower().strip() != 'file' else 'file' for c in df.columns]
    cols_clean = [standardize_col_name(c) for c in pragma_cols if str(c).lower().strip() != 'file']

    title_cols = [c for c in cols_clean if c.startswith('titulo')]
    nv_cols = [c for c in cols_clean if c.startswith('nv')]
    aux_cols = [c for c in cols_clean if c not in title_cols and c not in nv_cols and c not in ['fecha', 'valor']]

    combined_titles = ""
    for t_col in title_cols:
        if t_col in df.columns:
            vals = df[t_col].dropna().astype(str).tolist()
            if vals:
                combined_titles += " " + " ".join(vals)
    combined_titles_lower = combined_titles.lower()

    nv1_sample = " ".join(df["nv1"].dropna().head(10).astype(str)).lower() if "nv1" in df.columns else ""
    full_header_text = (combined_titles_lower + " " + nv1_sample + " " + str(extra_text or "").lower()).strip()
    full_norm = unicodedata.normalize('NFD', full_header_text).encode('ascii', 'ignore').decode('utf-8')
    titles_norm = unicodedata.normalize('NFD', combined_titles_lower).encode('ascii', 'ignore').decode('utf-8')

    # Deteccion de Precios / Cotizaciones de Commodities por unidad fisica (USD/Tn, GBP/Tn, EUR/Tn, etc.)
    commodity_price_units = []
    for c in nv_cols + aux_cols:
        if c in df.columns:
            for v in df[c].dropna().unique():
                pu = parse_commodity_price_unit(str(v))
                if pu and pu not in commodity_price_units:
                    commodity_price_units.append(pu)

    # Deteccion de factor sugerido
    suggested_factor = 1.0
    if "millones" in full_norm:
        suggested_factor = 1000000.0
    elif "miles" in full_norm:
        suggested_factor = 1000.0

    # Deteccion de moneda base y tipos de cambio
    has_usd_kw = any(k in full_norm for k in ["dolares", "usd", "$us", "moneda extranjera", "del exterior"])
    has_bob_kw = any(k in full_norm for k in ["bolivianos", "bob", "moneda nacional", " bs", "bs."])

    # Inicializar sugerencias de métrica/unidad
    suggested_metric = None
    suggested_unit = None

    # 1. Energia y Potencia Electrica (GWh, MWh, kWh, Wh, GW, MW, kW)
    if re.search(r'[\(\[\s]gwh[\)\]\s]|\bgwh\b', titles_norm) or re.search(r'[\(\[\s]gwh[\)\]\s]|\bgwh\b', full_norm):
        suggested_metric = "energia"
        suggested_unit = "GWh"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]mwh[\)\]\s]|\bmwh\b', titles_norm) or re.search(r'[\(\[\s]mwh[\)\]\s]|\bmwh\b', full_norm):
        suggested_metric = "energia"
        suggested_unit = "MWh"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]kwh[\)\]\s]|\bkwh\b', titles_norm) or re.search(r'[\(\[\s]kwh[\)\]\s]|\bkwh\b', full_norm):
        suggested_metric = "energia"
        suggested_unit = "kWh"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]wh[\)\]\s]|\bwh\b', titles_norm) or re.search(r'[\(\[\s]wh[\)\]\s]|\bwh\b', full_norm):
        suggested_metric = "energia"
        suggested_unit = "Wh"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]gw[\)\]\s]|\bgw\b', titles_norm) or re.search(r'[\(\[\s]gw[\)\]\s]|\bgw\b', full_norm):
        suggested_metric = "potencia"
        suggested_unit = "GW"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]mw[\)\]\s]|\bmw\b', titles_norm) or re.search(r'[\(\[\s]mw[\)\]\s]|\bmw\b', full_norm):
        suggested_metric = "potencia"
        suggested_unit = "MW"
        suggested_factor = 1.0
    elif re.search(r'[\(\[\s]kw[\)\]\s]|\bkw\b', titles_norm) or re.search(r'[\(\[\s]kw[\)\]\s]|\bkw\b', full_norm):
        suggested_metric = "potencia"
        suggested_unit = "kW"
        suggested_factor = 1.0
    elif any(k in full_norm for k in ["despacho de carga", "demanda de energia", "generacion electrica", "consumo electrico"]):
        suggested_metric = "energia"
        suggested_unit = "GWh" if "gwh" in full_norm else ("MWh" if "mwh" in full_norm else "MWh")
        suggested_factor = 1.0
    # 2. Tipos de cambio
    elif "tipo de cambio" in full_norm or "cotizacion" in full_norm or "paridad" in full_norm:
        suggested_metric = "tipo_cambio"
        suggested_factor = 1.0
        if "ufv" in full_norm:
            suggested_unit = "BOB/UFV"
        else:
            suggested_unit = "BOB/USD"
    # 3. Tasas
    elif ("tasa" in full_norm or "tasas" in full_norm or "rendimiento" in full_norm) and suggested_factor <= 1.0:
        suggested_metric = "tasa"
        suggested_unit = "%"
        suggested_factor = 1.0
    # 4. Porcentajes y ratios
    elif ("porcentaje" in full_norm or "%" in full_norm) and suggested_factor <= 1.0:
        suggested_metric = "porcentaje"
        suggested_unit = "%"
        suggested_factor = 1.0
    # 5. Indices
    elif "indice" in full_norm:
        suggested_metric = "indice"
        match_base = re.search(r"(\d{4}\s*=\s*100)", full_norm)
        suggested_unit = match_base.group(1).replace(" ", "") if match_base else "puntos"
        suggested_factor = 1.0
    # 6. Volumen / Hidrocarburos / Peso
    elif any(k in full_norm for k in ["toneladas", "tonelada", "tm", "tn"]):
        suggested_metric = "volumen"
        suggested_unit = "Tn"
        suggested_factor = 1.0
    elif re.search(r'\b(mmpcd|mpcd)\b', full_norm):
        suggested_metric = "volumen"
        suggested_unit = "MMpcd"
        suggested_factor = 1.0
    elif re.search(r'\b(bbl|barriles)\b', full_norm):
        suggested_metric = "volumen"
        suggested_unit = "Bbl"
        suggested_factor = 1.0
    elif re.search(r'\b(m3|metros cubicos)\b', full_norm):
        suggested_metric = "volumen"
        suggested_unit = "m3"
        suggested_factor = 1.0
    elif re.search(r'\b(litros|lts)\b', full_norm):
        suggested_metric = "volumen"
        suggested_unit = "L"
        suggested_factor = 1.0
    # 7. Clima
    elif any(k in full_norm for k in ["temperatura", "celsius", "centigrados"]) or "°c" in full_header_text.lower():
        suggested_metric = "temperatura"
        suggested_unit = "°C"
        suggested_factor = 1.0
    elif any(k in full_norm for k in ["precipitacion", "pluviosidad", "lluvia"]) or "mm" in full_norm:
        suggested_metric = "precipitacion"
        suggested_unit = "mm"
        suggested_factor = 1.0
    # 8. Conteo / Reclamos / Cantidades / Transacciones / Personas / Unidades
    count_keywords = [
        "reclamo", "reclamos", "queja", "quejas", "sancion", "sanciones", "multa", "multas",
        "solicitud", "solicitudes", "transaccion", "transacciones", "operacion", "operaciones",
        "conteo", "cantidad", "numero de", "nro de", "nro.", "nro ", "total de",
        "personas", "casos", "clientes", "cuentas", "usuarios", "afiliados", "empleados",
        "trabajadores", "beneficiarios", "poblacion", "unidades", "licencias", "polizas",
        "contratos", "visitas", "llamadas"
    ]
    has_count_kw = any(k in full_norm for k in count_keywords)
    has_monetary_kw = any(k in full_norm for k in [
        "bolivianos", "dolares", "dólares", "usd", "bob", " bs", "bs.", "moneda nacional", "moneda extranjera",
        "monto", "saldo", "cartera", "deposito", "depositos", "capital", "utilidad", "activo", "pasivo",
        "patrimonio", "ingresos", "gastos", "credito", "creditos", "costo", "financiero", "financiera",
        "subasta", "bonos", "letras", "adjudicad", "tgn", "bcb"
    ])

    has_reclamo_kw = any(k in full_norm for k in ["reclamo", "reclamos", "queja", "quejas", "sancion", "sanciones", "multa", "multas"])

    # 8/9. Conteo o Moneda: solo si ninguna categoría de la cadena anterior aplica
    if commodity_price_units:
        suggested_metric = "precio"
        suggested_unit = commodity_price_units[0]
        suggested_factor = 1.0
        if len(commodity_price_units) > 1:
            has_mixed_rows = True
    elif suggested_metric not in ["energia", "potencia", "tipo_cambio", "tasa", "porcentaje", "indice", "volumen", "temperatura", "precipitacion"]:
        if has_reclamo_kw or (has_count_kw and not has_monetary_kw and suggested_factor <= 1.0):
            suggested_metric = "conteo"
            suggested_unit = "reclamos" if has_reclamo_kw else "unidades"
            suggested_factor = 1.0
        else:
            suggested_metric = "moneda"
            suggested_unit = "USD" if (has_usd_kw and not has_bob_kw) else "BOB"


    # Deteccion de hechos multiples (facts/metricas), monedas, energia y filas hibridas
    detected_currencies = set()
    has_mixed_rows = False
    found_percent = False
    found_ratio = False
    found_tasa = False
    found_energy = set()
    found_count_in_rows = False
    found_indice_secondary = False
    detected_indice_unit = "puntos"

    # Escanear nv_cols Y title_cols para detectar hechos adicionales en filas
    for col in (nv_cols + title_cols):
        if col in df.columns:
            str_vals = df[col].dropna().astype(str).unique().tolist()
            for v in str_vals:
                vu = v.upper()
                vl = v.lower()
                words = set(re.split(r'[\s/()]+', vu))

                # Detección de monedas en filas
                if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in vu:
                    detected_currencies.add("BOB")
                if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in vu:
                    detected_currencies.add("USD")
                if "UFV" in words:
                    detected_currencies.add("UFV")
                if "BS/USD" in vu or "BOB/USD" in vu or ("TIPO DE CAMBIO" in vu and any(w in ["USD", "DOLAR", "DÓLAR"] for w in words)):
                    detected_currencies.add("BOB/USD")
                if "BS/UFV" in vu or "BOB/UFV" in vu or ("TIPO DE CAMBIO" in vu and "UFV" in words):
                    detected_currencies.add("BOB/UFV")

                # Detección de unidades de energía/potencia en filas
                if "GWH" in words:
                    detected_currencies.add("GWh")
                    found_energy.add("GWh")
                if "MWH" in words:
                    detected_currencies.add("MWh")
                    found_energy.add("MWh")
                if "KWH" in words:
                    detected_currencies.add("kWh")
                    found_energy.add("kWh")
                if "MW" in words:
                    detected_currencies.add("MW")
                    found_energy.add("MW")
                if "KW" in words:
                    detected_currencies.add("kW")
                    found_energy.add("kW")

                # Detección de porcentajes, tasas y ratios
                if "%" in vl or "porcentaj" in vl or "participaci" in vl or "proporcion" in vl:
                    found_percent = True
                if "veces" in vl or "ratio" in vl:
                    found_ratio = True
                if "tasa" in vl or "rendimiento" in vl or "tre(%)" in vl or "tea(%)" in vl:
                    found_tasa = True
                # Detección de índice como hecho secundario (en nv_cols)
                if "indice" in vl or "\u00edndice" in vl or "igae" in vl or "ipc" in vl:
                    if suggested_metric not in ["indice"]:
                        found_indice_secondary = True
                        match_ib = re.search(r'(\d{4}\s*=\s*100)', vl)
                        if match_ib:
                            detected_indice_unit = match_ib.group(1).replace(" ", "")
                # Detección de conteo en filas de nv_cols
                if col in nv_cols and any(tok in vl for tok in ["cantidad", "numero", "nro", "reclamo", "queja", "solicitud", "operacion", "transaccion", "personas", "casos", "cuentas"]):
                    found_count_in_rows = True

    # Estructurar hechos detectados (fact/metric dimensional)
    detected_facts = []

    # Hecho 1: Hecho base predominante
    detected_facts.append({
        "metrica": suggested_metric,
        "unidad": suggested_unit,
        "etiqueta": f"Base ({suggested_metric.capitalize()} / {suggested_unit})"
    })

    # Hechos adicionales detectados en filas
    if found_percent and suggested_metric != "porcentaje":
        detected_facts.append({
            "metrica": "porcentaje",
            "unidad": "%",
            "etiqueta": "Porcentaje / Participación (%)"
        })
        has_mixed_rows = True

    if found_ratio and suggested_metric != "ratio":
        detected_facts.append({
            "metrica": "ratio",
            "unidad": "veces",
            "etiqueta": "Ratio (veces)"
        })
        has_mixed_rows = True

    if found_tasa and suggested_metric != "tasa":
        detected_facts.append({
            "metrica": "tasa",
            "unidad": "%",
            "etiqueta": "Tasa (%)"
        })
        has_mixed_rows = True

    if found_indice_secondary and suggested_metric not in ["indice", "porcentaje"]:
        detected_facts.append({
            "metrica": "indice",
            "unidad": detected_indice_unit,
            "etiqueta": f"Índice ({detected_indice_unit})"
        })
        has_mixed_rows = True

    if len(detected_currencies) > 1:
        has_mixed_rows = True
        for curr in sorted(detected_currencies):
            if curr != suggested_unit:
                detected_facts.append({
                    "metrica": "moneda" if curr in ["BOB", "USD", "UFV"] else "tipo_cambio",
                    "unidad": curr,
                    "etiqueta": f"Moneda / Divisa ({curr})"
                })
    elif len(detected_currencies) == 1 and suggested_metric != "moneda":
        curr = list(detected_currencies)[0]
        detected_facts.append({
            "metrica": "moneda",
            "unidad": curr,
            "etiqueta": f"Moneda ({curr})"
        })
        has_mixed_rows = True

    if found_energy:
        for en in sorted(found_energy):
            if en != suggested_unit:
                m_type = "potencia" if en in ["MW", "GW", "kW"] else "energia"
                detected_facts.append({
                    "metrica": m_type,
                    "unidad": en,
                    "etiqueta": f"{m_type.capitalize()} ({en})"
                })
                has_mixed_rows = True

    has_multi_currency = len(detected_currencies) > 1 or len(commodity_price_units) > 1
    has_multiple_facts = len(detected_facts) > 1 or len(commodity_price_units) > 1
    if has_multiple_facts or len(commodity_price_units) > 1:
        has_mixed_rows = True

    return {
        "all_columns": cols_clean,
        "title_cols": title_cols,
        "nv_cols": nv_cols,
        "aux_cols": aux_cols,
        "suggested_metric": suggested_metric,
        "suggested_unit": suggested_unit,
        "suggested_factor": suggested_factor,
        "has_mixed_rows": has_mixed_rows,
        "has_multi_currency": has_multi_currency,
        "has_multiple_facts": has_multiple_facts,
        "detected_facts": detected_facts,
        "detected_currencies": sorted(list(detected_currencies)),
        "titles_text": combined_titles.strip(),
        "sample_df": df
    }


def generate_migration_sql(columns: List[str]) -> str:
    """Genera el DDL SQL de PostgreSQL cumpliendo con los estándares obligatorios de DATAX."""
    field_lines = ["  id UUID PRIMARY KEY DEFAULT gen_random_uuid()"]

    for col in columns:
        col_std = standardize_col_name(col)
        if col_std not in ["fecha", "valor", "file", "id"]:
            field_lines.append(f"  {col_std} text")

    field_lines.extend([
        "  fecha date",
        "  metrica character varying(255)",
        "  unidad_metrica character varying(255)",
        "  valor numeric",
        "  fecha_creacion date DEFAULT CURRENT_DATE",
        "  fecha_modificacion timestamp DEFAULT CURRENT_TIMESTAMP",
        "  observations text"
    ])

    cols_str = ",\n".join(field_lines)

    sql_template = (
        'CREATE TABLE IF NOT EXISTS "%s"."%s"\n'
        '(\n'
        + cols_str + '\n'
        ');\n\n'
        'CREATE OR REPLACE FUNCTION actualizar_fecha_modificacion()\n'
        'RETURNS TRIGGER AS $$\n'
        'BEGIN\n'
        '  NEW.fecha_modificacion = CURRENT_TIMESTAMP;\n'
        '  RETURN NEW;\n'
        'END;\n'
        '$$ LANGUAGE plpgsql;\n\n'
        'CREATE OR REPLACE TRIGGER trigger_actualizar_fecha_modificacion\n'
        'BEFORE UPDATE ON "%s"."%s"\n'
        'FOR EACH ROW\n'
        'EXECUTE FUNCTION actualizar_fecha_modificacion();\n'
    )
    return sql_template


def generate_migration_py(
    report_code: str,
    report_name: str,
    columns: List[str],
    metric: str,
    unit: str,
    factor: float,
    has_mixed_rows: bool = False,
    custom_metric_code: str = "",
    custom_unit_code: str = ""
) -> str:
    clean_cols = [standardize_col_name(c) for c in columns if c not in ["fecha", "valor", "file", "id"]]
    factor_num = int(factor) if factor == int(factor) else factor
    rep_title = report_name or "Estandarizacion y carga a PostgreSQL"

    # 1. Si el Agente Inteligente generó código de mapeo personalizado:
    if custom_metric_code.strip() and custom_unit_code.strip():
        def indent_code(code_str: str, spaces: int = 8) -> str:
            lines = code_str.strip().splitlines()
            return chr(10).join(" " * spaces + l for l in lines)

        indented_metric = indent_code(custom_metric_code)
        indented_unit = indent_code(custom_unit_code)

        return f'''"""Migration robot for report {report_code}: {rep_title}."""

import re
from typing import Tuple
import pandas as pd
from models.migration.Migration_Base import Migration_Base


class {report_code}(Migration_Base):
    """Migration robot for {report_code}."""

    def standard_report(self, dataframe: pd.DataFrame, conversion_factor: int) -> Tuple[dict, pd.DataFrame]:
        """
        Enrich dataframe with metric and metric unit metadata (Generado con Agente Inteligente DATAX).
        """
        dataframe.columns = [re.sub(r"[\\t\\xa0]+", "", str(c)).strip() for c in dataframe.columns]

        for col in dataframe.columns:
            if col not in ["valor", "fecha"]:
                dataframe[col] = dataframe[col].apply(
                    lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() not in ["none", "nan", ""] else None
                )

{indented_metric}

{indented_unit}

        idx_valor = dataframe.columns.get_loc("valor")
        dataframe.insert(idx_valor, column="metrica", value=dataframe.apply(get_metric, axis=1))
        dataframe.insert(idx_valor + 1, column="unidad_metrica", value=dataframe.apply(get_unit, axis=1))

        dataframe["valor"] = pd.to_numeric(
            dataframe["valor"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        )

        try:
            factor_val = float(conversion_factor) if conversion_factor is not None else {float(factor)}
        except (ValueError, TypeError):
            factor_val = {float(factor)}

        if factor_val <= 1.0 and {float(factor)} > 1.0:
            factor_val = {float(factor)}

        if factor_val > 1.0:
            mask_moneda = dataframe["metrica"] == "moneda"
            dataframe.loc[mask_moneda, "valor"] = dataframe.loc[mask_moneda, "valor"] * factor_val

        return ({{"conversion_factor": 1}}, dataframe)


Robot = {report_code}
'''

    # 2. Si tiene filas mixtas pero sin código del agente (plantilla estándar):
    elif has_mixed_rows:
        return f'''"""Migration robot for report {report_code}: {rep_title}."""

import re
from typing import Tuple
import pandas as pd
from models.migration.Migration_Base import Migration_Base


class {report_code}(Migration_Base):
    """Migration robot for {report_code}."""

    def standard_report(self, dataframe: pd.DataFrame, conversion_factor: int) -> Tuple[dict, pd.DataFrame]:
        """
        Enrich dataframe with metric and metric unit metadata.
        Mapeo dinamico de metricas y unidades (BOB, USD, UFV, tipos de cambio, ratios y porcentajes).
        """
        dataframe.columns = [re.sub(r"[\\t\\xa0]+", "", str(c)).strip() for c in dataframe.columns]

        for col in dataframe.columns:
            if col not in ["valor", "fecha"]:
                dataframe[col] = dataframe[col].apply(
                    lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() not in ["none", "nan", ""] else None
                )

        def get_metric(row) -> str:
            texts = [str(row.get(c, "")).upper() for c in reversed({clean_cols})]
            combined = " ".join(texts)
            if any(tok in combined for tok in ["%", "PORCENTAJ", "PARTICIPACI", "PROPORCION"]):
                return "porcentaje"
            if "VECES" in combined or "RATIO" in combined:
                return "ratio"
            if any(tok in combined for tok in ["INDICE", "ÍNDICE", "BASE 20", "BASE 19"]):
                return "indice"
            if any(tok in combined for tok in ["TASA", "RENDIMIENTO"]):
                return "tasa"
            if any(tok in combined for tok in ["TIPO DE CAMBIO", "COTIZACION", "COTIZACIÓN", "BS/USD", "BOB/USD", "BS/UFV", "BOB/UFV"]):
                return "tipo_cambio"
            if any(tok in combined for tok in ["GWH", "MWH", "KWH", "ENERGIA", "ENERGÍA"]):
                return "energia"
            if any(tok in combined for tok in ["POTENCIA", " MW", "(MW)", " GW", "(GW)", " KW", "(KW)"]):
                return "potencia"
            for t in texts:
                words = set(re.split(r"[\\s/()]+", t))
                if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in t or "DEL EXTERIOR" in t:
                    return "moneda"
                if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in t:
                    return "moneda"
                if "UFV" in words:
                    return "moneda"
            return "{metric}"

        def get_unit(row) -> str:
            texts = [str(row.get(c, "")).upper() for c in reversed({clean_cols})]
            combined = " ".join(texts)
            if any(tok in combined for tok in ["%", "PORCENTAJ", "PARTICIPACI", "PROPORCION"]):
                return "%"
            if "VECES" in combined or "RATIO" in combined:
                return "veces"
            match_base = re.search(r"(\\d{{4}}\\s*=\\s*100)", combined)
            if match_base:
                return match_base.group(1).replace(" ", "")
            for t in texts:
                words = set(re.split(r"[\\s/()]+", t))
                if "GWH" in words:
                    return "GWh"
                if "MWH" in words:
                    return "MWh"
                if "KWH" in words:
                    return "kWh"
                if "MW" in words:
                    return "MW"
                if "GW" in words:
                    return "GW"
                if "KW" in words:
                    return "kW"
            for t in texts:
                if any(tok in t for tok in ["BS/USD", "BOB/USD", "BS / USD", "BOB / USD"]) or ("TIPO DE CAMBIO" in t and any(tok in t for tok in ["USD", "DOLAR", "DÓLAR"])):
                    return "BOB/USD"
                if any(tok in t for tok in ["BS/UFV", "BOB/UFV", "BS / UFV", "BOB / UFV"]) or ("UFV" in t and "TIPO DE CAMBIO" in t) or ("BS/UFV" in t):
                    return "BOB/UFV"
            for t in texts:
                words = set(re.split(r"[\\s/()]+", t))
                if "UFV" in words:
                    return "UFV"
                if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in t or "DEL EXTERIOR" in t:
                    return "USD"
                if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in t:
                    return "BOB"
            return "{unit}"

        idx_valor = dataframe.columns.get_loc("valor")
        dataframe.insert(idx_valor, column="metrica", value=dataframe.apply(get_metric, axis=1))
        dataframe.insert(idx_valor + 1, column="unidad_metrica", value=dataframe.apply(get_unit, axis=1))

        dataframe["valor"] = pd.to_numeric(
            dataframe["valor"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        )

        try:
            factor_val = float(conversion_factor) if conversion_factor is not None else {float(factor)}
        except (ValueError, TypeError):
            factor_val = {float(factor)}

        if factor_val <= 1.0 and {float(factor)} > 1.0:
            factor_val = {float(factor)}

        if factor_val > 1.0:
            mask_moneda = dataframe["metrica"] == "moneda"
            dataframe.loc[mask_moneda, "valor"] = dataframe.loc[mask_moneda, "valor"] * factor_val

        return ({{"conversion_factor": 1}}, dataframe)


Robot = {report_code}
'''

    # 3. Reporte homogéneo (métrica y unidad fija):
    else:
        return f'''"""Migration robot for report {report_code}: {rep_title}."""

import re
from typing import Tuple
import pandas as pd
from models.migration.Migration_Base import Migration_Base


class {report_code}(Migration_Base):
    """Migration robot for {report_code}."""

    def standard_report(self, dataframe: pd.DataFrame, conversion_factor: int) -> Tuple[dict, pd.DataFrame]:
        """
        Enrich dataframe with clean columns and metric metadata.
        - metrica: '{metric}'
        - unidad_metrica: '{unit}'
        - conversion_factor: {factor_num}
        """
        dataframe.columns = [re.sub(r"[\\t\\xa0]+", "", str(c)).strip() for c in dataframe.columns]

        for col in dataframe.columns:
            if col not in ["valor", "fecha"]:
                dataframe[col] = dataframe[col].apply(
                    lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() not in ["none", "nan", ""] else None
                )

        idx_valor = dataframe.columns.get_loc("valor")
        dataframe.insert(idx_valor, column="metrica", value="{metric}")
        dataframe.insert(idx_valor + 1, column="unidad_metrica", value="{unit}")

        dataframe["valor"] = pd.to_numeric(
            dataframe["valor"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce"
        )

        try:
            factor_val = int(conversion_factor) if conversion_factor is not None else {factor_num}
        except (ValueError, TypeError):
            factor_val = {factor_num}

        if factor_val <= 1 and {factor_num} > 1:
            factor_val = {factor_num}

        if factor_val > 1 and "{metric}" == "moneda":
            dataframe["valor"] = dataframe["valor"] * factor_val

        return ({{"conversion_factor": factor_val}}, dataframe)


Robot = {report_code}
'''


def save_migration_files(
    repo_path: str,
    parent_code: str,
    report_code: str,
    sql_content: str,
    py_content: str
) -> Tuple[str, str]:
    """Guarda los dos archivos obligatorios en models/migration/M_.../"""
    mig_dir = os.path.join(repo_path, "models", "migration", parent_code)
    os.makedirs(mig_dir, exist_ok=True)

    sql_path = os.path.join(mig_dir, f"{report_code}.sql")
    py_path = os.path.join(mig_dir, f"{report_code}.py")

    with open(sql_path, "w", encoding="utf-8") as f:
        f.write(sql_content)

    with open(py_path, "w", encoding="utf-8") as f:
        f.write(py_content)

    return sql_path, py_path


def get_latest_conversion_for_report(report_code: str, engine) -> Optional[Dict]:
    """Obtiene la última conversión registrada para este reporte en platform_db con su archivo SQLite."""
    query = text("""
        SELECT c.id_conversion, c.conversion_path, c.converted_to, c.conversion_date, c.id_download
        FROM conversion c
        JOIN report r ON c.id_report = r.id_report
        WHERE r.code = :code AND c.conversion_path IS NOT NULL
        ORDER BY c.converted_to DESC, c.id_conversion DESC
        LIMIT 1;
    """)
    try:
        with engine.connect() as conn:
            row = conn.execute(query, {"code": report_code}).fetchone()
            if not row:
                return None

            conv_path = str(row[1] or "")
            unix_path = conv_path.replace("\\", "/")
            if unix_path.startswith("//10.0.0.16/data_process/"):
                unix_path = unix_path.replace("//10.0.0.16/data_process/", "/mnt/datos1/data_process/")
            elif unix_path.startswith("/10.0.0.16/data_process/"):
                unix_path = unix_path.replace("/10.0.0.16/data_process/", "/mnt/datos1/data_process/")
            elif unix_path.startswith("//10.0.0.12/data_process/"):
                unix_path = unix_path.replace("//10.0.0.12/data_process/", "/media/datax/Local_Disk_B/data_process/")

            return {
                "id_conversion": int(row[0]),
                "conversion_path_raw": conv_path,
                "conversion_path": unix_path,
                "converted_to": str(row[2]) if row[2] else "-",
                "conversion_date": str(row[3]) if row[3] else "-",
                "id_download": row[4]
            }
    except Exception as exc:
        print(f"Error al consultar latest conversion: {exc}")
        return None

