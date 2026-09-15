"""Lógica de migración para robots de conversión (C_BO_XXXX -> D_BO_XXXX_YY)."""

import os
import re
import sys
import shutil
import sqlite3
import subprocess
import importlib.util
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import create_engine


def scan_old_conversion_families(old_repo_path: str) -> List[Dict]:
    """Escanea las carpetas de conversión disponibles en el repositorio antiguo."""
    conv_dir = os.path.join(old_repo_path, "models", "conversion")
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
        sub_reports = []
        samples = []
        sqlites = []

        for f in os.listdir(item_path):
            fpath = os.path.join(item_path, f)
            if not os.path.isfile(fpath):
                continue
            lower = f.lower()
            if lower.endswith(".py") and not lower.startswith("__"):
                rep_match = re.search(r"(D_[A-Z]{2}_\d{9}_\d{2})", f)
                rep_code = rep_match.group(1) if rep_match else os.path.splitext(f)[0]
                sub_reports.append({"code": rep_code, "file": fpath})
            elif lower.endswith((".pdf", ".xlsx", ".xls", ".csv")):
                samples.append(fpath)
            elif lower.endswith(".sqlite"):
                sqlites.append(fpath)

        families.append({
            "parent_code": parent_code,
            "folder": item_path,
            "sub_reports": sub_reports,
            "samples": samples,
            "sqlites": sqlites
        })

    return families


def get_conversion_db_info(report_code: str, engine) -> Optional[Dict]:
    """Obtiene metadatos del reporte desde la tabla report de platform_db."""
    query = f"""
        SELECT id_report, code, name, page_number, decimal_separator, 
               key_words, path, storage_table, replacement_table,
               converted_report_path, is_active
        FROM report 
        WHERE code = '{report_code}';
    """
    try:
        df = pd.read_sql_query(query, con=engine)
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception as exc:
        return {"error": str(exc)}


def refactor_conversion_code(raw_code: str, report_code: str) -> str:
    """Aplica las reglas de estandarización V2 del Paso 4 de 'Creacion DAG Covnersion.md'."""
    code_content = raw_code

    # 1. Eliminar sys.path.append viejos o rutas relativas
    code_content = re.sub(r"sys\.path\.append\([^)]*\)\s*", "", code_content)

    # 2. Corregir imports de herramientas hacia los paths oficiales de la Plataforma V2
    code_content = re.sub(r"\bfrom\s+(?:models\.)?(?:conversion\.)?tools\.conversion_tools\b", "from models.conversion.tools.conversion_tools", code_content)
    code_content = re.sub(r"\bfrom\s+conversion_tools\b", "from models.conversion.tools.conversion_tools", code_content)
    code_content = re.sub(r"\bimport\s+conversion_tools\b", "import models.conversion.tools.conversion_tools as conversion_tools", code_content)

    code_content = re.sub(r"\bfrom\s+(?:models\.)?(?:download\.)?tools\.download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bfrom\s+download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bimport\s+download_tools\b", "import models.download.tools.download_tools as download_tools", code_content)

    # 3. Asegurar import requerido de Conversion_Base
    if "from models.conversion.Conversion_Base import Conversion_Base" not in code_content:
        code_content = "from models.conversion.Conversion_Base import Conversion_Base\n" + code_content

    # 4. Renombrar clase principal a <REPORT_CODE>(Conversion_Base)
    # Soporta class Robot:, class Robot():, class Robot(Conversion_Base):, class Executor_...:, etc.
    class_pattern = r"class\s+([A-Za-z0-9_]+)(?:\s*\([^)]*\))?\s*:"
    matches = list(re.finditer(class_pattern, code_content))
    for m in matches:
        cls_name = m.group(1)
        if cls_name != report_code:
            full_match = m.group(0)
            code_content = code_content.replace(full_match, f"class {report_code}(Conversion_Base):", 1)
            break

    # 5. Asegurar traceback.print_exc() en bloques except si falta
    lines = code_content.splitlines()
    new_lines = []
    for i, line in enumerate(lines):
        new_lines.append(line)
        if re.search(r"^\s*except(\s+.*)?:", line):
            next_block = "\n".join(lines[i + 1 : i + 4])
            if "print_exc" not in next_block:
                indent = re.match(r"^(\s*)", line).group(1) + "    "
                new_lines.append(f"{indent}import traceback; traceback.print_exc()")
    code_content = "\n".join(new_lines)

    # 6. Agregar alias al pie de compatibilidad
    alias_footer = f"\n\nExecutor_{report_code} = {report_code}\nRobot = {report_code}\n"
    if f"Executor_{report_code} = {report_code}" not in code_content:
        code_content += alias_footer

    return code_content


