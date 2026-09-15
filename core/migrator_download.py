
"""Lógica de migración para robots de descarga (Tipo I, II, III, IV)."""

import os
import re
import sys
import subprocess
import importlib.util
from typing import Dict, List, Optional, Tuple
import pandas as pd
from sqlalchemy import text


def scan_old_download_robots(old_repo_path: str) -> List[Dict]:
    """Escanea los robots de descarga disponibles en el repositorio antiguo."""
    download_dir = os.path.join(old_repo_path, "models", "download")
    if not os.path.isdir(download_dir):
        return []

    robots = []
    for item in sorted(os.listdir(download_dir)):
        item_path = os.path.join(download_dir, item)
        if not os.path.isdir(item_path):
            continue

        match = re.search(r"(D_[A-Z]{2}_\d{9})", item)
        if not match:
            continue

        code = match.group(1)
        # Buscar script principal
        script_file = None
        for candidate in [f"Executor_{code}.py", f"{code}.py"]:
            p = os.path.join(item_path, candidate)
            if os.path.isfile(p):
                script_file = p
                break

        if not script_file:
            for f in os.listdir(item_path):
                if f.endswith(".py") and not f.startswith("__"):
                    script_file = os.path.join(item_path, f)
                    break

        robots.append({
            "code": code,
            "folder": item_path,
            "script_file": script_file,
            "has_script": script_file is not None
        })

    return robots


def get_download_db_info(code: str, engine) -> Optional[Dict]:
    """Obtiene metadatos del robot desde platform_db."""
    query = f"""
        SELECT id_file, code, name, main_url, download_type, 
               schedule_interval, updated_to, key_words, state, path
        FROM file 
        WHERE code = '{code}';
    """
    try:
        df = pd.read_sql_query(query, con=engine)
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception as exc:
        return {"error": str(exc)}


def refactor_download_code(raw_code: str, code: str, download_type: str = "") -> str:
    """Transforma el código de V1 al estándar V2."""
    code_content = raw_code

    if "from models.download.Download_Base import Download_Base" not in code_content:
        code_content = "from models.download.Download_Base import Download_Base\n" + code_content

    # Limpiar rutas obsoletas de sys.path
    code_content = re.sub(r"""sys\.path\.append\(['"][^'"]*data-processing-platform[^'"]*['"]\)\s*""", "", code_content)
    code_content = re.sub(r"""sys\.path\.append\(['"][^'"]*platform_project[^'"]*['"]\)\s*""", "", code_content)

    # Renombrar clase principal a <CODE>, preservando clase base si no es Executor
    def _replace_class_parent(m):
        parent = m.group(1).strip() if m.group(1) else ""
        if parent in ["Executor", "object", ""] or not parent:
            parent = "Download_Base"
        return f"class {code}({parent}):"

    code_content, n = re.subn(
        r"class\s+Executor_[A-Za-z0-9_]+\s*(?:\(([^)]*)\))?\s*:",
        _replace_class_parent,
        code_content,
    )
    if n == 0:
        code_content = re.sub(
            r"class\s+[A-Za-z0-9_]+\s*(?:\(([^)]*)\))?\s*:",
            _replace_class_parent,
            code_content,
            count=1,
        )

    # Corrección Playwright XPath
    code_content = code_content.replace('row.query_selector_all("//td")', 'row.query_selector_all("td")')
    code_content = code_content.replace("row.query_selector_all('//td')", "row.query_selector_all('td')")

    # Regla Tipo I compare_files False
    if "Tipo I" in str(download_type):
        if "def compare_files" in code_content:
            parts = code_content.split("def compare_files")
            body = re.sub(r"return\s+\[\]\s*$", "return False", parts[1], flags=re.MULTILINE)
            code_content = parts[0] + "def compare_files" + body

    # Alias finales
    alias = f"\n\nExecutor_{code} = {code}\nRobot = {code}\n"
    if f"Executor_{code} = {code}" not in code_content:
        code_content += alias

    return code_content


def apply_download_migration(code: str, source_file: str, new_repo_path: str, download_type: str = "", skip_test: bool = False, skip_dag: bool = True, test_updated_to: str = "2024-01-01") -> Dict:
    """Aplica la migración completa y retorna log del proceso."""
    logs = []
    success = True

    try:
        with open(source_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_code = f.read()

        refactored = refactor_download_code(raw_code, code, download_type)

        # 1. Crear directorios y archivos
        dest_dir = os.path.join(new_repo_path, "models", "download", code)
        os.makedirs(dest_dir, exist_ok=True)

        # Eliminar __init__.py si existiera para cumplir con el estándar de los robots en el servidor
        init_path = os.path.join(dest_dir, "__init__.py")
        if os.path.exists(init_path):
            try:
                os.remove(init_path)
            except Exception:
                pass

        dest_file = os.path.join(dest_dir, f"{code}.py")
        with open(dest_file, "w", encoding="utf-8") as f:
            f.write(refactored)
        logs.append(f"✅ Archivo V2 guardado en: {dest_file}")

        # 2. Test Unitario
        if not skip_test:
            type_map = {
                "Tipo I": "test_download_type_i.py",
                "Tipo II": "test_download_type_ii.py",
                "Tipo III": "test_download_type_iii.py",
                "Tipo IV": "test_download_type_iv.py",
            }
            test_file = next((v for k, v in type_map.items() if k in str(download_type)), None)
            if test_file:
                test_path = os.path.join(new_repo_path, "models", "download", "tests", test_file)
                logs.append(f"🧪 Ejecutando test unitario: {test_file}...")
                env = os.environ.copy()
                env["CODE_ROBOT"] = code
                env["UPDATED_TO"] = test_updated_to

                res = subprocess.run([sys.executable, "-m", "unittest", test_path], cwd=new_repo_path, env=env, capture_output=True, text=True)
                if res.returncode == 0:
                    logs.append(f"🎉 Test unitario APROBADO (OK)")
                else:
                    logs.append(f"⚠️ Test unitario FALLÓ:\n{res.stderr or res.stdout}")
                    success = False
            else:
                logs.append(f"ℹ️ Tipo de descarga no mapeado a test unitario ({download_type})")

        # 3. Generación del DAG
        if not skip_dag and success:
            generator_file = os.path.join(new_repo_path, "include", "main-generate.py")
            if os.path.isfile(generator_file):
                spec = importlib.util.spec_from_file_location("main_generate", generator_file)
                gen_mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(gen_mod)
                RobotCodeHandler = getattr(gen_mod, "RobotCodeHandler")

                handler = RobotCodeHandler(process="download")
                handler.process_codes([code])
                if handler.robots:
                    handler.create_dags()
                    dag_path = os.path.join(new_repo_path, "dags", "download", f"{code}.py")
                    if os.path.isfile(dag_path):
                        logs.append(f"🚀 DAG generado exitosamente en: {dag_path}")
                    else:
                        logs.append(f"⚠️ No se encontró el archivo DAG generado.")
                        success = False
                else:
                    logs.append(f"⚠️ No se pudieron cargar datos desde BD para generar el DAG.")
                    success = False

    except Exception as exc:
        logs.append(f"❌ Excepción durante la migración: {exc}")
        success = False

    return {"success": success, "logs": logs}
