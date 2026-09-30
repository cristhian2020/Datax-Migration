"""Lógica de migración para robots de conversión (C_BO_XXXX -> D_BO_XXXX_YY)."""

import os
import re
import sys
import shutil
import sqlite3
import subprocess
import importlib.util
import unicodedata
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import create_engine, text


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

    # 3. Limpiar cualquier import previo o try/except obsoleto de Conversion_Base
    # a) Eliminar bloques try/except obsoletos de la vieja fábrica
    code_content = re.sub(
        r"try:\s*\n\s*from\s+models\.conversion(?:\.Conversion_Base)?\s+import\s+Conversion_Base\s*\nexcept[^\n]*:.*?(?=\n\S|\Z)",
        "",
        code_content,
        flags=re.DOTALL
    )
    # b) Eliminar imports sueltos previos (incluyendo el erróneo 'from models.conversion import Conversion_Base')
    code_content = re.sub(
        r"^[ \t]*from\s+models\.conversion(?:\.Conversion_Base)?\s+import\s+Conversion_Base[^\n]*\n?",
        "",
        code_content,
        flags=re.MULTILINE
    )
    # c) Asegurar un único import oficial y limpio al inicio del archivo
    code_content = "from models.conversion.Conversion_Base import Conversion_Base\n" + code_content.lstrip()

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


def normalize_srch_value(val: str) -> str:
    """Normaliza un texto para búsqueda en srch_value (sin tildes, caracteres combinados ni mayúsculas)."""
    if not val:
        return ""
    nfkd = unicodedata.normalize("NFKD", str(val))
    val_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return re.sub(r"\s+", " ", val_clean).strip().lower()


