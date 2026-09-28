"""Lógica de generación y preparación de robots y DAGs de migración (PostgreSQL / Airflow V2)."""

import os
import re
import sqlite3
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text


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
    """Inspecciona la tabla SQLite para obtener columnas, muestras y sugerir métricas y unidades."""
    with sqlite3.connect(sqlite_path) as conn:
        cursor = conn.cursor()
        if not table_name:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN ('columns_to_review', 'sqlite_sequence');")
            tables = [r[0] for r in cursor.fetchall()]
            table_name = tables[0] if tables else ""
        cursor.execute(f'PRAGMA table_info("{table_name}");')
        pragma_cols = [row[1] for row in cursor.fetchall()]
        df = pd.read_sql_query(f'SELECT * FROM "{table_name}" LIMIT 100;', conn)

    cols_clean = [re.sub(r'[\t\xa0]+', '', str(c)).strip() for c in pragma_cols if str(c).strip() != 'file']

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

    # Detección inicial de factor sugerido
    suggested_factor = 1.0
    if "millones" in combined_titles_lower:
        suggested_factor = 1000000.0
    elif "miles" in combined_titles_lower:
        suggested_factor = 1000.0

    # Detección de métrica y unidad sugerida
    suggested_metric = "moneda"
    suggested_unit = "BOB"
    if "tasa" in combined_titles_lower or "tasas" in combined_titles_lower:
        suggested_metric = "tasa"
        suggested_unit = "%"
        suggested_factor = 1.0
    elif "porcentaje" in combined_titles_lower or "%" in combined_titles_lower:
        suggested_metric = "porcentaje"
        suggested_unit = "%"
        suggested_factor = 1.0
    elif "indice" in combined_titles_lower or "índice" in combined_titles_lower:
        suggested_metric = "indice"
        match_base = re.search(r"(\d{4}\s*=\s*100)", combined_titles)
        suggested_unit = match_base.group(1).replace(" ", "") if match_base else "puntos"
        suggested_factor = 1.0
    elif "toneladas" in combined_titles_lower or "tonelada" in combined_titles_lower or "tm" in combined_titles_lower:
        suggested_metric = "volumen"
        suggested_unit = "Tn"
        suggested_factor = 1.0
    elif "tasa" in combined_titles_lower:
        suggested_metric = "tasa"
        suggested_unit = "%"
        suggested_factor = 1.0
    elif "mwh" in combined_titles_lower:
        suggested_metric = "energia"
        suggested_unit = "MWh"

    has_mixed_rows = False
    for col in nv_cols:
        if col in df.columns:
            str_vals = df[col].dropna().astype(str).str.lower().tolist()
            if any("%" in v or "participaci" in v or "veces" in v or "ratio" in v for v in str_vals):
                has_mixed_rows = True
                break

    return {
        "all_columns": cols_clean,
        "title_cols": title_cols,
        "nv_cols": nv_cols,
        "aux_cols": aux_cols,
        "suggested_metric": suggested_metric,
        "suggested_unit": suggested_unit,
        "suggested_factor": suggested_factor,
        "has_mixed_rows": has_mixed_rows,
        "titles_text": combined_titles.strip(),
        "sample_df": df.head(10)
    }


