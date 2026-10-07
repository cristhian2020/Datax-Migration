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
    """Transforma el código fuente V1 al estándar V2."""
    code_content = raw_code

    # 1. Limpiar rutas obsoletas de sys.path
    code_content = re.sub(r"sys\.path\.append\([^)]*\)\s*", "", code_content)

    # 2. Corregir imports de download_tools hacia los paths oficiales
    code_content = re.sub(r"\bfrom\s+(?:models\.)?(?:download\.)?tools\.download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bfrom\s+download_tools\b", "from models.download.tools.download_tools", code_content)
    code_content = re.sub(r"\bimport\s+download_tools\b", "import models.download.tools.download_tools as download_tools", code_content)

    # 3. Separar header y limpiar cualquier import previo o try/except obsoleto de Download_Base
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
    base_name = "Download_Base"
    official_import = "from models.download.Download_Base import Download_Base"

    while i < n:
        line = lines[i]
        stripped = line.strip()

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

            if base_name.lower() in all_block_text.lower():
                i = j
                continue

            if "download_tools" in all_block_text:
                for tl in try_lines:
                    if tl.strip().startswith(("from ", "import ")):
                        new_header_lines.append(tl.strip())
                i = j
                continue

            new_header_lines.append(line)
            new_header_lines.extend(try_lines)
            new_header_lines.extend(except_lines)
            i = j
            continue

        if (stripped.startswith("from ") or stripped.startswith("import ")) and base_name.lower() in stripped.lower():
            i += 1
            continue

        if re.match(rf"^{base_name}\s*=\s*object\b", stripped, re.IGNORECASE):
            i += 1
            continue

        new_header_lines.append(line)
        i += 1

    cleaned_header = "\n".join(new_header_lines).strip()
    code_content = f"{official_import}\n{cleaned_header}\n\n{body}"

    # 4. Renombrar clase principal a <CODE>, preservando clase base si no es Executor
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

    # 4. Corrección común en Playwright: row.query_selector_all("//td") -> "td"
    code_content = code_content.replace('row.query_selector_all("//td")', 'row.query_selector_all("td")')
    code_content = code_content.replace("row.query_selector_all('//td')", "row.query_selector_all('td')")

    # 5. Regla estricta Tipo I: compare_files debe retornar False si no hay novedades
    if "Tipo I" in str(download_type) or "file_download_template" in str(download_type):
        if "def compare_files" in code_content:
            parts = code_content.split("def compare_files")
            pre_compare = parts[0]
            compare_body = parts[1]
            compare_body = re.sub(
                r"return\s+\[\]\s*$",
                "return False",
                compare_body,
                flags=re.MULTILINE,
            )
            code_content = pre_compare + "def compare_files" + compare_body

    # 6. Limpiar alias huérfanos anteriores
    code_content = re.sub(r'^[ \t]*Robot\s*=\s*[A-Za-z0-9_]+[^\n]*\n?', '', code_content, flags=re.MULTILINE)
    code_content = re.sub(r'^[ \t]*Executor_[A-Za-z0-9_]+\s*=\s*[A-Za-z0-9_]+[^\n]*\n?', '', code_content, flags=re.MULTILINE)

    # 7. Agregar alias de compatibilidad oficiales
    alias_footer = f"\n\nExecutor_{code} = {code}\nRobot = {code}\n"
    code_content = code_content.rstrip() + alias_footer

    return code_content


def diagnose_download_test_failure(test_output: str, test_updated_to: str, code: str) -> List[str]:
    """Analiza la salida de error del test unitario de descarga y devuelve diagnósticos y sugerencias accionables."""
    diagnostics = []

    # 1. Detectar excepciones explícitas de Python en la ejecución del robot antes de aserciones
    exception_matches = re.findall(r"(?:ValueError|TypeError|AttributeError|KeyError|IndexError|FileNotFoundError|ModuleNotFoundError):\s*([^\n\r]+)", test_output)
    if exception_matches:
        for err_msg in exception_matches[:2]:
            diagnostics.append(
                f"⚠️ **Excepción en la lógica del robot:** `{err_msg.strip()}`.\n"
                f"   - **Causa:** Ocurrió un error en el scraping o en la clase base (ej. selector no encontrado, pestaña faltante o URL obsoleta).\n"
                f"   - **Solución:** Revisa la clase base correspondiente (ej. CNDC, ASFI, BCB) o la URL en la BD."
            )

    if any(k in test_output for k in ["Playwright", "TimeoutError", "net::ERR_", "Timeout 30000ms exceeded"]):
        diagnostics.append(
            "⏱️ **Tiempo de espera o red:** El navegador Playwright no pudo cargar la página o se agotó el tiempo de espera.\n"
            "   - **Solución:** Verifica que el portal web esté en línea y accesible desde tu navegador, o ajusta el tiempo de espera."
        )

    if "NameError" in test_output:
        diagnostics.append(
            "⚠️ **Error en código del Robot:** Hay un atributo, método o clase no definida en el archivo generado.\n"
            "   - **Solución:** Revisa la clase y que herede correctamente de Download_Base o su clase base."
        )

    # 2. Si no hubo excepciones explícitas, evaluar aserciones de scraping y fecha
    if not diagnostics:
        if "At least one file must be scraped" in test_output:
            diagnostics.append(
                f"📅 **Fallo de scraping por fecha:** No se detectaron archivos nuevos posteriores a `{test_updated_to}`.\n"
                f"   - **Causa más frecuente:** La página web del portal no tiene archivos posteriores a `{test_updated_to}` (o la fecha de prueba es muy reciente).\n"
                f"   - **Solución recomendada:** Prueba con una fecha más antigua (ej. `2024-01-01` o `2020-01-01`).\n"
                f"   - **Alternativa:** Si el código fue verificado manualmente, puedes generar el DAG directamente con el botón de rescate abajo."
            )

        if "At least one file must pass the date filter" in test_output:
            diagnostics.append(
                f"🔍 **Fallo en filtro de fechas (compare_files):** Se descargaron archivos pero ninguno superó la fecha `{test_updated_to}`.\n"
                f"   - **Solución:** Utiliza una fecha de prueba anterior a la fecha de emisión de los archivos para verificar la comparación."
            )

    if not diagnostics and ("FAIL" in test_output or "ERROR" in test_output):
        diagnostics.append(
            "⚠️ **Fallo en aserción del test unitario:** Revisa los logs detallados para ver la condición exacta que no se cumplió."
        )

    return diagnostics