def get_replacement_table_target(
    report_code: str,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax"
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Obtiene schema, table y nombre de la base de datos auxiliar desde platform_db."""
    try:
        platform_engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/platform_db",
            connect_args={"connect_timeout": 5}
        )
        rep_df = pd.read_sql_query(
            f"SELECT replacement_table FROM report WHERE code = '{report_code}';",
            con=platform_engine
        )
        if rep_df.empty or not rep_df.iloc[0]["replacement_table"]:
            return None, None, None, f"No hay 'replacement_table' configurada para {report_code} en platform_db."

        repl_str = str(rep_df.iloc[0]["replacement_table"]).strip()
        if ";" in repl_str:
            schema, table = repl_str.split(";", 1)
        elif "." in repl_str:
            schema, table = repl_str.split(".", 1)
        else:
            return None, None, None, f"Formato inválido en replacement_table: '{repl_str}' (se esperaba 'schema;table')"

        country_code = report_code.split("_")[1] if len(report_code.split("_")) > 1 else "BO"
        aux_db_name = f"DATA_DB_{country_code}_AUX"
        return schema.strip(), table.strip(), aux_db_name, None
    except Exception as exc:
        return None, None, None, f"Error consultando platform_db: {exc}"


def get_replacement_table_data(
    report_code: str,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax",
    limit: Optional[int] = 500
) -> Tuple[Optional[pd.DataFrame], str, Optional[str]]:
    """Consulta la tabla de reemplazos en DATA_DB_<country>_AUX ordenada de forma determinista."""
    schema, table, aux_db_name, err = get_replacement_table_target(report_code, db_host, db_port, db_user, db_pass)
    if err or not schema or not table:
        return None, "", err or "No se pudo determinar la tabla de reemplazos."

    tbl_full = f"{schema}.{table}"
    try:
        aux_engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{aux_db_name}",
            connect_args={"connect_timeout": 5}
        )
        limit_clause = f" LIMIT {int(limit)}" if limit else ""
        try:
            query = f'SELECT * FROM "{schema}"."{table}" ORDER BY id ASC{limit_clause};'
            df = pd.read_sql_query(query, con=aux_engine)
        except Exception:
            query = f'SELECT * FROM "{schema}"."{table}"{limit_clause};'
            df = pd.read_sql_query(query, con=aux_engine)

        return df, tbl_full, None
    except Exception as exc:
        return None, tbl_full, str(exc)


def save_replacement_table_changes(
    report_code: str,
    original_df: pd.DataFrame,
    edited_df: pd.DataFrame,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax",
    allow_delete: bool = True
) -> Dict:
    """Compara original_df y edited_df y sincroniza atómicamente los cambios (UPDATE, INSERT, DELETE) en la base de datos auxiliar."""
    schema, table, aux_db_name, err = get_replacement_table_target(report_code, db_host, db_port, db_user, db_pass)
    if err or not schema or not table:
        return {"success": False, "updated": 0, "inserted": 0, "deleted": 0, "error": err or "No se pudo determinar la tabla."}

    try:
        aux_engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{aux_db_name}",
            connect_args={"connect_timeout": 8}
        )

        updates = []
        inserts = []
        deletes = []

        has_id = "id" in original_df.columns and "id" in edited_df.columns
        orig_map = {}
        if has_id:
            for _, row in original_df.iterrows():
                if pd.notnull(row["id"]):
                    try:
                        orig_map[int(row["id"])] = row
                    except (ValueError, TypeError):
                        pass

        # Identificar updates e inserts
        for _, row in edited_df.iterrows():
            rid_raw = row.get("id") if has_id else None
            is_new = False
            rid = None
            if rid_raw is None or pd.isna(rid_raw):
                is_new = True
            else:
                try:
                    rid = int(rid_raw)
                    if rid not in orig_map or rid <= 0:
                        is_new = True
                except (ValueError, TypeError):
                    is_new = True

            orig_val = "" if pd.isna(row.get("original_value")) else str(row.get("original_value")).strip()
            srch_val = "" if pd.isna(row.get("srch_value")) else str(row.get("srch_value")).strip()
            final_val = "" if pd.isna(row.get("final_value")) else str(row.get("final_value")).strip()

            if is_new:
                if orig_val or final_val:
                    if not srch_val and orig_val:
                        srch_val = normalize_srch_value(orig_val)
                    inserts.append({
                        "original_value": orig_val,
                        "srch_value": srch_val,
                        "final_value": final_val
                    })
            else:
                orig_row = orig_map[rid]
                diff = {}
                for col in ["original_value", "srch_value", "final_value"]:
                    if col in edited_df.columns and col in original_df.columns:
                        v_old = "" if pd.isna(orig_row[col]) else str(orig_row[col]).strip()
                        v_new = "" if pd.isna(row[col]) else str(row[col]).strip()
                        if v_old != v_new:
                            diff[col] = v_new

                if diff:
                    if "original_value" in diff and not diff.get("srch_value") and not srch_val:
                        diff["srch_value"] = normalize_srch_value(diff["original_value"])
                    updates.append((rid, diff))

        # Identificar deletes si allow_delete es True
        if allow_delete and has_id:
            edited_ids = set()
            for _, r in edited_df.iterrows():
                try:
                    val = r.get("id")
                    if pd.notnull(val) and not pd.isna(val):
                        edited_ids.add(int(val))
                except (ValueError, TypeError):
                    pass
            for orig_id in orig_map.keys():
                if orig_id not in edited_ids:
                    deletes.append(orig_id)

        if not updates and not inserts and not deletes:
            return {"success": True, "updated": 0, "inserted": 0, "deleted": 0, "error": None, "message": "No hay cambios pendientes."}

        # Ejecutar en transacción atómica
        with aux_engine.begin() as conn:
            # 1. Updates
            for rid, diff in updates:
                set_parts = []
                params = {"_target_id": rid}
                for k, v in diff.items():
                    set_parts.append(f'"{k}" = :{k}')
                    params[k] = v
                sql_upd = f'UPDATE "{schema}"."{table}" SET {", ".join(set_parts)} WHERE "id" = :_target_id;'
                conn.execute(text(sql_upd), params)

            # 2. Inserts
            for ins_data in inserts:
                sql_ins = f'INSERT INTO "{schema}"."{table}" ("original_value", "srch_value", "final_value", "created_at") VALUES (:original_value, :srch_value, :final_value, NOW());'
                conn.execute(text(sql_ins), ins_data)

            # 3. Deletes
            for del_id in deletes:
                sql_del = f'DELETE FROM "{schema}"."{table}" WHERE "id" = :del_id;'
                conn.execute(text(sql_del), {"del_id": del_id})

        return {
            "success": True,
            "updated": len(updates),
            "inserted": len(inserts),
            "deleted": len(deletes),
            "error": None
        }
    except Exception as exc:
        return {"success": False, "updated": 0, "inserted": 0, "deleted": 0, "error": str(exc)}


def insert_single_replacement_record(
    report_code: str,
    original_value: str,
    srch_value: str,
    final_value: str,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax"
) -> Tuple[bool, Optional[str]]:
    """Inserta un único registro de reemplazo en la tabla correspondiente."""
    schema, table, aux_db_name, err = get_replacement_table_target(report_code, db_host, db_port, db_user, db_pass)
    if err or not schema or not table:
        return False, err or "No se pudo determinar la tabla."

    orig_clean = str(original_value).strip()
    final_clean = str(final_value).strip()
    srch_clean = str(srch_value).strip() if srch_value else normalize_srch_value(orig_clean)

    if not orig_clean and not final_clean:
        return False, "Debes ingresar al menos el valor original o el valor final."

    try:
        aux_engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{aux_db_name}",
            connect_args={"connect_timeout": 8}
        )
        with aux_engine.begin() as conn:
            conn.execute(
                text(f'INSERT INTO "{schema}"."{table}" ("original_value", "srch_value", "final_value", "created_at") VALUES (:orig, :srch, :final, NOW());'),
                {"orig": orig_clean, "srch": srch_clean, "final": final_clean}
            )
        return True, None
    except Exception as exc:
        return False, str(exc)


def delete_single_replacement_record(
    report_code: str,
    record_id: int,
    db_host: str = "10.0.0.16",
    db_port: int = 5434,
    db_user: str = "postgres",
    db_pass: str = "datax"
) -> Tuple[bool, Optional[str]]:
    """Elimina un único registro de reemplazo por su ID."""
    schema, table, aux_db_name, err = get_replacement_table_target(report_code, db_host, db_port, db_user, db_pass)
    if err or not schema or not table:
        return False, err or "No se pudo determinar la tabla."

    try:
        aux_engine = create_engine(
            f"postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{aux_db_name}",
            connect_args={"connect_timeout": 8}
        )
        with aux_engine.begin() as conn:
            conn.execute(
                text(f'DELETE FROM "{schema}"."{table}" WHERE "id" = :rid;'),
                {"rid": int(record_id)}
            )
        return True, None
    except Exception as exc:
        return False, str(exc)


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
            if c_low in ("valor", "file", "fecha") or c_low.startswith(("titulo", "id_")):
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


def get_latest_download_for_report(report_code: str, engine) -> Optional[Dict]:
    """Obtiene la última descarga registrada para este reporte en platform_db con su archivo Excel."""
    query = f"""
        SELECT d.id_download, d.path, d.downloaded_to
        FROM report r
        JOIN download d ON r.id_file = d.id_file
        WHERE r.code = '{report_code}'
        ORDER BY d.id_download DESC
        LIMIT 1;
    """
    try:
        df = pd.read_sql_query(query, con=engine)
        if df.empty:
            return None
        row = df.iloc[0].to_dict()
        paths = [p.strip() for p in str(row.get("path", "")).split(";") if p.strip()]
        excel_paths = [p for p in paths if p.lower().endswith((".xls", ".xlsx"))]
        best_file = excel_paths[0] if excel_paths else (paths[0] if paths else "")
        return {
            "id_download": int(row["id_download"]),
            "file": best_file,
            "downloaded_to": str(row.get("downloaded_to", "")),
            "all_paths": paths
        }
    except Exception as exc:
        return None