def generate_migration_sql(columns: List[str]) -> str:
    """Genera el DDL SQL de PostgreSQL cumpliendo con los estándares obligatorios de DATAX."""
    field_lines = ["  id UUID PRIMARY KEY DEFAULT gen_random_uuid()"]

    for col in columns:
        if col not in ["fecha", "valor"]:
            field_lines.append(f"  {col} text")

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
    """Genera el código Python del robot de migración heredando de Migration_Base."""
    clean_cols = [c for c in columns if c not in ["fecha", "valor"]]
    factor_num = int(factor) if factor == int(factor) else factor

    if has_mixed_rows:
        return (
            f'"""Migration robot for report {report_code}: {report_name or "Estandarización y carga a PostgreSQL"}."""\n\n'
            'import re\n'
            'from typing import Tuple\n'
            'import pandas as pd\n'
            'from models.migration.Migration_Base import Migration_Base\n\n\n'
            f'class {report_code}(Migration_Base):\n'
            f'    """Migration robot for {report_code}."""\n\n'
            '    def standard_report(self, dataframe: pd.DataFrame, conversion_factor: int) -> Tuple[dict, pd.DataFrame]:\n'
            '        """\n'
            '        Enrich dataframe with metric and metric unit metadata.\n'
            '        Manejo híbrido:\n'
            '        - Filas de porcentaje/participación: metrica = \'porcentaje\', unidad_metrica = \'%\'\n'
            '        - Filas de ratio/veces: metrica = \'ratio\', unidad_metrica = \'veces\'\n'
            f'        - Filas monetarias: metrica = \'{metric}\', unidad_metrica = \'{unit}\' (escalado selectivo)\n'
            '        """\n'
            '        dataframe.columns = [re.sub(r"[\\t\\xa0]+", "", str(c)).strip() for c in dataframe.columns]\n\n'
            '        for col in dataframe.columns:\n'
            '            if col not in ["valor", "fecha"]:\n'
            '                dataframe[col] = dataframe[col].apply(\n'
            '                    lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() not in ["none", "nan", ""] else None\n'
            '                )\n\n'
            '        def get_metric(row) -> str:\n'
            f'            vals = " ".join([str(row.get(c, "")).lower() for c in {clean_cols}])\n'
            '            if "%" in vals or "participaci" in vals:\n'
            '                return "porcentaje"\n'
            '            if "veces" in vals or "ratio" in vals:\n'
            '                return "ratio"\n'
            f'            return "{metric}"\n\n'
            '        def get_unit(row) -> str:\n'
            f'            vals = " ".join([str(row.get(c, "")).lower() for c in {clean_cols}])\n'
            '            if "%" in vals or "participaci" in vals:\n'
            '                return "%"\n'
            '            if "veces" in vals or "ratio" in vals:\n'
            '                return "veces"\n'
            f'            return "{unit}"\n\n'
            '        idx_valor = dataframe.columns.get_loc("valor")\n'
            '        dataframe.insert(idx_valor, column="metrica", value=dataframe.apply(get_metric, axis=1))\n'
            '        dataframe.insert(idx_valor + 1, column="unidad_metrica", value=dataframe.apply(get_unit, axis=1))\n\n'
            '        dataframe["valor"] = pd.to_numeric(dataframe["valor"], errors="coerce")\n\n'
            '        try:\n'
            f'            factor_val = float(conversion_factor) if conversion_factor is not None else {float(factor)}\n'
            '        except (ValueError, TypeError):\n'
            f'            factor_val = {float(factor)}\n\n'
            f'        if factor_val <= 1.0 and {float(factor)} > 1.0:\n'
            f'            factor_val = {float(factor)}\n\n'
            f'        if factor_val > 1.0:\n'
            f'            mask_moneda = dataframe["metrica"] == "{metric}"\n'
            '            dataframe.loc[mask_moneda, "valor"] = dataframe.loc[mask_moneda, "valor"] * factor_val\n\n'
            '        return ({"conversion_factor": 1}, dataframe)\n\n\n'
            f'Robot = {report_code}\n'
        )
    else:
        return (
            f'"""Migration robot for report {report_code}: {report_name or "Estandarización y carga a PostgreSQL"}."""\n\n'
            'import re\n'
            'from typing import Tuple\n'
            'import pandas as pd\n'
            'from models.migration.Migration_Base import Migration_Base\n\n\n'
            f'class {report_code}(Migration_Base):\n'
            f'    """Migration robot for {report_code}."""\n\n'
            '    def standard_report(self, dataframe: pd.DataFrame, conversion_factor: int) -> Tuple[dict, pd.DataFrame]:\n'
            '        """\n'
            '        Enrich dataframe with clean columns and metric metadata.\n'
            f'        - metrica: \'{metric}\'\n'
            f'        - unidad_metrica: \'{unit}\'\n'
            f'        - conversion_factor: {factor_num}\n'
            '        """\n'
            '        dataframe.columns = [re.sub(r"[\\t\\xa0]+", "", str(c)).strip() for c in dataframe.columns]\n\n'
            '        for col in dataframe.columns:\n'
            '            if col not in ["valor", "fecha"]:\n'
            '                dataframe[col] = dataframe[col].apply(\n'
            '                    lambda x: str(x).strip() if pd.notna(x) and str(x).strip().lower() not in ["none", "nan", ""] else None\n'
            '                )\n\n'
            '        idx_valor = dataframe.columns.get_loc("valor")\n'
            f'        dataframe.insert(idx_valor, column="metrica", value="{metric}")\n'
            f'        dataframe.insert(idx_valor + 1, column="unidad_metrica", value="{unit}")\n\n'
            '        try:\n'
            f'            factor_val = int(conversion_factor) if conversion_factor is not None else {factor_num}\n'
            '        except (ValueError, TypeError):\n'
            f'            factor_val = {factor_num}\n\n'
            f'        if factor_val <= 1 and {factor_num} > 1:\n'
            f'            factor_val = {factor_num}\n\n'
            '        return ({"conversion_factor": factor_val}, dataframe)\n\n\n'
            f'Robot = {report_code}\n'
        )


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