def generate_download_dag_only(code: str, new_repo_path: str) -> Dict:
    """Genera exclusivamente el archivo DAG de descarga sin volver a ejecutar los tests unitarios."""
    generator_file = os.path.join(new_repo_path, "include", "main-generate.py")
    if not os.path.isfile(generator_file):
        return {"success": False, "message": f"Generador no encontrado en {generator_file}"}

    try:
        include_dir = os.path.join(new_repo_path, "include")
        if include_dir not in sys.path:
            sys.path.insert(0, include_dir)
        if new_repo_path not in sys.path:
            sys.path.insert(0, new_repo_path)

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
                return {"success": True, "dag_path": dag_path, "message": f"DAG generado exitosamente en: {dag_path}"}
            else:
                return {"success": False, "message": "El generador se ejecutó pero el archivo DAG no fue creado."}
        else:
            return {"success": False, "message": f"No se encontraron metadatos en la BD para generar DAG de {code}."}
    except Exception as exc:
        return {"success": False, "message": f"Excepción al generar DAG: {exc}"}


def reset_file_updated_to_in_db(code: str, new_date: str, engine) -> Dict:
    """Actualiza la fecha 'updated_to' en la tabla 'file' de platform_db."""
    try:
        with engine.begin() as conn:
            if not new_date or new_date.strip().upper() == "NULL":
                sql = text("UPDATE file SET updated_to = NULL WHERE code = :code;")
                conn.execute(sql, {"code": code})
                return {"success": True, "message": f"Fecha 'updated_to' de {code} reseteada a NULL en platform_db."}
            else:
                sql = text("UPDATE file SET updated_to = :dt WHERE code = :code;")
                conn.execute(sql, {"code": code, "dt": new_date.strip()})
                return {"success": True, "message": f"Fecha 'updated_to' de {code} actualizada a '{new_date.strip()}' en platform_db."}
    except Exception as exc:
        return {"success": False, "message": f"Error al actualizar BD: {exc}"}


def apply_download_migration(code: str, source_file: str, new_repo_path: str, download_type: str = "", skip_test: bool = False, skip_dag: bool = True, test_updated_to: str = "2024-01-01") -> Dict:
    """Aplica la migración completa y retorna log del proceso y diagnósticos."""
    logs = []
    diagnostics = []
    success = True
    dest_file = None

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
            type_map = [
                (r"\bTipo\s+IV\b|file_download_type_iv|multi_file_download_template", "test_download_type_iv.py"),
                (r"\bTipo\s+III\b|file_download_type_iii|data_download_template", "test_download_type_iii.py"),
                (r"\bTipo\s+II\b|file_download_type_ii|direct_download_template", "test_download_type_ii.py"),
                (r"\bTipo\s+I\b|file_download_type_i|file_download_template", "test_download_type_i.py"),
            ]
            test_file = None
            for pattern, t_file in type_map:
                if re.search(pattern, str(download_type), re.IGNORECASE):
                    test_file = t_file
                    break
            if test_file:
                test_path = os.path.join(new_repo_path, "models", "download", "tests", test_file)
                logs.append(f"🧪 Ejecutando test unitario: {test_file} con fecha {test_updated_to}...")
                env = os.environ.copy()
                env["CODE_ROBOT"] = code
                env["UPDATED_TO"] = test_updated_to

                res = subprocess.run([sys.executable, "-m", "unittest", test_path], cwd=new_repo_path, env=env, capture_output=True, text=True)
                test_output = res.stderr or res.stdout
                if res.returncode == 0:
                    logs.append(f"🎉 Test unitario APROBADO (OK)")
                else:
                    logs.append(f"⚠️ Test unitario FALLÓ:\n{test_output}")
                    success = False
                    diagnostics = diagnose_download_test_failure(test_output, test_updated_to, code)
                    for d in diagnostics:
                        logs.append(f"💡 {d}")
            else:
                logs.append(f"ℹ️ Tipo de descarga no mapeado a test unitario ({download_type})")

        # 3. Generación del DAG
        if not skip_dag and success:
            dag_res = generate_download_dag_only(code, new_repo_path)
            if dag_res["success"]:
                logs.append(f"🚀 DAG generado exitosamente en: {dag_res.get('dag_path')}")
            else:
                logs.append(f"⚠️ {dag_res.get('message')}")
                success = False

    except Exception as exc:
        logs.append(f"❌ Excepción durante la migración: {exc}")
        success = False

    return {
        "success": success,
        "logs": logs,
        "diagnostics": diagnostics,
        "can_force_dag": (dest_file is not None and os.path.isfile(dest_file)),
        "file_saved": dest_file
    }
