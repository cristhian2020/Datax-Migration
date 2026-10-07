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
               converted_report_path, "isActive" AS is_active
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
    base_name = "Conversion_Base"
    official_import = "from models.conversion.Conversion_Base import Conversion_Base"

    # 1. Eliminar sys.path.append viejos o rutas relativas
    code_content = re.sub(r"sys\.path\.append\([^)]*\)\s*", "", code_content)

    # 2. Corregir imports de herramientas hacia los paths oficiales de la Plataforma V2
    code_content = re.sub(r"\bfrom\s+(?:models\.)?(?:conversion\.)?tools\.conversion_tools\b", "from models.conversion.tools.conversion_tools", code_content)
    code_content = re.sub(r"\bfrom\s+conversion_tools\b", "from models.conversion.tools.conversion_tools", code_content)
    code_content = re.sub(r"\bimport\s+conversion_tools\b", "import models.conversion.tools.conversion_tools as conversion_tools", code_content)

    code_content = re.sub(r"\bfrom\s+(?:models\.)?(?:download\.)?tools\.download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bfrom\s+download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bimport\s+download_tools\b", "import models.download.tools.download_tools as download_tools", code_content)

    # 3. Separar header (antes de la clase principal) del cuerpo
    class_match = re.search(r"^[ \t]*class\s+[A-Za-z0-9_]+", code_content, flags=re.MULTILINE)
    if class_match:
        header = code_content[:class_match.start()]
        body = code_content[class_match.start():]
    else:
        header = code_content
        body = ""

    lines = header.splitlines()
    new_header_lines = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # Si encontramos un bloque 'try:' en el header
        if stripped == "try:":
            try_lines = []
            except_lines = []
            in_except = False
            j = i + 1

            while j < n:
                cur_line = lines[j]
                cur_stripped = cur_line.strip()

                if cur_stripped and not cur_line.startswith((" ", "\t")):
                    if cur_stripped.startswith("except"):
                        in_except = True
                        except_lines.append(cur_line)
                        j += 1
                        continue
                    else:
                        break

                if in_except:
                    except_lines.append(cur_line)
                else:
                    try_lines.append(cur_line)
                j += 1

            all_block_text = "\n".join(try_lines + except_lines)

            # Si envuelve Conversion_Base: descartar todo el bloque obsoleto
            if base_name.lower() in all_block_text.lower():
                i = j
                continue

            # Si envuelve conversion_tools / download_tools: extraer solo los imports limpios
            if "conversion_tools" in all_block_text or "download_tools" in all_block_text:
                for tl in try_lines:
                    if tl.strip().startswith(("from ", "import ")):
                        new_header_lines.append(tl.strip())
                i = j
                continue

            # Si es otro bloque try:, conservarlo
            new_header_lines.append(line)
            new_header_lines.extend(try_lines)
            new_header_lines.extend(except_lines)
            i = j
            continue

        # Eliminar imports sueltos de Conversion_Base
        if (stripped.startswith("from ") or stripped.startswith("import ")) and base_name.lower() in stripped.lower():
            i += 1
            continue

        # Eliminar asignaciones Conversion_Base = object
        if re.match(rf"^{base_name}\s*=\s*object\b", stripped, re.IGNORECASE):
            i += 1
            continue

        new_header_lines.append(line)
        i += 1

    cleaned_header = "\n".join(new_header_lines).strip()

    # 4. Asegurar exactamente un import oficial limpio al inicio
    code_content = f"{official_import}\n{cleaned_header}\n\n{body}"

    # 5. Renombrar clase principal a <REPORT_CODE>(Conversion_Base)
    class_pattern = r"class\s+([A-Za-z0-9_]+)(?:\s*\([^)]*\))?\s*:"
    m = re.search(class_pattern, code_content)
    if m:
        cls_name = m.group(1)
        if cls_name != report_code:
            full_match = m.group(0)
            code_content = code_content.replace(full_match, f"class {report_code}({base_name}):", 1)

    # 6. Limpiar traceback.print_exc() inyectados en bloques de control de flujo (ej. except ValueError)
    lines = code_content.splitlines()
    cleaned_lines = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        cleaned_lines.append(line)
        if re.search(r"^\s*except\s+(?:\([^)]*\bValueError\b[^)]*\)|ValueError\b)", line):
            if i + 1 < n and "traceback.print_exc()" in lines[i + 1]:
                i += 1
        i += 1
    code_content = "\n".join(cleaned_lines)

    # 7. Asegurar traceback.print_exc() SOLO en bloques de excepciones generales (Exception)
    lines = code_content.splitlines()
    new_lines = []
    for i, line in enumerate(lines):
        new_lines.append(line)
        if re.search(r"^\s*except\s+(?:Exception\b|as\b\s*\w+)", line, re.IGNORECASE):
            next_block = "\n".join(lines[i + 1 : i + 4])
            if "print_exc" not in next_block:
                indent = re.match(r"^(\s*)", line).group(1) + "    "
                new_lines.append(f"{indent}import traceback; traceback.print_exc()")
    code_content = "\n".join(new_lines)

    # 8. Limpiar cualquier alias huérfano previo para evitar NameError
    code_content = re.sub(r'^[ \t]*Robot\s*=\s*[A-Za-z0-9_]+[^\n]*\n?', '', code_content, flags=re.MULTILINE)
    code_content = re.sub(r'^[ \t]*Executor_[A-Za-z0-9_]+\s*=\s*[A-Za-z0-9_]+[^\n]*\n?', '', code_content, flags=re.MULTILINE)

    # 9. Agregar alias oficiales limpios al pie
    alias_footer = f"\n\nExecutor_{report_code} = {report_code}\nRobot = {report_code}\n"
    code_content = code_content.rstrip() + alias_footer

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

    diagnostics = diagnose_conversion_test_failure(res.stdout, res.stderr, report_code) if res.returncode != 0 else []

    return {
        "success": res.returncode == 0,
        "stdout": res.stdout,
        "stderr": res.stderr,
        "sqlite_created": sqlite_exists,
        "sqlite_path": sqlite_path if sqlite_exists else None,
        "diagnostics": diagnostics
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


def diagnose_conversion_test_failure(stdout: str, stderr: str, report_code: str) -> List[str]:
    """Diagnostica fallos en tests de conversión y devuelve sugerencias accionables."""
    output = f"{stdout}\n{stderr}"
    diagnostics = []

    if "NameError: name" in output and "is not defined" in output:
        match = re.search(r"name '([^']+)' is not defined", output)
        missing_name = match.group(1) if match else "desconocido"
        diagnostics.append(
            f"⚠️ **NameError detectado (`{missing_name}`):**\n"
            f"   - **Causa:** El código hace referencia a una variable o clase que no existe (ej. un alias residual `Robot = {missing_name}`).\n"
            f"   - **Solución:** Guarda nuevamente el código desde el Paso 1 para que el refactor limpie los alias automáticamente."
        )

    if "TypeError: module() takes at most 2 arguments" in output or "cannot import name 'Conversion_Base'" in output:
        diagnostics.append(
            "⚠️ **Error de Importación de Conversion_Base:**\n"
            "   - **Causa:** Import incorrecto `from models.conversion import Conversion_Base`.\n"
            "   - **Solución:** Debe ser estrictamente `from models.conversion.Conversion_Base import Conversion_Base`."
        )

    if "validate_data_results" in output or "AssertionError: True is not false" in output:
        diagnostics.append(
            "⚖️ **Fallo en Validación Matemática (Sumas / Tolerancia):**\n"
            "   - **Causa:** `validate_data_results()` retornó `True` (indicando inconsistencia en las sumas por fecha).\n"
            "   - **Regla DATAX:** La función debe retornar `False` cuando los datos son consistentes y cuadran matemáticamente.\n"
            "   - **Solución:** Revisa si la suma de los componentes individuales difiere del Total General por más de la tolerancia (`TOLERANCE=6.0`)."
        )

    if "No such file or directory" in output or "FileNotFoundError" in output:
        diagnostics.append(
            "📁 **Archivo de muestra no encontrado:**\n"
            "   - **Causa:** La ruta del archivo de muestra (.xlsx/.pdf) no existe o no tiene permisos de lectura.\n"
            "   - **Solución:** Sube una muestra válida en el Paso 1 o usa la muestra descargada automáticamente de la base de datos."
        )

    if "IndexError" in output or "KeyError" in output:
        diagnostics.append(
            "🔍 **Error de Índices o Columnas en Extracción:**\n"
            "   - **Causa:** El DataFrame extraído no tiene la estructura de columnas o filas esperada por el robot.\n"
            "   - **Solución:** Verifica que el número de página sea correcto y que las cabeceras coincidan con la muestra actual."
        )

    if not diagnostics and ("FAIL" in output or "ERROR" in output):
        diagnostics.append(
            "⚠️ **Excepción durante la prueba:** Revisa la traza completa (traceback) mostrada a continuación."
        )

    return diagnostics


def reset_report_migrated_to_in_db(report_code: str, engine) -> Dict:
    """Resetea el campo 'migrated_to' a NULL en la tabla 'report' para permitir re-migraciones limpias en PostgreSQL."""
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            sql = text("UPDATE report SET migrated_to = NULL WHERE code = :code;")
            conn.execute(sql, {"code": report_code})
            return {"success": True, "message": f"Campo 'migrated_to' de {report_code} reseteado a NULL exitosamente."}
    except Exception as exc:
        return {"success": False, "message": f"Error al actualizar BD: {exc}"}
