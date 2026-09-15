import os
import time
from typing import Dict, List, Tuple, Callable, Optional
import paramiko

def test_connection(
    host: str,
    port: int = 22,
    username: str = "datax-pds",
    password: Optional[str] = None,
    key_filename: Optional[str] = None,
    timeout: int = 8
) -> Tuple[bool, str]:
    """Prueba la conexión SSH al servidor remoto."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            key_filename=key_filename,
            timeout=timeout,
            look_for_keys=True if not password else False
        )
        stdin, stdout, stderr = client.exec_command("uname -a")
        sys_info = stdout.read().decode("utf-8", errors="ignore").strip()
        client.close()
        return True, f"Conexión exitosa. Sistema: {sys_info}"
    except Exception as e:
        return False, f"Fallo al conectar: {str(e)}"

def list_migrated_robots(local_repo: str, process_type: str = "download") -> List[Dict]:
    """Escanea el repositorio local dev y devuelve la lista de robots ya migrados en models/download o models/conversion."""
    models_dir = os.path.join(local_repo, "models", process_type)
    if not os.path.isdir(models_dir):
        return []

    robots = []
    for entry in sorted(os.listdir(models_dir)):
        entry_path = os.path.join(models_dir, entry)
        if not os.path.isdir(entry_path):
            continue
        
        # Debe tener formato D_... o C_...
        if not (entry.startswith("D_") or entry.startswith("C_")):
            continue

        files = [f for f in os.listdir(entry_path) if os.path.isfile(os.path.join(entry_path, f))]
        main_py = os.path.join(entry_path, f"{entry}.py")
        has_main = os.path.isfile(main_py)
        
        robots.append({
            "code": entry,
            "folder_path": entry_path,
            "has_main": has_main,
            "files": files,
            "files_count": len(files)
        })

    return robots

def deploy_robot_to_server(
    host: str,
    port: int = 22,
    username: str = "datax-pds",
    password: Optional[str] = None,
    key_filename: Optional[str] = None,
    remote_base_path: str = "/home/datax-pds/datax/data-processing-platform-dev",
    process_type: str = "download",
    robot_code: str = "",
    local_dir: str = "",
    generate_dag: bool = True,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """
    Sube los archivos del robot al servidor mediante SFTP y ejecuta
    docker compose exec airflow-worker python include/main-generate.py
    """
    logs = []

    def log(msg: str):
        logs.append(msg)
        if log_callback:
            log_callback(msg)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        log(f"🔌 Conectando a {username}@{host}:{port}...")
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            key_filename=key_filename,
            timeout=10,
            look_for_keys=True if not password else False
        )
        log("✅ Conexión SSH establecida.")

        # 1. Crear carpeta remota (manejando permisos con sudo si es necesario)
        remote_folder = f"{remote_base_path}/models/{process_type}/{robot_code}"
        log(f"📁 Verificando carpeta remota: {remote_folder}...")

        mkdir_cmd = f"mkdir -p '{remote_folder}'"
        stdin, stdout, stderr = client.exec_command(mkdir_cmd)
        exit_status = stdout.channel.recv_exit_status()

        if exit_status != 0:
            err_msg = stderr.read().decode("utf-8", errors="ignore").strip()
            log(f"⚠️ mkdir normal requirió permisos ({err_msg}). Intentando con sudo...")
            if password:
                sudo_cmd = f"echo '{password}' | sudo -S mkdir -p '{remote_folder}' && echo '{password}' | sudo -S chown -R {username}:{username} '{remote_folder}'"
                stdin, stdout, stderr = client.exec_command(sudo_cmd)
                sudo_exit = stdout.channel.recv_exit_status()
                if sudo_exit != 0:
                    sudo_err = stderr.read().decode("utf-8", errors="ignore").strip()
                    log(f"❌ Falló creación con sudo: {sudo_err}")
                    return {"success": False, "logs": logs, "dag_generated": False}
                log("✅ Carpeta remota creada con permisos asignados correctamente.")
            else:
                log("❌ No se especificó contraseña para ejecutar sudo.")
                return {"success": False, "logs": logs, "dag_generated": False}
        else:
            log("✅ Carpeta remota lista.")

        # 2. Subir archivos locales mediante SFTP
        sftp = client.open_sftp()
        uploaded_count = 0

        if process_type == "conversion":
            # Para conversión: en models/conversion/<CODE> SOLO van archivos .py
            log(f"📤 Subiendo scripts Python de `{local_dir}` a `{remote_folder}`...")
            for f in os.listdir(local_dir):
                if not f.endswith(".py") or f in ("__init__.py", "__pycache__", ".DS_Store"):
                    continue
                l_path = os.path.join(local_dir, f)
                if os.path.isfile(l_path):
                    r_path = f"{remote_folder}/{f}"
                    log(f"   ⬆️ Subiendo script {f}...")
                    sftp.put(l_path, r_path)
                    uploaded_count += 1

            # Limpiar archivos no deseados (.xlsx, .pdf, .sqlite, .csv, etc.) en models/conversion/<CODE>
            clean_cmd = f"rm -f '{remote_folder}/*.xlsx' '{remote_folder}/*.pdf' '{remote_folder}/*.sqlite' '{remote_folder}/*.csv' '{remote_folder}/__init__.py'"
            try:
                client.exec_command(clean_cmd)
            except Exception:
                pass

            # Subir archivos .sqlite a /mnt/datos1/data_process/<PAIS>/<D_CODE>/
            parts = robot_code.split("_")
            country = parts[1] if len(parts) > 1 else "BO"
            d_code = f"D_{parts[1]}_{parts[2]}" if len(parts) >= 3 else robot_code.replace("C_", "D_")
            remote_data_dir = f"/mnt/datos1/data_process/{country}/{d_code}"

            sqlite_files = [f for f in os.listdir(local_dir) if f.endswith(".sqlite") and os.path.isfile(os.path.join(local_dir, f))]
            if sqlite_files:
                log(f"📁 Preparando carpeta de datos remota para SQLite: `{remote_data_dir}`...")
                mkdir_sql = f"mkdir -p '{remote_data_dir}' && chmod 777 '{remote_data_dir}'"
                stdin, stdout, stderr = client.exec_command(mkdir_sql)
                if stdout.channel.recv_exit_status() != 0 and password:
                    sudo_sql = f"echo '{password}' | sudo -S mkdir -p '{remote_data_dir}' && echo '{password}' | sudo -S chmod 777 '{remote_data_dir}'"
                    stdin, stdout, stderr = client.exec_command(sudo_sql)
                    stdout.channel.recv_exit_status()

                for sql_f in sqlite_files:
                    local_sql = os.path.join(local_dir, sql_f)
                    remote_sql = f"{remote_data_dir}/{sql_f}"
                    log(f"   💾 Subiendo archivo SQLite `{sql_f}` a `{remote_data_dir}`...")
                    sftp.put(local_sql, remote_sql)
                    try:
                        client.exec_command(f"chmod 777 '{remote_sql}'")
                        if password:
                            client.exec_command(f"echo '{password}' | sudo -S chmod 777 '{remote_sql}'")
                    except Exception:
                        pass
                    log(f"   ✅ SQLite `{sql_f}` desplegado en `{remote_data_dir}` con permisos 777.")
        else:
            log(f"📤 Subiendo archivos de `{local_dir}` a `{remote_folder}`...")
            local_files = [
                f for f in os.listdir(local_dir) 
                if os.path.isfile(os.path.join(local_dir, f)) 
                and f not in ("__init__.py", "__pycache__", ".DS_Store") 
                and not f.endswith(".pyc")
            ]
            for fname in local_files:
                l_path = os.path.join(local_dir, fname)
                r_path = f"{remote_folder}/{fname}"
                log(f"   ⬆️ Subiendo {fname}...")
                sftp.put(l_path, r_path)
                uploaded_count += 1

            # Limpiar __init__.py en el servidor si existía previamente
            try:
                client.exec_command(f"rm -f '{remote_folder}/__init__.py'")
            except Exception:
                pass

        sftp.close()
        log(f"✅ {uploaded_count} archivo(s) de código transferido(s) con éxito.")

        # 3. Generar DAG en Docker en el servidor si se solicitó
        dag_generated = False
        if generate_dag:
            log("⚙️ Ejecutando generador de DAGs en Docker...")
            proc_opt = "1" if process_type == "download" else "2"
            
            # Comando con pipe para responder automáticamente al generador interactivo
            gen_cmd = (
                f"cd {remote_base_path} && "
                f"printf '{proc_opt}\\n1\\n{robot_code}\\n' | "
                f"docker compose exec -T airflow-worker python include/main-generate.py"
            )
            
            log(f"   Comando remoto: printf '{proc_opt}\\n1\\n{robot_code}\\n' | docker compose exec -T airflow-worker python include/main-generate.py")
            stdin, stdout, stderr = client.exec_command(gen_cmd, get_pty=True)

            output_lines = []
            while True:
                line = stdout.readline()
                if not line:
                    break
                clean_line = line.strip()
                if clean_line:
                    output_lines.append(clean_line)
                    log(f"   [Docker] {clean_line}")

            cmd_exit = stdout.channel.recv_exit_status()
            
            out_full = " ".join(output_lines)
            if "Generated:" in out_full or "Done!" in out_full or cmd_exit == 0:
                dag_generated = True
                log("🎉 DAG generado exitosamente en el servidor.")
            else:
                log("⚠️ El comando de generación terminó con advertencias o errores.")

        client.close()
        return {
            "success": True,
            "logs": logs,
            "dag_generated": dag_generated
        }

    except Exception as e:
        log(f"❌ Excepción durante el despliegue: {str(e)}")
        if client:
            client.close()
        return {
            "success": False,
            "logs": logs,
            "dag_generated": False
        }


def trigger_dag_on_server(
    host: str,
    port: int = 22,
    username: str = "datax-pds",
    password: Optional[str] = None,
    remote_base_path: str = "/home/datax-pds/datax/data-processing-platform-dev",
    dag_id: str = "",
    conf: Optional[Dict] = None,
    log_callback: Optional[Callable[[str], None]] = None
) -> Dict:
    """Dispara un DAG de Airflow en el servidor remoto con parámetros de configuración."""
    logs = []

    def log(msg: str):
        logs.append(msg)
        if log_callback:
            log_callback(msg)

    import json
    conf_json = json.dumps(conf or {})
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        log(f"🔌 Conectando a {username}@{host}:{port}...")
        client.connect(
            hostname=host,
            port=port,
            username=username,
            password=password,
            timeout=10,
            look_for_keys=True if not password else False
        )
        log("✅ Conexión SSH establecida.")

        # Comando para disparar DAG en Airflow worker
        cmd = (
            f"cd {remote_base_path} && "
            f"docker compose exec -T airflow-worker airflow dags trigger {dag_id} --conf '{conf_json}'"
        )
        log(f"🚀 Ejecutando: docker compose exec -T airflow-worker airflow dags trigger {dag_id}...")
        stdin, stdout, stderr = client.exec_command(cmd, get_pty=True)

        output_lines = []
        for line in iter(stdout.readline, ""):
            clean = line.strip()
            if clean:
                output_lines.append(clean)
                log(f"   [Airflow] {clean}")

        status = stdout.channel.recv_exit_status()
        client.close()

        success = (status == 0) or any("creating dag run" in l.lower() or "queued" in l.lower() for l in output_lines)
        return {
            "success": success,
            "logs": logs,
            "output": "\n".join(output_lines)
        }
    except Exception as exc:
        if client:
            client.close()
        log(f"❌ Error al disparar DAG: {exc}")
        return {"success": False, "logs": logs, "output": str(exc)}
