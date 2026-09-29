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


def inspect_sqlite_structure(sqlite_path: str, table_name: str = "") -> Dict:
    """Inspecciona la tabla SQLite para obtener columnas, muestras y sugerir metricas y unidades."""
    with sqlite3.connect(sqlite_path) as conn:
        cursor = conn.cursor()
        if not table_name:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('columns_to_review', 'sqlite_sequence');")
            tables = [r[0] for r in cursor.fetchall()]
            table_name = tables[0] if tables else ""
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        pragma_cols = [row[1] for row in cursor.fetchall()]
        df = pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT 200;', conn)

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
    full_header_text = (combined_titles_lower + " " + nv1_sample).strip()

    # Deteccion de factor sugerido
    suggested_factor = 1.0
    if "millones" in full_header_text:
        suggested_factor = 1000000.0
    elif "miles" in full_header_text:
        suggested_factor = 1000.0

    # Deteccion de moneda base y tipos de cambio
    has_usd_kw = any(k in full_header_text for k in ["dolares", "dólares", "usd", "$us", "moneda extranjera", "del exterior"])
    has_bob_kw = any(k in full_header_text for k in ["bolivianos", "bob", "moneda nacional", " bs", "bs."])

    suggested_metric = "moneda"
    suggested_unit = "USD" if (has_usd_kw and not has_bob_kw) else "BOB"

    if "tipo de cambio" in full_header_text or "cotizacion" in full_header_text or "cotización" in full_header_text:
        suggested_metric = "tipo_cambio"
        suggested_factor = 1.0
        if "ufv" in full_header_text:
            suggested_unit = "BOB/UFV"
        else:
            suggested_unit = "BOB/USD"
    elif "tasa" in full_header_text or "tasas" in full_header_text:
        suggested_metric = "tasa"
        suggested_unit = "%"
        suggested_factor = 1.0
    elif "porcentaje" in full_header_text or "%" in full_header_text:
        suggested_metric = "porcentaje"
        suggested_unit = "%"
        suggested_factor = 1.0
    elif "indice" in full_header_text or "índice" in full_header_text:
        suggested_metric = "indice"
        match_base = re.search(r"(\d{4}\s*=\s*100)", full_header_text)
        suggested_unit = match_base.group(1).replace(" ", "") if match_base else "puntos"
        suggested_factor = 1.0
    elif "toneladas" in full_header_text or "tonelada" in full_header_text or "tm" in full_header_text:
        suggested_metric = "volumen"
        suggested_unit = "Tn"
        suggested_factor = 1.0
    elif "mwh" in full_header_text:
        suggested_metric = "energia"
        suggested_unit = "MWh"

    # Deteccion de monedas multiples y filas hibridas
    detected_currencies = set()
    has_mixed_rows = False

    for col in nv_cols:
        if col in df.columns:
            str_vals = df[col].dropna().astype(str).tolist()
            for v in str_vals:
                vu = v.upper()
                words = set(re.split(r'[\s/()]+', vu))
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

                vl = v.lower()
                if "%" in vl or "participaci" in vl or "veces" in vl or "ratio" in vl:
                    has_mixed_rows = True

    has_multi_currency = len(detected_currencies) > 1
    if has_multi_currency:
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
        "detected_currencies": sorted(list(detected_currencies)),
        "titles_text": combined_titles.strip(),
        "sample_df": df.head(10)
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
    has_mixed_rows: bool = False
) -> str:
    clean_cols = [c for c in columns if c not in ["fecha", "valor"]]
    factor_num = int(factor) if factor == int(factor) else factor
    rep_title = report_name or "Estandarizacion y carga a PostgreSQL"

    if has_mixed_rows:
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
            if "%" in combined or "PARTICIPACI" in combined:
                return "porcentaje"
            if "VECES" in combined or "RATIO" in combined:
                return "ratio"
            if any(tok in combined for tok in ["INDICE", "ÍNDICE", "BASE 20", "BASE 19"]):
                return "indice"
            if any(tok in combined for tok in ["TASA", "RENDIMIENTO"]):
                return "tasa"
            if any(tok in combined for tok in ["TIPO DE CAMBIO", "COTIZACION", "COTIZACIÓN", "BS/USD", "BOB/USD", "BS/UFV", "BOB/UFV"]):
                return "tipo_cambio"
            return "{metric}"

        def get_unit(row) -> str:
            texts = [str(row.get(c, "")).upper() for c in reversed({clean_cols})]
            combined = " ".join(texts)
            if "%" in combined or "PARTICIPACI" in combined:
                return "%"
            if "VECES" in combined or "RATIO" in combined:
                return "veces"
            match_base = re.search(r"(\\d{{4}}\\s*=\\s*100)", combined)
            if match_base:
                return match_base.group(1).replace(" ", "")
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

        dataframe["valor"] = pd.to_numeric(dataframe["valor"], errors="coerce")

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

        try:
            factor_val = int(conversion_factor) if conversion_factor is not None else {factor_num}
        except (ValueError, TypeError):
            factor_val = {factor_num}

        if factor_val <= 1 and {factor_num} > 1:
            factor_val = {factor_num}

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