def detect_available_samples(parent_code: str, old_repo_path: str, new_repo_path: str) -> List[str]:
    """Detecta archivos de muestra (.pdf, .xlsx, .xls, .csv) en origen y destino."""
    samples = []
    seen = set()

    # Buscar en carpeta destino (V2)
    dest_dir = os.path.join(new_repo_path, "models", "conversion", parent_code)
    if os.path.isdir(dest_dir):
        for f in os.listdir(dest_dir):
            if f.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")):
                p = os.path.join(dest_dir, f)
                samples.append(p)
                seen.add(f.lower())

    # Buscar en carpeta origen (V1)
    for folder_candidate in [parent_code, parent_code.replace("C_", "D_")]:
        src_dir = os.path.join(old_repo_path, "models", "conversion", folder_candidate)
        if os.path.isdir(src_dir):
            for f in os.listdir(src_dir):
                if f.lower().endswith((".pdf", ".xlsx", ".xls", ".csv")) and f.lower() not in seen:
                    p = os.path.join(src_dir, f)
                    samples.append(p)
                    seen.add(f.lower())

    return samples


def save_uploaded_sample_file(new_repo_path: str, parent_code: str, uploaded_file) -> str:
    """Guarda un archivo de muestra subido por el usuario en la carpeta del modelo."""
    dest_dir = os.path.join(new_repo_path, "models", "conversion", parent_code)
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, uploaded_file.name)
    with open(dest_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    return dest_path


def run_conversion_step_test(
    report_code: str,
    sample_file_path: str,
    new_repo_path: str,
    skip_text_match: bool = False
) -> Dict:
    """Ejecuta el test unitario controlando SKIP_TEXT_MATCH."""
    test_path = os.path.join(new_repo_path, "models", "conversion", "tests", "test_conversion.py")
    if not os.path.isfile(test_path):
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Archivo de test no encontrado: {test_path}",
            "sqlite_created": False
        }

    env = os.environ.copy()
    env["REPORT_CODE"] = report_code
    env["FILE_PATH"] = sample_file_path
    env["SKIP_TEXT_MATCH"] = "1" if skip_text_match else "0"

    cmd = [sys.executable, "-m", "unittest", test_path]
    res = subprocess.run(cmd, cwd=new_repo_path, env=env, capture_output=True, text=True)

    parent_code = '_'.join(report_code.split('_')[:-1]).replace('D_', 'C_')
    sqlite_path = os.path.join(new_repo_path, "models", "conversion", parent_code, f"{report_code}.sqlite")
    sqlite_exists = os.path.isfile(sqlite_path)

    return {
        "success": res.returncode == 0,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "sqlite_created": sqlite_exists,
        "sqlite_path": sqlite_path if sqlite_exists else None
    }


def get_sqlite_data(
    new_repo_path: str,
    parent_code: str,
    report_code: str,
    limit: int = 100
) -> Tuple[Optional[pd.DataFrame], Optional[str], Optional[str]]:
    """Lee la tabla de datos extraídos en SQLite."""
    sqlite_path = os.path.join(new_repo_path, "models", "conversion", parent_code, f"{report_code}.sqlite")
    if not os.path.isfile(sqlite_path):
        return None, None, f"No se encontró el archivo SQLite en: {sqlite_path}"

    try:
        conn = sqlite3.connect(sqlite_path)
        # Verificar que la tabla existe
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cur.fetchall()]
        if report_code not in tables:
            conn.close()
            return None, sqlite_path, f"La tabla '{report_code}' no existe en el SQLite. Tablas encontradas: {tables}"

        query = f"SELECT * FROM [{report_code}] LIMIT {limit};"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df, sqlite_path, None
    except Exception as exc:
        return None, sqlite_path, str(exc)


def get_replacement_table_data(
    report_code: str,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax",
    limit: int = 100
) -> Tuple[Optional[pd.DataFrame], str, Optional[str]]:
    """Consulta la tabla de reemplazos en DATA_DB_BO_AUX."""
    # 1. Obtener replacement_table desde platform_db
    try:
        platform_engine = create_engine(f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/platform_db", connect_args={"connect_timeout": 5})
        rep_df = pd.read_sql_query(f"SELECT replacement_table FROM report WHERE code = '{report_code}';", con=platform_engine)
        if rep_df.empty or not rep_df.iloc[0]["replacement_table"]:
            return None, "", f"No hay 'replacement_table' configurada para {report_code} en platform_db."

        repl_str = rep_df.iloc[0]["replacement_table"]
        schema, table = repl_str.split(";")
    except Exception as exc:
        return None, "", f"Error consultando platform_db: {exc}"

    # 2. Conectar a DATA_DB_<country>_AUX
    country_code = report_code.split("_")[1] if len(report_code.split("_")) > 1 else "BO"
    aux_db_name = f"DATA_DB_{country_code}_AUX"
    try:
        aux_engine = create_engine(f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{aux_db_name}", connect_args={"connect_timeout": 5})
        query = f'SELECT * FROM "{schema}"."{table}" LIMIT {limit};'
        df = pd.read_sql_query(query, con=aux_engine)
        return df, f"{schema}.{table}", None
    except Exception as exc:
        return None, f"{schema}.{table}", str(exc)


def setup_columns_to_review(sqlite_path: str, report_code: str) -> Tuple[bool, List[str], List[str], Optional[str]]:
    """Configura la tabla columns_to_review en el SQLite según Paso 8."""
    if not os.path.isfile(sqlite_path):
        return False, [], [], f"Archivo SQLite no encontrado: {sqlite_path}"
    try:
        conn = sqlite3.connect(sqlite_path)
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info([{report_code}]);")
        cols_info = cur.fetchall()
        if not cols_info:
            conn.close()
            return False, [], [], f"No se pudo leer la estructura de la tabla '{report_code}'"

        all_cols = [c[1] for c in cols_info]
        review_cols = []
        for col in all_cols:
            c_low = col.strip().lower()
            if c_low in ("valor", "file") or c_low.startswith(("titulo", "id_")):
                continue
            review_cols.append(col)

        cur.execute("DROP TABLE IF EXISTS columns_to_review;")
        cur.execute("CREATE TABLE columns_to_review (column TEXT);")
        cur.executemany("INSERT INTO columns_to_review (column) VALUES (?);", [(c,) for c in review_cols])
        conn.commit()

        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [t[0] for t in cur.fetchall()]
        conn.close()
        return True, review_cols, tables, None
    except Exception as exc:
        return False, [], [], str(exc)


def apply_conversion_migration(
    parent_code: str,
    family_data: Dict,
    new_repo_path: str,
    skip_test: bool = False,
    skip_dag: bool = True
) -> Dict:
    """Aplica la migración completa de la familia de conversión."""
    logs = []
    success = True

    try:
        dest_dir = os.path.join(new_repo_path, "models", "conversion", parent_code)
        os.makedirs(dest_dir, exist_ok=True)

        # Copiar muestras
        sample_file_path = None
        for s in family_data.get("samples", []):
            dest_s = os.path.join(dest_dir, os.path.basename(s))
            shutil.copyfile(s, dest_s)
            if not sample_file_path:
                sample_file_path = dest_s

        # Copiar sqlites
        for sq in family_data.get("sqlites", []):
            dest_sq = os.path.join(dest_dir, os.path.basename(sq))
            shutil.copyfile(sq, dest_sq)

        # Refactorizar scripts
        for rep in family_data.get("sub_reports", []):
            rep_code = rep["code"]
            with open(rep["file"], "r", encoding="utf-8", errors="ignore") as f:
                raw_c = f.read()
            refactored = refactor_conversion_code(raw_c, rep_code)
            dest_f = os.path.join(dest_dir, f"{rep_code}.py")
            with open(dest_f, "w", encoding="utf-8") as f:
                f.write(refactored)
            logs.append(f"✅ Robot refactorizado y guardado: {dest_f}")

            # Test si hay muestra
            if not skip_test and sample_file_path:
                test_res = run_conversion_step_test(rep_code, sample_file_path, new_repo_path, skip_text_match=False)
                if test_res["success"]:
                    logs.append(f"✅ Test unitario superado para {rep_code}")
                    sq_path = os.path.join(dest_dir, f"{rep_code}.sqlite")
                    if os.path.isfile(sq_path):
                        ok_cr, cols_cr, _, _ = setup_columns_to_review(sq_path, rep_code)
                        if ok_cr:
                            logs.append(f"✅ columns_to_review configurado: {cols_cr}")
                else:
                    logs.append(f"❌ Falló test unitario para {rep_code}")
                    success = False

        return {"success": success, "logs": logs}
    except Exception as exc:
        return {"success": False, "logs": [f"Error general: {exc}"]}
