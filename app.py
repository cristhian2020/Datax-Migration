"""Datax Migration Studio - Interfaz Web Interactiva para Migración V1 -> V2."""

import os
import sys
import re
import importlib
import streamlit as st
import pandas as pd

# Setup paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import core.agent_analyzer
import core.migrator_migration
importlib.reload(core.agent_analyzer)
importlib.reload(core.migrator_migration)
from core.agent_analyzer import run_agent_sqlite_analysis, parse_commodity_price_unit
from core.config import (
    DEFAULT_GEMINI_API_KEY,
    DEFAULT_OLD_REPO,
    DEFAULT_NEW_REPO,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_PASS,
    DEFAULT_DB_NAME,
    DEFAULT_SSH_HOST,
    DEFAULT_SSH_PORT,
    DEFAULT_SSH_USER,
    DEFAULT_SSH_PASS,
    DEFAULT_GITHUB_REPO,
    DEFAULT_GITHUB_TOKEN,
    get_engine,
)
from core.github_client import (
    test_github_access,
    list_pull_requests,
    get_pr_files,
    download_github_file,
)
from core.migrator_download import (
    scan_old_download_robots,
    scan_v2_download_robots,
    save_v2_download_code,
    test_download_robot_v2,
    get_download_db_info,
    refactor_download_code,
    apply_download_migration,
    generate_download_dag_only,
    reset_file_updated_to_in_db,
)
from core.migrator_conversion import (
    scan_old_conversion_families,
    scan_v2_conversion_families,
    get_conversion_db_info,
    refactor_conversion_code,
    detect_available_samples,
    save_uploaded_sample_file,
    run_conversion_step_test,
    get_sqlite_data,
    get_replacement_table_data,
    save_replacement_table_changes,
    insert_single_replacement_record,
    delete_single_replacement_record,
    normalize_srch_value,
    setup_columns_to_review,
    apply_conversion_migration,
    get_latest_download_for_report,
    reset_report_migrated_to_in_db,
)
from core.migrator_migration import (
    scan_conversion_outputs,
    scan_existing_migration_robots,
    load_migration_robot_files,
    get_migration_db_info,
    inspect_sqlite_structure,
    generate_migration_sql,
    generate_migration_py,
    save_migration_files,
    get_latest_conversion_for_report,
)
from core.deployer import (
    test_connection,
    list_migrated_robots,
    deploy_robot_to_server,
    trigger_dag_on_server,
)


st.set_page_config(
    page_title="Datax Migration Studio",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)


def safe_dataframe(df: pd.DataFrame, use_container_width: bool = True, **kwargs):
    """Muestra un DataFrame con st.dataframe o fallback a HTML estilizado si falla pyarrow."""
    try:
        st.dataframe(df, use_container_width=use_container_width, **kwargs)
    except Exception:
        html_table = df.to_html(classes="safe-table", index=False, na_rep="-", border=0)
        styled_html = f"""
        <div style="max-height: 420px; overflow: auto; border: 1px solid #334155; border-radius: 6px; padding: 4px; background-color: #0f172a; margin-bottom: 1rem;">
            <style>
                table.safe-table {{ width: 100%; border-collapse: collapse; font-family: sans-serif; font-size: 0.88rem; }}
                table.safe-table th {{ background-color: #1e293b; color: #38bdf8; padding: 8px 10px; border-bottom: 1px solid #334155; text-align: left; position: sticky; top: 0; z-index: 1; }}
                table.safe-table td {{ padding: 6px 10px; border-bottom: 1px solid #1e293b; color: #f1f5f9; }}
                table.safe-table tr:hover {{ background-color: #1e293b88; }}
            </style>
            {html_table}
        </div>
        """
        st.markdown(styled_html, unsafe_allow_html=True)


def show_deploy_success_banner(robot_code: str, process_type: str = "Robot", dag_id: str = ""):
    """Muestra una notificación Toast flotante y un Banner DevOps profesional de confirmación."""
    actual_dag = dag_id or robot_code
    try:
        st.toast(f"✅ {process_type} {robot_code} desplegado y DAG activo en Airflow!", icon="🚀")
    except Exception:
        pass

    styled_banner = f"""
    <div style="background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 78, 59, 0.25)); border: 1px solid #10b981; border-left: 5px solid #10b981; border-radius: 8px; padding: 14px 18px; margin: 14px 0 18px 0; box-shadow: 0 4px 12px rgba(0,0,0,0.15);">
        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 1.5rem;">🟢</span>
                <div>
                    <div style="color: #34d399; font-weight: 700; font-size: 1.02rem; letter-spacing: 0.5px;">
                        DESPLIEGUE EXITOSO EN SERVIDOR DEV
                    </div>
                    <div style="color: #cbd5e1; font-size: 0.88rem; margin-top: 2px;">
                        Archivos sincronizados por SFTP y DAG <code>{actual_dag}</code> registrado en el worker de Airflow.
                    </div>
                </div>
            </div>
            <div style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981; padding: 4px 10px; border-radius: 6px; font-size: 0.78rem; color: #6ee7b7; font-family: monospace;">
                STATUS: DEPLOYED & READY
            </div>
        </div>
    </div>
    """
    st.markdown(styled_banner, unsafe_allow_html=True)



# ─── SIDEBAR ───────────────────────────────────────────────────
st.sidebar.title("🚀 Datax Studio")
st.sidebar.markdown("**Centro de Migración V1 ➔ V2**")
st.sidebar.markdown("---")

old_repo = st.sidebar.text_input("📁 Repositorio Antiguo (V1)", value=DEFAULT_OLD_REPO)
new_repo = st.sidebar.text_input("📁 Repositorio Nuevo (V2)", value=DEFAULT_NEW_REPO)

with st.sidebar.expander("🗄️ Configuración Base de Datos", expanded=False):
    db_host = st.text_input("Host", value=DEFAULT_DB_HOST)
    db_port = st.number_input("Puerto", value=DEFAULT_DB_PORT, step=1)
    db_user = st.text_input("Usuario", value=DEFAULT_DB_USER)
    db_pass = st.text_input("Contraseña", value=DEFAULT_DB_PASS, type="password")
    db_name = st.text_input("Base de datos", value=DEFAULT_DB_NAME)

engine = None
db_connected = False
try:
    engine = get_engine(db_host, db_port, db_user, db_pass, db_name)
    with engine.connect() as conn:
        db_connected = True
    st.sidebar.success("🟢 Conexión a platform_db Activa")
except Exception as e:
    engine = None
    db_connected = False
    st.sidebar.warning("🔴 Sin conexión a platform_db (Offline)")

with st.sidebar.expander("🐙 Conexión GitHub (Pasantes)", expanded=False):
    gh_repo = st.text_input("Repositorio (owner/repo):", value=DEFAULT_GITHUB_REPO, key="sidebar_gh_repo")
    gh_token = st.text_input(
        "GitHub Token (PAT):",
        value=st.session_state.get("github_token", DEFAULT_GITHUB_TOKEN),
        type="password",
        help="Token con permisos de lectura de repositorios para acceder al repositorio privado de los pasantes.",
        key="sidebar_gh_token"
    )
    st.session_state["github_repo"] = gh_repo
    st.session_state["github_token"] = gh_token

    col_ght1, col_ght2 = st.columns(2)
    with col_ght1:
        if st.button("🔌 Probar", key="btn_test_gh_conn"):
            if not gh_token:
                st.warning("Ingresa un token PAT.")
            else:
                with st.spinner("Conectando con GitHub..."):
                    ok_gh, msg_gh, _ = test_github_access(gh_token, gh_repo)
                if ok_gh:
                    st.success(msg_gh)
                else:
                    st.error(msg_gh)
    with col_ght2:
        if st.button("💾 Guardar .env", key="btn_save_gh_env"):
            try:
                env_path = os.path.join(CURRENT_DIR, ".env")
                env_lines = []
                if os.path.isfile(env_path):
                    with open(env_path, "r", encoding="utf-8") as fe:
                        for l in fe.readlines():
                            if not l.startswith("GITHUB_TOKEN=") and not l.startswith("GITHUB_REPO="):
                                env_lines.append(l)
                env_lines.append(f"GITHUB_REPO={gh_repo}\n")
                env_lines.append(f"GITHUB_TOKEN={gh_token}\n")
                with open(env_path, "w", encoding="utf-8") as fe:
                    fe.writelines(env_lines)
                st.success("Guardado en .env")
            except Exception as ex:
                st.error(f"Error: {ex}")


with st.sidebar.expander("🤖 Agente IA (Google Gemini)", expanded=False):
    gemini_api_key = st.text_input(
        "Gemini API Key:",
        value=st.session_state.get("gemini_api_key", DEFAULT_GEMINI_API_KEY),
        type="password",
        help="Obtén tu API key gratuita en: https://aistudio.google.com/app/apikey",
        key="sidebar_gemini_key"
    )
    st.session_state["gemini_api_key"] = gemini_api_key
    st.caption("ℹ️ *Si no se ingresa clave, el Agente usará el Motor Heurístico Avanzado de forma 100% offline.*")

mode = st.sidebar.radio("Navegación", [
    "📥 Robots de Descarga", 
    "🔄 Robots de Conversión", 
    "🚚 Robots de Migración",
    # "📦 Migración por Lote"  # 
])

# ─── PESTAÑA 1: DESCARGA ───────────────────────────────────────
if "Robots de Descarga" in mode:
    st.header("📥 Robots de Descarga (`D_...`)")
    st.caption("Estandarización V1 ➔ V2 o Validación, Pruebas y Despliegue de robots nuevos desarrollados en V2.")

    dl_flow_mode = st.radio(
        "Flujo de trabajo para Descarga:",
        ["🔄 Migrar desde Repositorio V1 (Legado)", "✨ Código Nuevo / Ya Desarrollado en V2"],
        horizontal=True,
        key="dl_flow_mode"
    )

    if dl_flow_mode.startswith("🔄"):
        robots = scan_old_download_robots(old_repo)
        if not robots:
            st.warning(f"No se encontraron robots de descarga en `{old_repo}/models/download`.")
        else:
            robot_codes = [r["code"] for r in robots]
            selected_code = st.selectbox("Selecciona el robot a migrar:", robot_codes, index=0)
            selected_robot = next(r for r in robots if r["code"] == selected_code)

            # Estado en BD y en V2
            new_robot_path = os.path.join(new_repo, "models", "download", selected_code, f"{selected_code}.py")
            new_dag_path = os.path.join(new_repo, "dags", "download", f"{selected_code}.py")
            already_migrated = os.path.isfile(new_robot_path)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Código Robot", selected_code)
            col2.metric("Estado en Repo V2", "🟢 Migrado" if already_migrated else "🔴 Pendiente")

            db_info = get_download_db_info(selected_code, engine) if db_connected else None
            if db_info and "error" not in db_info:
                col3.metric("Tipo Descarga", db_info.get("download_type", "No definido"))
                col4.metric("Última Descarga", str(db_info.get("updated_to", "-")))
                st.info(f"🏛️ **{db_info.get('name')}** | URL: {db_info.get('main_url')} | Frecuencia: `{db_info.get('schedule_interval')}`")
            else:
                col3.metric("Tipo Descarga", "Desconocido")
                col4.metric("Última Descarga", "-")

            # Lectura y Refactor
            raw_code = ""
            refactored_code = ""
            if selected_robot["script_file"] and os.path.isfile(selected_robot["script_file"]):
                with open(selected_robot["script_file"], "r", encoding="utf-8", errors="ignore") as f:
                    raw_code = f.read()
                dl_type = db_info.get("download_type", "") if db_info else ""
                refactored_code = refactor_download_code(raw_code, selected_code, dl_type)

            tab_code, tab_action, tab_deploy = st.tabs(["📄 Comparativa de Código (V1 vs V2)", "⚡ Ejecutar Migración", "🚀 Despliegue al Servidor"])

            with tab_code:
                c1, c2 = st.columns(2)
                with c1:
                    st.subheader("Código Original (V1)")
                    st.code(raw_code, language="python")
                with c2:
                    st.subheader("Código Estandarizado (V2)")
                    st.code(refactored_code, language="python")

            # Gestión de BD para el robot de descarga
            if db_connected:
                with st.expander(f"🛠️ Gestión de Base de Datos para `{selected_code}`", expanded=False):
                    c_db1, c_db2 = st.columns([3, 1])
                    with c_db1:
                        new_db_dt = st.text_input("Nueva fecha 'updated_to' (o 'NULL' para resetear)", value="2024-01-01", key=f"db_dt_{selected_code}")
                    with c_db2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Actualizar en BD", key=f"btn_upd_db_{selected_code}", use_container_width=True):
                            upd_res = reset_file_updated_to_in_db(selected_code, new_db_dt, engine)
                            if upd_res["success"]:
                                st.success(upd_res["message"])
                                st.rerun()
                            else:
                                st.error(upd_res["message"])

            with tab_action:
                st.subheader("Opciones de Migración")
                c_opt1, c_opt2 = st.columns(2)
                with c_opt1:
                    skip_test = st.checkbox("Omitir test unitario (migrar solo archivos y DAG)", value=False)
                with c_opt2:
                    generate_dag = st.checkbox("Generar DAG de Airflow en dags/download", value=True, help="Genera automáticamente el DAG en dags/download/<CODE>.py")
                skip_dag = not generate_dag

                # Selector inteligente de fechas de corte
                st.markdown("**📅 Fecha de corte para la prueba (`UPDATED_TO`):**")
                st.caption("ℹ️ El test exige encontrar al menos un archivo posterior a esta fecha. Selecciona una fecha anterior a la última publicación para asegurar que el scraper pase.")
                
                db_date_val = str(db_info.get("updated_to", "")) if db_info and db_info.get("updated_to") else "2024-01-01"
                
                c_dt1, c_dt2, c_dt3 = st.columns(3)
                with c_dt1:
                    if st.button("⏪ 1 año antes (Recomendado)", key=f"dt_1y_{selected_code}", use_container_width=True):
                        st.session_state[f"test_date_{selected_code}"] = "2024-01-01"
                        st.rerun()
                with c_dt2:
                    if st.button("📜 Histórico (2020-01-01)", key=f"dt_hist_{selected_code}", use_container_width=True):
                        st.session_state[f"test_date_{selected_code}"] = "2020-01-01"
                        st.rerun()
                with c_dt3:
                    if st.button("📅 Fecha en BD", key=f"dt_db_{selected_code}", use_container_width=True):
                        st.session_state[f"test_date_{selected_code}"] = db_date_val
                        st.rerun()

                current_test_date = st.session_state.get(f"test_date_{selected_code}", "2024-01-01")
                test_date = st.text_input("Fecha seleccionada para la prueba:", value=current_test_date, key=f"input_dt_{selected_code}")

                col_btn1, col_btn2 = st.columns(2)
                if col_btn1.button("🧪 Simulación (Dry-Run)", use_container_width=True):
                    st.info(f"Simulación exitosa: {selected_code} listo para migrarse a `{new_robot_path}`.")

                if col_btn2.button("🚀 Migrar Robot y Ejecutar Prueba", type="primary", use_container_width=True):
                    with st.spinner("Procesando migración, ejecutando pruebas y creando DAG..."):
                        res = apply_download_migration(
                            code=selected_code,
                            source_file=selected_robot["script_file"],
                            new_repo_path=new_repo,
                            download_type=db_info.get("download_type", "") if db_info else "",
                            skip_test=skip_test,
                            skip_dag=skip_dag,
                            test_updated_to=test_date
                        )
                        st.session_state[f"last_dl_res_{selected_code}"] = res
                        if res["success"]:
                            st.success(f"✨ ¡Robot {selected_code} migrado exitosamente a la Plataforma V2!")
                        else:
                            st.error(f"⚠️ Ocurrieron advertencias o fallos durante la migración.")

                # Mostrar resultados guardados en session_state para permitir rescate
                last_res = st.session_state.get(f"last_dl_res_{selected_code}")
                if last_res:
                    if last_res.get("diagnostics"):
                        st.markdown("### 🩺 Diagnóstico Inteligente de Fallos")
                        for d in last_res["diagnostics"]:
                            st.warning(d)

                    if not last_res["success"] and last_res.get("can_force_dag"):
                        st.markdown("---")
                        st.info("💡 El archivo `.py` ya fue guardado en `models/download`. Si el fallo se debe a que el portal web no tiene archivos nuevos hoy o requieres desplegarlo, puedes generar el DAG directamente:")
                        if st.button("🚀 Forzar Generación de DAG (Omitir fallo de fecha)", key=f"force_dag_{selected_code}", type="secondary", use_container_width=True):
                            with st.spinner("Generando DAG en dags/download..."):
                                f_res = generate_download_dag_only(selected_code, new_repo)
                                if f_res["success"]:
                                    st.success(f_res["message"])
                                else:
                                    st.error(f_res["message"])

                    with st.expander("📋 Ver logs completos de la migración", expanded=not last_res["success"]):
                        for l in last_res["logs"]:
                            st.write(l)

            with tab_deploy:
                st.subheader(f"Despliegue al Servidor Remoto para `{selected_code}`")
                st.caption(f"Sube `{selected_code}` al servidor y ejecuta el generador de DAGs en Docker.")
                col_sd1, col_sd2 = st.columns(2)
                with col_sd1:
                    dep_v1_host = st.text_input("Host Servidor:", value=DEFAULT_SSH_HOST, key=f"dep_v1_dl_host_{selected_code}")
                    dep_v1_user = st.text_input("Usuario SSH:", value=DEFAULT_SSH_USER, key=f"dep_v1_dl_user_{selected_code}")
                with col_sd2:
                    dep_v1_port = st.number_input("Puerto SSH:", value=DEFAULT_SSH_PORT, key=f"dep_v1_dl_port_{selected_code}")
                    dep_v1_pass = st.text_input("Contraseña SSH:", value=DEFAULT_SSH_PASS, type="password", key=f"dep_v1_dl_pass_{selected_code}")

                col_con1, col_con2 = st.columns([1, 3])
                with col_con1:
                    if st.button("🔌 Probar Conexión", key=f"btn_test_ssh_v1_{selected_code}"):
                        if not dep_v1_pass:
                            st.warning("Ingresa la contraseña de SSH.")
                        else:
                            ok_c, msg_c = test_connection(dep_v1_host, int(dep_v1_port), dep_v1_user, dep_v1_pass)
                            if ok_c: st.success(msg_c)
                            else: st.error(msg_c)

                gen_dag_srv_v1 = st.checkbox("Generar DAG de descarga en Docker (Airflow)", value=True, key=f"chk_v1_dag_srv_{selected_code}")

                if st.button("🚀 Subir al Servidor y Desplegar Robot", type="primary", use_container_width=True, key=f"btn_v1_dep_srv_{selected_code}"):
                    if not dep_v1_pass:
                        st.error("Introduce la contraseña de SSH.")
                    elif not already_migrated:
                        st.error(f"El robot aún no ha sido migrado a `{new_robot_path}`. Ejecuta primero la migración en la pestaña anterior.")
                    else:
                        with st.spinner("Transfiriendo archivos vía SFTP y ejecutando generador en Docker..."):
                            local_dl_folder = os.path.join(new_repo, "models", "download", selected_code)
                            res_dep = deploy_robot_to_server(
                                host=dep_v1_host,
                                port=int(dep_v1_port),
                                username=dep_v1_user,
                                password=dep_v1_pass,
                                remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                                process_type="download",
                                robot_code=selected_code,
                                local_dir=local_dl_folder,
                                generate_dag=gen_dag_srv_v1
                            )
                            if res_dep["success"]:
                                show_deploy_success_banner(selected_code, process_type="Robot de Descarga")
                            else:
                                st.error("⚠️ Ocurrieron errores durante el despliegue.")
                            for l in res_dep["logs"]:
                                st.write(l)

                st.markdown("---")
                st.markdown("#### ⚡ Disparar DAG en Airflow (Trigger Remoto)")
                if st.button(f"🎯 Disparar DAG `{selected_code}` en Airflow", key=f"btn_v1_trig_dl_{selected_code}"):
                    if not dep_v1_pass:
                        st.error("Introduce la contraseña de SSH.")
                    else:
                        with st.spinner(f"Disparando DAG {selected_code} en Airflow..."):
                            trig_res = trigger_dag_on_server(
                                host=dep_v1_host,
                                port=int(dep_v1_port),
                                username=dep_v1_user,
                                password=dep_v1_pass,
                                remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                                dag_id=selected_code,
                                conf={}
                            )
                            if trig_res["success"]:
                                st.success(f"🎉 DAG `{selected_code}` disparado exitosamente en Airflow!")
                            else:
                                st.warning("El comando terminó con advertencias o error.")
                            with st.expander("Ver salida detallada de Airflow", expanded=True):
                                st.code(trig_res["output"] or "Sin salida")

    else:
        # ─── FLUJO CÓDIGO NUEVO / YA EN V2 ───────────────────────────
        v2_dl_robots = scan_v2_download_robots(new_repo)
        
        sel_v2_mode = st.radio(
            "Modo de selección de robot V2:",
            ["📁 Seleccionar de robots en Repo V2 (models/download)", "✍️ Ingresar código manualmente (GitHub / Nuevo)"],
            horizontal=True,
            key="sel_v2_dl_mode"
        )

        if sel_v2_mode.startswith("📁") and v2_dl_robots:
            v2_codes = [r["code"] for r in v2_dl_robots]
            selected_code = st.selectbox("Robot de Descarga detectado en V2:", v2_codes, index=0, key="sel_code_v2_dl")
            current_robot_data = next((r for r in v2_dl_robots if r["code"] == selected_code), None)
        else:
            if sel_v2_mode.startswith("📁") and not v2_dl_robots:
                st.info("No se encontraron carpetas de robots en `models/download` del repositorio V2 aún. Puedes ingresar el código a continuación:")
            selected_code = st.text_input("Código del robot de descarga (ej. D_BO_000000017):", value="D_BO_000000017", key="inp_code_v2_dl").strip()
            current_robot_data = next((r for r in v2_dl_robots if r["code"] == selected_code), None)

        # Estado en Repo V2 y en BD
        new_robot_path = os.path.join(new_repo, "models", "download", selected_code, f"{selected_code}.py")
        new_dag_path = os.path.join(new_repo, "dags", "download", f"{selected_code}.py")
        script_exists = os.path.isfile(new_robot_path)
        dag_exists = os.path.isfile(new_dag_path)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Código Robot", selected_code)
        col2.metric("Script V2", "🟢 Presente" if script_exists else "🔴 Pendiente")
        col3.metric("DAG Airflow", "🟢 Creado" if dag_exists else "🔴 Pendiente")

        db_info = get_download_db_info(selected_code, engine) if db_connected else None
        if db_info and "error" not in db_info:
            col4.metric("Última Descarga", str(db_info.get("updated_to", "-")))
            st.info(f"🏛️ **{db_info.get('name')}** | Tipo: `{db_info.get('download_type', 'No definido')}` | URL: {db_info.get('main_url')} | Frecuencia: `{db_info.get('schedule_interval')}`")
        else:
            col4.metric("Última Descarga", "-")
            st.caption("ℹ️ Sin registro activo en la tabla `file` de `platform_db` (Offline o robot nuevo).")

        tab_v2_code, tab_v2_test, tab_v2_deploy = st.tabs([
            "💻 1. Código del Robot (V2)",
            "🧪 2. Pruebas Unitarias & DAG",
            "🚀 3. Despliegue al Servidor"
        ])

        with tab_v2_code:
            st.subheader(f"Gestión de Código V2 para `{selected_code}`")
            src_options = [
                "📁 Archivo local en Repo V2 (models/download)",
                "🐙 Cargar desde Pull Request de GitHub (Pasantes)",
                "📤 Subir archivo .py (descargado)",
                "📋 Pegar código del desarrollador directamente"
            ]
            chosen_src = st.radio("Origen del código:", src_options, index=0 if script_exists else 3, horizontal=True, key=f"src_v2_{selected_code}")

            raw_code_v2 = ""
            if chosen_src.startswith("📁"):
                if script_exists:
                    with open(new_robot_path, "r", encoding="utf-8", errors="ignore") as f:
                        raw_code_v2 = f.read()
                else:
                    raw_code_v2 = f"# No existe aún el archivo: models/download/{selected_code}/{selected_code}.py"

            elif chosen_src.startswith("🐙"):
                active_gh_token = st.session_state.get("github_token", DEFAULT_GITHUB_TOKEN)
                active_gh_repo = st.session_state.get("github_repo", DEFAULT_GITHUB_REPO)
                if not active_gh_token:
                    st.warning("Configura tu GitHub PAT en la barra lateral para consultar PRs.")
                else:
                    pr_q = st.text_input("Filtrar PRs por código:", value=selected_code, key=f"pr_q_dl_{selected_code}")
                    with st.spinner("Consultando GitHub..."):
                        prs_found = list_pull_requests(active_gh_token, active_gh_repo, state="open", search_query=pr_q)
                    if prs_found:
                        pr_labels = [f"PR #{p['number']}: {p['title']} (@{p['author']})" for p in prs_found]
                        sel_pr_idx = st.selectbox("Selecciona PR:", range(len(pr_labels)), format_func=lambda i: pr_labels[i], key=f"sel_pr_dl_{selected_code}")
                        chosen_pr = prs_found[sel_pr_idx]
                        pr_files = get_pr_files(active_gh_token, active_gh_repo, chosen_pr["number"])
                        py_files = [f for f in pr_files if f["is_py"]]
                        if py_files:
                            py_sel_name = st.selectbox("Archivo en PR:", [f["filename"] for f in py_files], key=f"py_pr_dl_{selected_code}")
                            chosen_py = next(f for f in py_files if f["filename"] == py_sel_name)
                            if st.button("📥 Cargar al Editor", key=f"btn_load_pr_dl_{selected_code}"):
                                dl_bytes = download_github_file(active_gh_token, chosen_py["raw_url"], chosen_py["contents_url"])
                                if dl_bytes:
                                    raw_code_v2 = dl_bytes.decode("utf-8", errors="ignore")
                                    st.session_state[f"gh_code_dl_{selected_code}"] = raw_code_v2
                                    st.success("Código descargado del PR.")
                            if f"gh_code_dl_{selected_code}" in st.session_state:
                                raw_code_v2 = st.session_state[f"gh_code_dl_{selected_code}"]

            elif chosen_src.startswith("📤"):
                uploaded_py = st.file_uploader("Subir script .py:", type=["py"], key=f"up_py_dl_{selected_code}")
                if uploaded_py:
                    raw_code_v2 = uploaded_py.getvalue().decode("utf-8", errors="ignore")
                    st.success("Archivo subido con éxito.")

            elif chosen_src.startswith("📋"):
                init_val = ""
                if script_exists:
                    with open(new_robot_path, "r", encoding="utf-8", errors="ignore") as f:
                        init_val = f.read()
                raw_code_v2 = st.text_area("Pega el código Python desarrollado en V2:", value=init_val, height=280, key=f"ta_code_dl_{selected_code}")

            st.markdown("**Visualizador / Editor de Código V2:**")
            st.code(raw_code_v2 if raw_code_v2 else "# Esperando código...", language="python")

            c_sv1, c_sv2 = st.columns([2, 1])
            with c_sv1:
                chk_ensure_compat = st.checkbox("Asegurar alias de compatibilidad (`Executor_<CODE> = <CODE>`, `Robot = <CODE>`)", value=True, key=f"chk_compat_dl_{selected_code}")
            with c_sv2:
                if st.button("💾 Guardar en models/download/ (V2)", type="primary", use_container_width=True, key=f"btn_save_v2_dl_{selected_code}"):
                    if not raw_code_v2.strip() or raw_code_v2.startswith("# No existe aún"):
                        st.error("No hay código válido para guardar.")
                    else:
                        final_to_save = raw_code_v2
                        if chk_ensure_compat and f"Executor_{selected_code}" not in final_to_save:
                            final_to_save = final_to_save.rstrip() + f"\n\nExecutor_{selected_code} = {selected_code}\nRobot = {selected_code}\n"
                        ok_sv, sv_path = save_v2_download_code(selected_code, new_repo, final_to_save)
                        if ok_sv:
                            st.success(f"✨ Guardado exitosamente en: `{sv_path}`")
                            st.rerun()

        with tab_v2_test:
            st.subheader("Pruebas Unitarias & Generación de DAG")
            st.caption("Ejecuta el test unitario de scraping sobre el archivo local ya presente en `models/download/`.")

            if not script_exists:
                st.warning(f"⚠️ El archivo `{new_robot_path}` no existe aún. Guárdalo primero en la pestaña 1.")
            else:
                db_date_val = str(db_info.get("updated_to", "")) if db_info and db_info.get("updated_to") else "2024-01-01"
                st.markdown("**📅 Fecha de corte para la prueba (`UPDATED_TO`):**")
                c_dt1, c_dt2, c_dt3 = st.columns(3)
                with c_dt1:
                    if st.button("⏪ 1 año antes (Recomendado)", key=f"v2_dt_1y_{selected_code}", use_container_width=True):
                        st.session_state[f"v2_test_date_{selected_code}"] = "2024-01-01"
                        st.rerun()
                with c_dt2:
                    if st.button("📜 Histórico (2020-01-01)", key=f"v2_dt_hist_{selected_code}", use_container_width=True):
                        st.session_state[f"v2_test_date_{selected_code}"] = "2020-01-01"
                        st.rerun()
                with c_dt3:
                    if st.button("📅 Fecha en BD", key=f"v2_dt_db_{selected_code}", use_container_width=True):
                        st.session_state[f"v2_test_date_{selected_code}"] = db_date_val
                        st.rerun()

                cur_v2_dt = st.session_state.get(f"v2_test_date_{selected_code}", "2024-01-01")
                test_date_v2 = st.text_input("Fecha seleccionada:", value=cur_v2_dt, key=f"v2_inp_dt_{selected_code}")

                col_tbtn1, col_tbtn2 = st.columns(2)
                with col_tbtn1:
                    if st.button("🧪 Ejecutar Prueba Unitaria en V2", type="primary", use_container_width=True, key=f"btn_test_v2_dl_{selected_code}"):
                        dl_type_str = db_info.get("download_type", "") if db_info else ""
                        with st.spinner(f"Ejecutando prueba unitaria de {selected_code} con fecha {test_date_v2}..."):
                            t_res = test_download_robot_v2(selected_code, new_repo, dl_type_str, test_date_v2)
                            st.session_state[f"last_v2_test_{selected_code}"] = t_res
                            if t_res["success"]:
                                st.success(f"🎉 ¡Prueba unitaria APROBADA (OK) para `{selected_code}`!")
                            else:
                                st.error("⚠️ La prueba unitaria falló.")

                with col_tbtn2:
                    if st.button("🚀 Generar DAG de Descarga en Airflow", use_container_width=True, key=f"btn_dag_v2_dl_{selected_code}"):
                        with st.spinner("Generando DAG en dags/download..."):
                            dag_res = generate_download_dag_only(selected_code, new_repo)
                            if dag_res["success"]:
                                st.success(dag_res["message"])
                                st.rerun()
                            else:
                                st.error(dag_res["message"])

                last_t = st.session_state.get(f"last_v2_test_{selected_code}")
                if last_t:
                    if last_t.get("diagnostics"):
                        st.markdown("### 🩺 Diagnóstico Inteligente de Fallos")
                        for d in last_t["diagnostics"]:
                            st.warning(d)
                    with st.expander("📋 Ver logs completos de la prueba", expanded=not last_t["success"]):
                        for l in last_t["logs"]:
                            st.write(l)

            # Gestión de BD
            if db_connected:
                with st.expander(f"🛠️ Gestión de Base de Datos para `{selected_code}`", expanded=False):
                    c_db1, c_db2 = st.columns([3, 1])
                    with c_db1:
                        new_db_dt_v2 = st.text_input("Nueva fecha 'updated_to' (o 'NULL' para resetear)", value="2024-01-01", key=f"v2_db_dt_{selected_code}")
                    with c_db2:
                        st.write("")
                        st.write("")
                        if st.button("💾 Actualizar en BD", key=f"v2_btn_upd_db_{selected_code}", use_container_width=True):
                            upd_res = reset_file_updated_to_in_db(selected_code, new_db_dt_v2, engine)
                            if upd_res["success"]:
                                st.success(upd_res["message"])
                                st.rerun()
                            else:
                                st.error(upd_res["message"])

        with tab_v2_deploy:
            st.subheader(f"Despliegue al Servidor Remoto para `{selected_code}`")
            col_sd1, col_sd2 = st.columns(2)
            with col_sd1:
                dep_dl_host = st.text_input("Host Servidor:", value=DEFAULT_SSH_HOST, key=f"dep_dl_host_{selected_code}")
                dep_dl_user = st.text_input("Usuario SSH:", value=DEFAULT_SSH_USER, key=f"dep_dl_user_{selected_code}")
            with col_sd2:
                dep_dl_port = st.number_input("Puerto SSH:", value=DEFAULT_SSH_PORT, key=f"dep_dl_port_{selected_code}")
                dep_dl_pass = st.text_input("Contraseña SSH:", value=DEFAULT_SSH_PASS, type="password", key=f"dep_dl_pass_{selected_code}")

            col_con_v2_1, col_con_v2_2 = st.columns([1, 3])
            with col_con_v2_1:
                if st.button("🔌 Probar Conexión", key=f"btn_test_ssh_v2_{selected_code}"):
                    if not dep_dl_pass:
                        st.warning("Ingresa la contraseña de SSH.")
                    else:
                        ok_c, msg_c = test_connection(dep_dl_host, int(dep_dl_port), dep_dl_user, dep_dl_pass)
                        if ok_c: st.success(msg_c)
                        else: st.error(msg_c)

            gen_dag_srv = st.checkbox("Generar DAG de descarga en Docker (Airflow)", value=True, key=f"chk_gen_dag_srv_{selected_code}")

            if st.button("🚀 Subir al Servidor y Desplegar Robot de Descarga", type="primary", use_container_width=True, key=f"btn_dep_srv_dl_{selected_code}"):
                if not dep_dl_pass:
                    st.error("Introduce la contraseña de SSH.")
                elif not script_exists:
                    st.error(f"No existe el archivo `{new_robot_path}` para transferir.")
                else:
                    with st.spinner("Transfiriendo archivos vía SFTP y ejecutando generador en Docker..."):
                        local_dl_folder = os.path.join(new_repo, "models", "download", selected_code)
                        res_dep = deploy_robot_to_server(
                            host=dep_dl_host,
                            port=int(dep_dl_port),
                            username=dep_dl_user,
                            password=dep_dl_pass,
                            remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                            process_type="download",
                            robot_code=selected_code,
                            local_dir=local_dl_folder,
                            generate_dag=gen_dag_srv
                        )
                        if res_dep["success"]:
                            show_deploy_success_banner(selected_code, process_type="Robot de Descarga")
                        else:
                            st.error("⚠️ Ocurrieron errores durante el despliegue.")
                        for l in res_dep["logs"]:
                            st.write(l)

            st.markdown("---")
            st.markdown("#### ⚡ Disparar DAG en Airflow (Trigger Remoto)")
            if st.button(f"🎯 Disparar DAG `{selected_code}` en Airflow", key=f"btn_v2_trig_dl_{selected_code}"):
                if not dep_dl_pass:
                    st.error("Introduce la contraseña de SSH.")
                else:
                    with st.spinner(f"Disparando DAG {selected_code} en Airflow..."):
                        trig_res = trigger_dag_on_server(
                            host=dep_dl_host,
                            port=int(dep_dl_port),
                            username=dep_dl_user,
                            password=dep_dl_pass,
                            remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                            dag_id=selected_code,
                            conf={}
                        )
                        if trig_res["success"]:
                            st.success(f"🎉 DAG `{selected_code}` disparado exitosamente en Airflow!")
                        else:
                            st.warning("El comando terminó con advertencias o error.")
                        with st.expander("Ver salida detallada de Airflow", expanded=True):
                            st.code(trig_res["output"] or "Sin salida")

# ─── PESTAÑA 2: CONVERSIÓN (ASISTENTE POR PASOS) ───────────────
elif "Robots de Conversión" in mode:
    st.header("🔄 Asistente por Pasos: Robots de Conversión (`C_...`)")
    st.caption("Flujo guiado y seguro de 5 pasos para extraer, auditar datos (NVx/fecha/valor), configurar plantilla y desplegar al servidor.")

    conv_flow_mode = st.radio(
        "Flujo de trabajo para Conversión:",
        ["🔄 Migrar desde Repositorio V1 (Legado)", "✨ Código Nuevo / Ya Desarrollado en V2"],
        horizontal=True,
        key="conv_flow_mode"
    )

    is_v2_flow = conv_flow_mode.startswith("✨")
    if is_v2_flow:
        families = scan_v2_conversion_families(new_repo)
        scan_option_label = "📁 Seleccionar de repositorio nuevo V2 (models/conversion)"
    else:
        families = scan_old_conversion_families(old_repo)
        scan_option_label = "📁 Seleccionar de repositorio antiguo V1 escaneado"

    # Selección de Modo: Ingresar código directo (GitHub/Jira/Nuevo) o Explorar repositorio escaneado
    sel_mode = st.radio(
        "Modo de selección de reporte:",
        ["✍️ Ingresar código del reporte manualmente (GitHub / Jira / Nuevo)", scan_option_label],
        horizontal=True,
        key=f"conv_sel_mode_{'v2' if is_v2_flow else 'v1'}"
    )

    selected_fam = {"parent_code": "", "folder": "", "sub_reports": [], "samples": [], "sqlites": []}

    if sel_mode.startswith("✍️"):
        col_m1, col_m2 = st.columns([1, 1])
        with col_m1:
            rep_input = st.text_input("Código del reporte (ej. D_BO_000000017_01):", value="D_BO_000000017_01").strip()
            rep_choice = rep_input
        with col_m2:
            # Deducir código padre C_BO_...
            parts = rep_input.split("_")
            if len(parts) >= 3:
                auto_parent = f"C_{parts[1]}_{parts[2]}"
            else:
                auto_parent = rep_input.replace("D_", "C_")
            selected_parent = st.text_input("Código de la familia (deducido):", value=auto_parent).strip()

        # Buscar si existe en families escaneadas para aprovechar muestras o subreportes
        matched_fam = next((f for f in families if f["parent_code"] == selected_parent), None)
        if matched_fam:
            selected_fam = matched_fam
        else:
            selected_fam = {
                "parent_code": selected_parent,
                "folder": os.path.join(new_repo, "models", "conversion", selected_parent),
                "sub_reports": [{"code": rep_choice, "file": ""}],
                "samples": [],
                "sqlites": []
            }

    else:
        if not families:
            repo_label = "repositorio nuevo V2" if is_v2_flow else "repositorio antiguo V1"
            st.warning(f"No se encontraron familias de conversión en el {repo_label}.")
            selected_parent = "C_BO_000000017"
            rep_choice = "D_BO_000000017_01"
        else:
            fam_codes = [f["parent_code"] for f in families]
            col_fam1, col_fam2 = st.columns([1, 1])
            with col_fam1:
                def_idx = fam_codes.index("C_BO_000000017") if "C_BO_000000017" in fam_codes else 0
                selected_parent = st.selectbox("1. Selecciona la familia de conversión:", fam_codes, index=def_idx)
                selected_fam = next(f for f in families if f["parent_code"] == selected_parent)
            with col_fam2:
                sub_rep_list = [r["code"] for r in selected_fam["sub_reports"]]
                if not sub_rep_list:
                    sub_rep_list = [selected_parent]
                rep_choice = st.selectbox("2. Selecciona el sub-reporte a migrar/probar:", sub_rep_list, index=0)

    # Tabs de los 5 pasos
    conv_tab1, conv_tab2, conv_tab3, conv_tab4, conv_tab5 = st.tabs([
        "Paso 1: Archivo y Código",
        "Paso 2: Pruebas (Extracción / Reemplazos)",
        "Paso 3: Verificación SQL (Datos / Reemplazos)",
        "Paso 4: Plantilla SQLite (columns_to_review)",
        "Paso 5: Despliegue al Servidor"
    ])

    # ─────────────────────────────────────────────────────────────
    # PASO 1: ARCHIVO Y CÓDIGO
    # ─────────────────────────────────────────────────────────────
    with conv_tab1:
        st.subheader("Paso 1: Preparación de Archivos y Estandarización de Código")
        
        # Consultar metadatos en platform_db
        db_info_conv = get_conversion_db_info(rep_choice, engine)
        if db_info_conv and not db_info_conv.get("error"):
            st.info(f"📋 **Metadatos en BD:** Nombre: *{db_info_conv.get('name', 'N/A')}* | Página: `{db_info_conv.get('page_number', 'N/A')}` | Storage Table: `{db_info_conv.get('storage_table', 'N/A')}` | Replacement Table: `{db_info_conv.get('replacement_table', 'N/A')}`")
        elif db_info_conv and db_info_conv.get("error"):
            st.warning(f"Aviso BD: {db_info_conv['error']}")
        else:
            st.info(f"ℹ️ El reporte `{rep_choice}` aún no tiene registro en la tabla `report` de `platform_db`.")

        # Gestión del Archivo de Muestra
        st.markdown("#### 📁 Archivo de Muestra para Pruebas")
        detected_samples = detect_available_samples(selected_parent, old_repo, new_repo)
        
        sample_file_to_use = None
        if detected_samples:
            sample_names = [os.path.basename(s) for s in detected_samples]
            sample_idx = st.selectbox(
                "Archivo de muestra detectado en la carpeta:",
                range(len(sample_names)),
                format_func=lambda i: f"📄 {sample_names[i]} ({detected_samples[i]})"
            )
            sample_file_to_use = detected_samples[sample_idx]
            st.success(f"Archivo de muestra activo: `{sample_file_to_use}`")
        else:
            st.warning("⚠️ No se encontró ningún archivo de muestra (.pdf, .xlsx, .xls, .csv) para este modelo.")

        uploaded_sample = st.file_uploader(
            "Opcional: Subir un nuevo archivo de muestra (.pdf, .xlsx, .xls, .csv):",
            type=["pdf", "xlsx", "xls", "csv"],
            key=f"sample_uploader_{rep_choice}"
        )
        if uploaded_sample is not None:
            saved_sample_path = save_uploaded_sample_file(new_repo, selected_parent, uploaded_sample)
            sample_file_to_use = saved_sample_path
            st.success(f"✅ Archivo de muestra guardado en: `{saved_sample_path}`")

        st.session_state[f"sample_file_{rep_choice}"] = sample_file_to_use

        # Código original vs V2
        st.markdown("#### 💻 Origen del Código del Robot")
        source_options = [
            "🐙 Cargar desde Pull Request de GitHub (Pasantes)",
            "📋 Pegar código del freelancer directamente",
            "📤 Subir archivo .py (descargado de GitHub)",
            "📁 Archivo detectado en la carpeta / repositorio local"
        ]
        default_src_idx = 0 if sel_mode.startswith("✍️") else 3
        source_mode = st.radio(
            "¿De dónde deseas obtener el código de este robot?",
            source_options,
            index=default_src_idx,
            horizontal=True,
            key=f"src_mode_{rep_choice}"
        )

        raw_conv_code = ""
        chosen_rep_data = next((r for r in selected_fam["sub_reports"] if r["code"] == rep_choice), None)

        if source_mode == "🐙 Cargar desde Pull Request de GitHub (Pasantes)":
            active_gh_token = st.session_state.get("github_token", DEFAULT_GITHUB_TOKEN)
            active_gh_repo = st.session_state.get("github_repo", DEFAULT_GITHUB_REPO)

            if not active_gh_token:
                st.warning("⚠️ No se ha configurado un GitHub Token (PAT). Por favor ingrésalo en la barra lateral en la sección '🐙 Conexión GitHub (Pasantes)'.")
            else:
                col_pr1, col_pr2 = st.columns([3, 1])
                with col_pr1:
                    pr_search_q = st.text_input("Filtrar Pull Requests por código / palabra clave:", value=rep_choice, key=f"pr_q_{rep_choice}")
                with col_pr2:
                    st.write("")
                    st.write("")
                    st.button("🔄 Refrescar PRs", key=f"btn_ref_prs_{rep_choice}")

                with st.spinner(f"Consultando Pull Requests en {active_gh_repo}..."):
                    prs_found = list_pull_requests(active_gh_token, active_gh_repo, state="open", search_query=pr_search_q)

                if not prs_found:
                    st.info(f"No se encontraron Pull Requests abiertos que coincidan con '{pr_search_q}' en `{active_gh_repo}`.")
                else:
                    pr_labels = []
                    for p in prs_found:
                        prefix = "⭐ Coincide: " if p["matched"] else ""
                        pr_labels.append(f"{prefix}PR #{p['number']}: {p['title']} (por @{p['author']})")

                    sel_pr_idx = st.selectbox(
                        "Selecciona el Pull Request del pasante:",
                        range(len(pr_labels)),
                        format_func=lambda i: pr_labels[i],
                        key=f"sel_pr_item_{rep_choice}"
                    )
                    chosen_pr = prs_found[sel_pr_idx]
                    st.caption(f"🌿 Rama: `{chosen_pr['branch']}` | 🔗 Enlace: [{chosen_pr['title']}]({chosen_pr['html_url']})")

                    # Archivos en el PR
                    with st.spinner(f"Obteniendo archivos del PR #{chosen_pr['number']}..."):
                        pr_files = get_pr_files(active_gh_token, active_gh_repo, chosen_pr["number"])

                    py_files = [f for f in pr_files if f["is_py"]]
                    sample_files = [f for f in pr_files if f["is_sample"]]

                    if py_files:
                        py_names = [f["filename"] for f in py_files]
                        best_idx = 0
                        for idx_p, pf in enumerate(py_files):
                            if rep_choice.lower() in pf["filename"].lower() or selected_parent.lower() in pf["filename"].lower():
                                best_idx = idx_p
                                break

                        col_sel_py, col_btn_load = st.columns([3, 1])
                        with col_sel_py:
                            sel_py_file = st.selectbox("Script .py en el PR:", py_names, index=best_idx, key=f"py_sel_{chosen_pr['number']}_{rep_choice}")
                        with col_btn_load:
                            st.write("")
                            st.write("")
                            load_py_clicked = st.button("📥 Cargar al Editor", type="primary", key=f"btn_dl_code_{chosen_pr['number']}")

                        chosen_py_obj = next(f for f in py_files if f["filename"] == sel_py_file)

                        # Auto-cargar si se presionó el botón o si ya estaba cargado en session_state
                        if load_py_clicked:
                            with st.spinner("Descargando script desde GitHub..."):
                                downloaded_bytes = download_github_file(active_gh_token, chosen_py_obj["raw_url"], chosen_py_obj["contents_url"])
                                if downloaded_bytes:
                                    raw_conv_code = downloaded_bytes.decode("utf-8", errors="ignore")
                                    st.session_state[f"gh_code_{rep_choice}"] = raw_conv_code
                                    st.success(f"✅ Código de `{os.path.basename(sel_py_file)}` cargado exitosamente.")
                                else:
                                    st.error("❌ No se pudo descargar el archivo de GitHub.")
                        elif f"gh_code_{rep_choice}" in st.session_state:
                            raw_conv_code = st.session_state[f"gh_code_{rep_choice}"]
                        else:
                            st.info(f"Haz clic en '📥 Cargar al Editor' para traer el código de `{os.path.basename(sel_py_file)}`.")
                    else:
                        st.warning(f"No se detectaron scripts `.py` en el PR #{chosen_pr['number']}.")

                    # Detección y descarga de muestras si existen en el PR
                    if sample_files:
                        st.markdown("##### 📁 Archivo(s) de muestra detectado(s) en este PR")
                        for sf in sample_files:
                            c_sf1, c_sf2 = st.columns([3, 1])
                            sf_base = os.path.basename(sf["filename"])
                            c_sf1.write(f"📄 `{sf['filename']}` ({sf['status']})")
                            if c_sf2.button(f"⬇️ Descargar {sf_base}", key=f"dl_sf_{chosen_pr['number']}_{sf_base}"):
                                dest_parent_dir = os.path.join(new_repo, "models", "conversion", selected_parent)
                                os.makedirs(dest_parent_dir, exist_ok=True)
                                target_sample_loc = os.path.join(dest_parent_dir, sf_base)
                                with st.spinner(f"Descargando {sf_base}..."):
                                    sample_bytes = download_github_file(active_gh_token, sf["raw_url"], sf["contents_url"])
                                    if sample_bytes:
                                        with open(target_sample_loc, "wb") as f_samp:
                                            f_samp.write(sample_bytes)
                                        st.session_state[f"sample_file_{rep_choice}"] = target_sample_loc
                                        st.success(f"✅ Muestra guardada en `{target_sample_loc}` y activa para pruebas!")
                                    else:
                                        st.error("No se pudo descargar la muestra de GitHub.")

        elif source_mode == "📁 Archivo detectado en la carpeta / repositorio local":
            if chosen_rep_data and chosen_rep_data.get("file") and os.path.isfile(chosen_rep_data["file"]):
                with open(chosen_rep_data["file"], "r", encoding="utf-8", errors="ignore") as f:
                    raw_conv_code = f.read()
            else:
                # Intentar buscar en el repo nuevo si ya se había guardado
                local_dest_py = os.path.join(new_repo, "models", "conversion", selected_parent, f"{rep_choice}.py")
                if os.path.isfile(local_dest_py):
                    with open(local_dest_py, "r", encoding="utf-8", errors="ignore") as f:
                        raw_conv_code = f.read()
                else:
                    raw_conv_code = f"# No se encontró archivo .py local para {rep_choice}."

        elif source_mode == "📤 Subir archivo .py (descargado de GitHub)":
            uploaded_py = st.file_uploader(f"Subir script de {rep_choice} (.py):", type=["py"], key=f"py_up_{rep_choice}")
            if uploaded_py is not None:
                raw_conv_code = uploaded_py.getvalue().decode("utf-8", errors="ignore")
                st.success(f"✅ Archivo `{uploaded_py.name}` cargado.")
            elif chosen_rep_data and chosen_rep_data.get("file") and os.path.isfile(chosen_rep_data["file"]):
                with open(chosen_rep_data["file"], "r", encoding="utf-8", errors="ignore") as f:
                    raw_conv_code = f.read()

        elif source_mode == "📋 Pegar código del freelancer directamente":
            initial_val = ""
            if chosen_rep_data and chosen_rep_data.get("file") and os.path.isfile(chosen_rep_data["file"]):
                with open(chosen_rep_data["file"], "r", encoding="utf-8", errors="ignore") as f:
                    initial_val = f.read()
            raw_conv_code = st.text_area(
                "Pega el código entregado por el freelancer o copiado de GitHub:",
                value=initial_val,
                height=250,
                key=f"text_area_{rep_choice}"
            )

        is_already_v2 = ("Conversion_Base" in raw_conv_code and "models.conversion" in raw_conv_code) or is_v2_flow
        
        apply_conv_refactor = st.checkbox(
            "Aplicar refactorizador V1 ➔ V2 (quitar sys.path, ajustar imports y clase base Conversion_Base)",
            value=(not is_already_v2),
            key=f"chk_apply_conv_refactor_{rep_choice}",
            help="Desmárcalo si el código ya fue escrito o adaptado directamente en la arquitectura V2."
        )

        if apply_conv_refactor:
            refactored_conv_code = refactor_conversion_code(raw_conv_code, rep_choice)
            c_code1, c_code2 = st.columns(2)
            with c_code1:
                st.markdown("**Código Original / Ingresado**")
                st.code(raw_conv_code if raw_conv_code else "# Sin código ingresado", language="python")
            with c_code2:
                st.markdown("**Código Estandarizado (V2)**")
                st.code(refactored_conv_code if refactored_conv_code else "# Esperando código", language="python")
            code_to_save = refactored_conv_code
            save_btn_label = f"💾 Guardar Código Estandarizado de {rep_choice} en V2"
        else:
            st.markdown("**Código V2 Listo para Guardar / Ejecutar:**")
            st.code(raw_conv_code if raw_conv_code else "# Esperando código...", language="python")
            code_to_save = raw_conv_code
            save_btn_label = f"💾 Guardar Código de {rep_choice} en V2"

        if st.button(save_btn_label, type="primary", key=f"btn_save_conv_code_{rep_choice}"):
            if not code_to_save.strip() or code_to_save.startswith("# No se encontró"):
                st.error("No hay código válido para guardar. Carga o pega el código primero.")
            else:
                dest_parent_dir = os.path.join(new_repo, "models", "conversion", selected_parent)
                os.makedirs(dest_parent_dir, exist_ok=True)
                
                # Asegurar que no haya __init__.py
                init_rm = os.path.join(dest_parent_dir, "__init__.py")
                if os.path.exists(init_rm):
                    try: os.remove(init_rm)
                    except Exception: pass
                    
                target_script = os.path.join(dest_parent_dir, f"{rep_choice}.py")
                with open(target_script, "w", encoding="utf-8") as f:
                    f.write(code_to_save)
                st.success(f"✨ Archivo guardado correctamente en: `{target_script}`")

    # ─────────────────────────────────────────────────────────────
    # PASO 2: PRUEBAS DE CONVERSIÓN (FASE 1 Y 2)
    # ─────────────────────────────────────────────────────────────
    with conv_tab2:
        st.subheader("Paso 2: Pruebas Unitarias de Conversión")
        st.write("Ejecuta la prueba en dos etapas como indica el manual:")
        st.markdown("""
        * **Botón 1 (Extracción Pura - Paso 6):** Prueba la extracción de tablas sin tocar la base de datos auxiliar. Genera el archivo SQLite con los datos extraídos.
        * **Botón 2 (Con Reemplazos / text_match - Paso 7):** Ejecuta `text_match`, creando/actualizando la tabla de reemplazos en `DATA_DB_BO_AUX`.
        """)

        active_sample = st.session_state.get(f"sample_file_{rep_choice}", sample_file_to_use)
        if not active_sample or not os.path.isfile(active_sample):
            st.warning("⚠️ Debes seleccionar o subir un archivo de muestra en el Paso 1 para poder ejecutar las pruebas.")
        else:
            st.info(f"Usando muestra: `{active_sample}`")

            col_btn_test1, col_btn_test2 = st.columns(2)

            # BOTÓN 1: EXTRACCIÓN PURA
            with col_btn_test1:
                if st.button("1. 🧪 Probar Extracción Pura (Sin text_match)", use_container_width=True):
                    with st.spinner("Ejecutando test unitario de extracción pura (Paso 6)..."):
                        t1_res = run_conversion_step_test(
                            report_code=rep_choice,
                            sample_file_path=active_sample,
                            new_repo_path=new_repo,
                            skip_text_match=True
                        )
                        if t1_res["success"]:
                            st.success("✅ Test de Extracción Pura APROBADO (OK)!")
                            if t1_res["sqlite_created"]:
                                st.success(f"📁 Archivo SQLite generado exitosamente: `{t1_res['sqlite_path']}`")
                        else:
                            st.error("❌ El test de extracción pura falló.")
                            if t1_res.get("diagnostics"):
                                st.markdown("### 🩺 Diagnóstico Inteligente:")
                                for d in t1_res["diagnostics"]:
                                    st.warning(d)

                        with st.expander("Ver logs de la prueba (stdout / stderr)", expanded=not t1_res["success"]):
                            if t1_res["stdout"]:
                                st.code(t1_res["stdout"])
                            if t1_res["stderr"]:
                                st.code(t1_res["stderr"])

            # BOTÓN 2: CON REEMPLAZOS
            with col_btn_test2:
                if st.button("2. 🔀 Probar con Reemplazos (text_match activo)", type="primary", use_container_width=True):
                    with st.spinner("Ejecutando test con reemplazos hacia DATA_DB_BO_AUX (Paso 7)..."):
                        t2_res = run_conversion_step_test(
                            report_code=rep_choice,
                            sample_file_path=active_sample,
                            new_repo_path=new_repo,
                            skip_text_match=False
                        )
                        if t2_res["success"]:
                            st.success("✅ Test con Reemplazos APROBADO (OK)!")
                            st.info("Se ha creado/actualizado la tabla de reemplazos en `DATA_DB_BO_AUX`.")
                        else:
                            st.error("❌ El test con reemplazos falló.")
                            if t2_res.get("diagnostics"):
                                st.markdown("### 🩺 Diagnóstico Inteligente:")
                                for d in t2_res["diagnostics"]:
                                    st.warning(d)

                        with st.expander("Ver logs de la prueba (stdout / stderr)", expanded=not t2_res["success"]):
                            if t2_res["stdout"]:
                                st.code(t2_res["stdout"])
                            if t2_res["stderr"]:
                                st.code(t2_res["stderr"])

    # ─────────────────────────────────────────────────────────────
    # PASO 3: VERIFICACIÓN Y AUDITORÍA DE DATOS
    # ─────────────────────────────────────────────────────────────
    with conv_tab3:
        st.subheader("Paso 3: Verificación y Auditoría de Datos Extraídos")
        st.write("Revisa visualmente los resultados antes de proceder a la creación de la plantilla o subida al servidor:")

        sub_audit1, sub_audit2 = st.tabs(["📊 Datos Extraídos (SQLite)", "🏷️ Tabla de Reemplazos (DATA_DB_BO_AUX)"])

        with sub_audit1:
            st.markdown(f"#### Datos de la Tabla `{rep_choice}` en SQLite local")
            df_sqlite, sq_path_found, err_sq = get_sqlite_data(new_repo, selected_parent, rep_choice, limit=200)
            if df_sqlite is not None:
                st.success(f"Se cargaron **{len(df_sqlite)}** filas del archivo: `{sq_path_found}`")
                st.markdown("**Columnas detectadas:** " + ", ".join([f"`{c}`" for c in df_sqlite.columns]))
                safe_dataframe(df_sqlite, use_container_width=True)
                
                # Verificación de columnas de nivel
                nv_cols = [c for c in df_sqlite.columns if c.lower().startswith("nv") or "nivel" in c.lower() or "categoria" in c.lower()]
                if nv_cols:
                    st.info(f"💡 Columnas jerárquicas de nivel encontradas: {nv_cols}. Verifica que los textos correspondan exactamente a cada nivel.")
                if "valor" in df_sqlite.columns:
                    st.write(f"Métricas de columna `valor`: Tipo={df_sqlite['valor'].dtype}, Total no nulos={df_sqlite['valor'].count()}")
            else:
                st.warning(f"Aún no hay datos en SQLite para `{rep_choice}`. Ejecuta primero la prueba en el Paso 2 para generar el archivo.")
                if err_sq:
                    st.caption(f"Detalle: {err_sq}")

        with sub_audit2:
            st.markdown(f"#### 🏷️ Editor de Tabla de Reemplazos (`DATA_DB_BO_AUX`)")
            st.caption(
                "✏️ **Edición Directa en Pantalla:** Puedes editar los valores directamente en la tabla (doble clic en cualquier celda), "
                "agregar nuevas filas al final o corregir problemas de codificación (ej. 'Espaa' ➔ 'España') sin tener que abrir Beekeeper o DBeaver."
            )

            # Claves de session_state para persistencia
            st_key_df = f"repl_data_df_{rep_choice}"
            st_key_tbl = f"repl_tbl_name_{rep_choice}"
            st_key_err = f"repl_last_err_{rep_choice}"

            # Botones superiores de acción
            col_act1, col_act2, col_act3 = st.columns([1.5, 1.5, 3])
            with col_act1:
                btn_load = st.button("🔄 Cargar / Refrescar BD", key=f"btn_load_repl_{rep_choice}", help="Recarga los datos frescos de PostgreSQL y descarta ediciones no guardadas")
            with col_act2:
                btn_save_top = st.button("💾 Guardar Cambios en BD", key=f"btn_save_repl_top_{rep_choice}", type="primary", help="Aplica todos los cambios (modificaciones, agregados y eliminaciones) en la base de datos")

            # Carga automática inicial o al presionar Refrescar
            if btn_load or (st_key_df not in st.session_state):
                with st.spinner("Consultando tabla de reemplazos en PostgreSQL..."):
                    df_repl, repl_tbl_name, err_repl = get_replacement_table_data(
                        report_code=rep_choice,
                        db_host=db_host,
                        db_port=db_port,
                        db_user=db_user,
                        db_pass=db_pass,
                        limit=500
                    )
                    st.session_state[st_key_df] = df_repl
                    st.session_state[st_key_tbl] = repl_tbl_name
                    st.session_state[st_key_err] = err_repl

            current_df = st.session_state.get(st_key_df)
            current_tbl_name = st.session_state.get(st_key_tbl, "")
            current_err = st.session_state.get(st_key_err)

            if current_df is not None:
                st.success(f"Tabla activa: **`{current_tbl_name}`** | **{len(current_df)}** registros cargados.")

                # Configuración de columnas para el editor
                col_cfg = {}
                if "id" in current_df.columns:
                    col_cfg["id"] = st.column_config.NumberColumn(
                        "ID (Solo Lectura)",
                        disabled=True,
                        help="Identificador autoincremental de la base de datos (No modificable)"
                    )
                if "original_value" in current_df.columns:
                    col_cfg["original_value"] = st.column_config.TextColumn(
                        "original_value (Original)",
                        required=True,
                        help="Texto original tal como viene en el reporte fuente"
                    )
                if "srch_value" in current_df.columns:
                    col_cfg["srch_value"] = st.column_config.TextColumn(
                        "srch_value (Búsqueda limpia)",
                        help="Texto normalizado en minúsculas y sin tildes para búsqueda"
                    )
                if "final_value" in current_df.columns:
                    col_cfg["final_value"] = st.column_config.TextColumn(
                        "final_value (Reemplazo final)",
                        required=True,
                        help="Valor definitivo y estandarizado con el que se mapea"
                    )
                if "created_at" in current_df.columns:
                    col_cfg["created_at"] = st.column_config.DatetimeColumn(
                        "created_at",
                        disabled=True,
                        help="Timestamp de inserción en la base de datos"
                    )

                # Tabla interactiva
                edited_df = st.data_editor(
                    current_df,
                    key=f"repl_editor_{rep_choice}",
                    use_container_width=True,
                    num_rows="dynamic",
                    column_config=col_cfg
                )

                # Detección de cambios pendientes
                n_upd = 0
                n_ins = 0
                n_del = 0
                has_id = "id" in current_df.columns and "id" in edited_df.columns
                if has_id:
                    orig_ids = set(current_df["id"].dropna().astype(int).tolist())
                    edit_ids = set()
                    for _, r in edited_df.iterrows():
                        rid = r.get("id")
                        if pd.notnull(rid) and not pd.isna(rid):
                            try:
                                irid = int(rid)
                                if irid in orig_ids and irid > 0:
                                    edit_ids.add(irid)
                                else:
                                    n_ins += 1
                            except (ValueError, TypeError):
                                n_ins += 1
                        else:
                            if (pd.notnull(r.get("original_value")) and str(r.get("original_value")).strip()) or (pd.notnull(r.get("final_value")) and str(r.get("final_value")).strip()):
                                n_ins += 1

                    orig_map = {int(r["id"]): r for _, r in current_df.iterrows() if pd.notnull(r["id"])}
                    for _, r in edited_df.iterrows():
                        try:
                            rid = int(r.get("id"))
                            if rid in orig_map:
                                orig_r = orig_map[rid]
                                for c in ["original_value", "srch_value", "final_value"]:
                                    if c in edited_df.columns and c in current_df.columns:
                                        vo = "" if pd.isna(orig_r[c]) else str(orig_r[c]).strip()
                                        ve = "" if pd.isna(r[c]) else str(r[c]).strip()
                                        if vo != ve:
                                            n_upd += 1
                                            break
                        except (ValueError, TypeError):
                            pass

                    n_del = len(orig_ids - edit_ids)

                has_changes = (n_upd > 0 or n_ins > 0 or n_del > 0)
                if has_changes:
                    st.info(f"📝 **Cambios locales pendientes:** {n_upd} modificados, {n_ins} nuevos, {n_del} eliminados. Recuerda hacer clic en **Guardar Cambios en BD**.")

                col_s1, col_s2 = st.columns([2, 4])
                with col_s1:
                    btn_save_bot = st.button("💾 Guardar Cambios en Base de Datos", key=f"btn_save_repl_bot_{rep_choice}", type="primary", use_container_width=True)

                # Ejecutar guardado si se presiona el botón superior o inferior
                if btn_save_top or btn_save_bot:
                    if not has_changes:
                        st.info("ℹ️ No hay modificaciones pendientes en la tabla.")
                    else:
                        with st.spinner("Guardando modificaciones en PostgreSQL (`DATA_DB_BO_AUX`)..."):
                            res_save = save_replacement_table_changes(
                                report_code=rep_choice,
                                original_df=current_df,
                                edited_df=edited_df,
                                db_host=db_host,
                                db_port=db_port,
                                db_user=db_user,
                                db_pass=db_pass,
                                allow_delete=True
                            )
                        if res_save.get("success"):
                            st.success(
                                f"🎉 **¡Cambios guardados con éxito en `{current_tbl_name}`!** "
                                f"({res_save['updated']} actualizados, {res_save['inserted']} nuevos, {res_save['deleted']} eliminados)"
                            )
                            # Recargar datos actualizados desde la BD
                            df_repl_fresh, _, _ = get_replacement_table_data(
                                report_code=rep_choice,
                                db_host=db_host,
                                db_port=db_port,
                                db_user=db_user,
                                db_pass=db_pass,
                                limit=500
                            )
                            st.session_state[st_key_df] = df_repl_fresh
                            st.rerun()
                        else:
                            st.error(f"❌ Error al guardar en base de datos: {res_save.get('error')}")

                # Sección rápida: Insertar un nuevo reemplazo
                with st.expander("➕ Formulario Rápido: Agregar un nuevo registro de reemplazo"):
                    col_nf1, col_nf2, col_nf3 = st.columns(3)
                    with col_nf1:
                        new_orig = st.text_input("Texto Original (original_value):", key=f"inp_new_orig_{rep_choice}", placeholder="ej. Bolivia")
                    with col_nf2:
                        auto_srch = normalize_srch_value(new_orig) if new_orig else ""
                        new_srch = st.text_input("Búsqueda Normalizada (srch_value):", value=auto_srch, key=f"inp_new_srch_{rep_choice}", help="Calculado automáticamente sin tildes/espacios")
                    with col_nf3:
                        new_final = st.text_input("Valor Final (final_value):", value=new_orig, key=f"inp_new_final_{rep_choice}", placeholder="ej. Bolivia")

                    if st.button("➕ Insertar Registro Directo", key=f"btn_insert_single_{rep_choice}", type="secondary"):
                        if not new_orig and not new_final:
                            st.warning("Ingresa un valor original o final.")
                        else:
                            ok_ins, err_ins = insert_single_replacement_record(
                                report_code=rep_choice,
                                original_value=new_orig,
                                srch_value=new_srch,
                                final_value=new_final,
                                db_host=db_host,
                                db_port=db_port,
                                db_user=db_user,
                                db_pass=db_pass
                            )
                            if ok_ins:
                                st.success(f"✅ Registro insertado exitosamente en `{current_tbl_name}`.")
                                df_repl_fresh, _, _ = get_replacement_table_data(
                                    report_code=rep_choice,
                                    db_host=db_host,
                                    db_port=db_port,
                                    db_user=db_user,
                                    db_pass=db_pass,
                                    limit=500
                                )
                                st.session_state[st_key_df] = df_repl_fresh
                                st.rerun()
                            else:
                                st.error(f"Error al insertar: {err_ins}")

                # Sección de eliminación por ID
                with st.expander("🗑️ Eliminar un registro específico por ID"):
                    col_del1, col_del2 = st.columns([2, 1])
                    with col_del1:
                        del_id_input = st.number_input("ID del registro a eliminar:", min_value=1, step=1, key=f"inp_del_id_{rep_choice}")
                    with col_del2:
                        st.write("")
                        st.write("")
                        if st.button("🗑️ Eliminar por ID", key=f"btn_del_single_{rep_choice}"):
                            ok_del, err_del = delete_single_replacement_record(
                                report_code=rep_choice,
                                record_id=del_id_input,
                                db_host=db_host,
                                db_port=db_port,
                                db_user=db_user,
                                db_pass=db_pass
                            )
                            if ok_del:
                                st.success(f"✅ Registro con ID {del_id_input} eliminado correctamente.")
                                df_repl_fresh, _, _ = get_replacement_table_data(
                                    report_code=rep_choice,
                                    db_host=db_host,
                                    db_port=db_port,
                                    db_user=db_user,
                                    db_pass=db_pass,
                                    limit=500
                                )
                                st.session_state[st_key_df] = df_repl_fresh
                                st.rerun()
                            else:
                                st.error(f"Error al eliminar: {err_del}")

            else:
                st.warning(f"No se pudieron cargar datos de la tabla de reemplazos `{current_tbl_name or rep_choice}`.")
                if current_err:
                    st.error(f"Detalle: {current_err}")
                st.info("Asegúrate de que la conexión a `platform_db` y `DATA_DB_BO_AUX` esté activa (VPN o red local) y que hayas ejecutado la prueba con reemplazos en el Paso 2.")
                if st.button("🔄 Reintentar Carga", key=f"btn_retry_load_{rep_choice}"):
                    st.session_state.pop(st_key_df, None)
                    st.rerun()

    # ─────────────────────────────────────────────────────────────
    # PASO 4: PLANTILLA SQLITE (COLUMNS_TO_REVIEW)
    # ─────────────────────────────────────────────────────────────
    with conv_tab4:
        st.subheader("Paso 4: Configurar 'columns_to_review' en Plantilla SQLite")
        st.markdown("""
        Según el **Paso 8** del manual:
        - La tabla interna del SQLite debe llamarse **`columns_to_review`**.
        - La columna debe llamarse **`column`**.
        - **SOLO** debe incluir niveles jerárquicos (`nv1`, `nv2`, ..., `nvX`). Excluye `fecha` si el reporte tiene fechas anuales/discontinuas.
        - 🚫 **NUNCA** incluir `valor` ni metadatos (`file`, `tituloX`).
        """)

        dest_sq = os.path.join(new_repo, "models", "conversion", selected_parent, f"{rep_choice}.sqlite")
        if not os.path.isfile(dest_sq):
            st.warning(f"No se encontró el archivo SQLite `{dest_sq}`. Ejecuta las pruebas del Paso 2 primero.")
        else:
            st.info(f"Archivo SQLite listo: `{dest_sq}`")
            if st.button("⚙️ Configurar e Inicializar columns_to_review", type="primary"):
                ok_cr, review_cols, tables_found, err_cr = setup_columns_to_review(dest_sq, rep_choice)
                if ok_cr:
                    st.success("✅ ¡Tabla `columns_to_review` configurada con éxito!")
                    st.write(f"**Tablas presentes en el SQLite:** `{tables_found}`")
                    st.write(f"**Columnas añadidas a revisión ({len(review_cols)}):**")
                    st.json(review_cols)
                else:
                    st.error(f"Error configurando columns_to_review: {err_cr}")

    # ─────────────────────────────────────────────────────────────
    # PASO 5: DESPLIEGUE AL SERVIDOR
    # ─────────────────────────────────────────────────────────────
    with conv_tab5:
        st.subheader("Paso 5: Despliegue al Servidor Remoto y Generación de DAG")
        st.markdown("""
        Una vez que los datos y la plantilla SQLite han sido verificados:
        1. Sube el script `.py` a `models/conversion/` en el servidor.
        2. Sube la plantilla `.sqlite` de referencia a `/mnt/datos1/data_process/...`.
        3. Genera el DAG de conversión automáticamente en Airflow (Docker).
        """)

        col_dep1, col_dep2 = st.columns(2)
        with col_dep1:
            deploy_srv_host = st.text_input("Host Servidor:", value=DEFAULT_SSH_HOST, key="dep_conv_host")
            deploy_srv_user = st.text_input("Usuario SSH:", value=DEFAULT_SSH_USER, key="dep_conv_user")
        with col_dep2:
            deploy_srv_port = st.number_input("Puerto SSH:", value=DEFAULT_SSH_PORT, key="dep_conv_port")
            deploy_srv_pass = st.text_input("Contraseña SSH / sudo:", value=DEFAULT_SSH_PASS, type="password", key="dep_conv_pass")

        dest_sq_check = os.path.join(new_repo, "models", "conversion", selected_parent, f"{rep_choice}.sqlite")
        sq_available = os.path.isfile(dest_sq_check)

        st.write(f"Archivo de código: `models/conversion/{selected_parent}/{rep_choice}.py`")
        st.write(f"Plantilla SQLite: `{dest_sq_check}` ({'Listo' if sq_available else 'No generado'})")

        gen_dag_choice = st.checkbox("Generar DAG de conversión en Airflow (Docker)", value=True, key="chk_gen_dag_conv")

        if st.button("🚀 Subir al Servidor y Generar DAG de Conversión", type="primary", use_container_width=True):
            if not deploy_srv_pass:
                st.error("Por favor introduce la contraseña del servidor.")
            else:
                with st.spinner("Transfiriendo archivos vía SFTP y ejecutando generador en Docker..."):
                    local_model_folder = os.path.join(new_repo, "models", "conversion", selected_parent)
                    res_dep = deploy_robot_to_server(
                        host=deploy_srv_host,
                        port=int(deploy_srv_port),
                        username=deploy_srv_user,
                        password=deploy_srv_pass,
                        remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                        process_type="conversion",
                        robot_code=selected_parent,
                        local_dir=local_model_folder,
                        generate_dag=gen_dag_choice
                    )
                    if res_dep["success"]:
                        show_deploy_success_banner(selected_parent, process_type="Robot de Conversión", dag_id=selected_parent)
                    else:
                        st.error("⚠️ Ocurrieron errores durante el despliegue.")

                    for l in res_dep["logs"]:
                        st.write(l)

        # ─────────────────────────────────────────────────────────
        # SUB-SECCIÓN: DISPARO MANUAL DE PRUEBA EN AIRFLOW
        # ─────────────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🎯 Probar Ejecución del DAG en Airflow (Trigger Remoto)")
        st.caption("Ejecuta el comando `airflow dags trigger` dentro del contenedor worker de Airflow con los parámetros de prueba.")

                # Autocompletado inteligente desde platform_db
        auto_dl = get_latest_download_for_report(rep_choice, engine)
        if auto_dl:
            st.info(f"🎯 **Última descarga detectada automáticamente:** ID `{auto_dl['id_download']}` (Corte: `{auto_dl['downloaded_to']}`)")
            default_id_dl = auto_dl["id_download"]
            default_file_dl = auto_dl["file"]
        else:
            default_id_dl = 1
            default_file_dl = os.path.join(r"\\10.0.0.16\downloaded_files\BO", selected_parent.replace("C_", "D_"), "2026")

        col_trig1, col_trig2 = st.columns(2)
        with col_trig1:
            trig_code = st.text_input("Código de reporte (--conf 'code'):", value=rep_choice, key=f"trig_code_{rep_choice}")
            trig_id_dl = st.number_input("ID de descarga (--conf 'id_download'):", value=default_id_dl, step=1, key=f"trig_iddl_{rep_choice}")
        with col_trig2:
            trig_file = st.text_input("Ruta descargada (--conf 'file'):", value=default_file_dl, key=f"trig_file_{rep_choice}")

        if st.button(f"🎯 Disparar DAG `{selected_parent}` en Airflow", use_container_width=True):
            if not deploy_srv_pass:
                st.error("Por favor introduce la contraseña del servidor arriba para conectar por SSH.")
            else:
                conf_payload = {
                    "code": trig_code,
                    "id_download": int(trig_id_dl),
                    "file": trig_file
                }
                with st.spinner(f"Disparando DAG {selected_parent} en Airflow..."):
                    trig_res = trigger_dag_on_server(
                        host=deploy_srv_host,
                        port=int(deploy_srv_port),
                        username=deploy_srv_user,
                        password=deploy_srv_pass,
                        remote_base_path="/home/datax-pds/datax/data-processing-platform-dev",
                        dag_id=selected_parent,
                        conf=conf_payload
                    )
                    if trig_res["success"]:
                        st.success(f"🎉 DAG `{selected_parent}` disparado exitosamente en Airflow!")
                    else:
                        st.warning("El comando terminó con advertencias o error.")

                    with st.expander("Ver salida detallada de Airflow", expanded=True):
                        st.code(trig_res["output"] or "Sin salida")

# ─── PESTAÑA 3: LOTE ───────────────────────────────────────────

# ═════════════════════════════════════════════════════════════════════════════
# PESTAÑA: MIGRACIÓN A POSTGRESQL (M_...)
# ═════════════════════════════════════════════════════════════════════════════
elif "Robots de Migración" in mode:
    st.header("🚚 Robots de Migración (`M_...` / PostgreSQL)")
    st.caption("Generación automática desde SQLite de Conversión o Revisión y Despliegue de robots de migración existentes en V2.")

    mig_flow_mode = st.radio(
        "Flujo de trabajo para Migración:",
        ["🔄 Generar desde SQLite de Conversión (Flujo Estándar)", "✨ Robot de Migración Existente / Ya Desarrollado en V2"],
        horizontal=True,
        key="mig_flow_mode"
    )

    if mig_flow_mode.startswith("🔄"):
        conv_families = scan_conversion_outputs(new_repo)
        if not conv_families:
            st.warning(f"No se encontraron familias de conversión con archivos `.sqlite` en `{new_repo}/models/conversion`.")
        else:
            fam_dict = {f["parent_code"]: f for f in conv_families}
            col_m1, col_m2 = st.columns(2)
            with col_m1:
                sel_parent = st.selectbox("1. Familia de Conversión / Migración:", list(fam_dict.keys()), key="mig_parent_sel")
        
        fam_info = fam_dict[sel_parent]
        reports_in_fam = fam_info["reports"]
        rep_codes = [r["code"] for r in reports_in_fam]

        with col_m2:
            sel_report = st.selectbox("2. Reporte a Migrar:", rep_codes, key="mig_report_sel")

        rep_obj = next(r for r in reports_in_fam if r["code"] == sel_report)
        sqlite_file = rep_obj["sqlite_file"]
        mig_parent_code = fam_info["migration_parent"]

        db_mig_info = None
        if db_connected and engine is not None:
            db_mig_info = get_migration_db_info(sel_report, engine)

        if db_mig_info:
            st.info(
                f"📊 **Metadatos en BD:** Nombre: *{db_mig_info.get('name', 'N/A')}* | "
                f"Storage Table: `{db_mig_info.get('storage_table', 'N/A')}` | "
                f"Conversion Factor en BD: `{db_mig_info.get('conversion_factor', 'N/A')}` | "
                f"Decimal Separator: `{db_mig_info.get('decimal_separator', 'N/A')}`"
            )
        else:
            st.caption(f"ℹ️ Archivo SQLite detectado: `{sqlite_file}`")

        report_db_name = db_mig_info.get("name", "") if db_mig_info else ""
        struct = inspect_sqlite_structure(sqlite_file, sel_report, extra_text=report_db_name)
        
        tab_cfg, tab_preview, tab_deploy = st.tabs([
            "⚙️ 1. Configuración & Estructura",
            "📄 2. Previsualizar Código (.sql & .py)",
            "🚀 3. Guardar & Desplegar al Servidor"
        ])

        with tab_cfg:
            st.markdown("#### 🤖 Agente Analizador Inteligente de SQLite (Gemini / Heurístico)")
            st.caption("El Agente examina títulos, jerarquías multinivel, categorías únicas y la distribución numérica en SQLite para clasificar exactamente métricas homogéneas o mixtas (tasa, moneda, %, BOB, USD, UFV) y el factor de conversión correspondiente.")

            agent_state_key = f"agent_res_{sel_report}"
            col_ag1, col_ag2, col_ag3 = st.columns([2, 1, 1])
            with col_ag1:
                run_agent_btn = st.button("🧠 Ejecutar Análisis con Agente IA", key=f"btn_ag_{sel_report}", use_container_width=True)
            with col_ag2:
                re_run_btn = st.button("🔄 Re-analizar", key=f"btn_reag_{sel_report}", use_container_width=True, help="Limpia el resultado anterior y vuelve a consultar al Agente IA.")
            with col_ag3:
                auto_agent = st.checkbox("Analizar al cargar", value=False, key=f"auto_ag_{sel_report}")

            if run_agent_btn or re_run_btn or (auto_agent and agent_state_key not in st.session_state):
                with st.spinner("El Agente IA está analizando títulos, jerarquías y datos del SQLite..."):
                    agent_res = run_agent_sqlite_analysis(
                        sqlite_path=sqlite_file,
                        api_key=st.session_state.get("gemini_api_key", DEFAULT_GEMINI_API_KEY)
                    )
                    st.session_state[agent_state_key] = agent_res
                    # Sincronizar explícitamente los controles de la UI:
                    st.session_state[f"cb_mixed_{sel_report}"] = bool(agent_res.get("is_mixed", True))
                    st.session_state[f"metric_{sel_report}"] = agent_res.get("base_metric", "precio")
                    st.session_state[f"unit_{sel_report}"] = agent_res.get("base_unit", "GBP/Tn")
                    st.session_state[f"factor_{sel_report}"] = float(agent_res.get("conversion_factor", 1.0))
                    st.rerun()

            agent_data = st.session_state.get(agent_state_key, {})
            custom_m = agent_data.get("get_metric_code", "") if agent_data else ""
            custom_u = agent_data.get("get_unit_code", "") if agent_data else ""
            if agent_data and "explanation" in agent_data:
                src_badge = "Google Gemini API 🚀" if "gemini" in str(agent_data.get("source", "")).lower() else "Motor Heurístico Avanzado ⚡"
                st.info(f"💡 **Diagnóstico del Agente IA ({src_badge}):**\n\n{agent_data.get('explanation', '')}")
                if agent_data.get("agent_warning"):
                    st.warning(agent_data["agent_warning"])

            # Valores efectivos priorizados por el Agente si ya analizó:
            effective_metric = agent_data.get("base_metric", struct["suggested_metric"])
            effective_unit = agent_data.get("base_unit", struct["suggested_unit"])
            effective_factor = agent_data.get("conversion_factor", struct["suggested_factor"])
            effective_is_mixed = agent_data.get("is_mixed", (struct["has_mixed_rows"] or struct.get("has_multi_currency", False) or struct.get("has_multiple_facts", False)))

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                metric_options = [
                    "precio", "tasa", "moneda", "porcentaje", "tipo_cambio", "volumen", 
                    "energia", "potencia", "indice", "ratio", "conteo", "temperatura", "precipitacion"
                ]
                if effective_metric not in metric_options:
                    metric_options.insert(0, effective_metric)
                def_metric_idx = metric_options.index(effective_metric) if effective_metric in metric_options else 0
                chosen_metric = st.selectbox("Métrica Base:", metric_options, index=def_metric_idx, key=f"metric_{sel_report}")
                
                common_units = [
                    "USD/Tn", "GBP/Tn", "EUR/Tn", "USD/Bbl", "USc/lb",
                    "BOB", "USD", "UFV", "BOB/USD", "BOB/UFV", "%", "veces", "puntos",
                    "unidades", "reclamos", "personas", "casos", "cuentas", "transacciones", "operaciones",
                    "GWh", "MWh", "kWh", "Wh", "GW", "MW", "kW",
                    "Tn", "Kg", "m3", "MMpcd", "Bbl", "litros", "°C", "mm"
                ]
                if effective_unit not in common_units:
                    common_units.insert(0, effective_unit)
                chosen_unit = st.selectbox("Unidad Métrica Base:", common_units, index=common_units.index(effective_unit) if effective_unit in common_units else 0, key=f"unit_{sel_report}", help="Unidad predominante del reporte.")
                custom_unit = st.text_input("✍️ O escribir otra unidad personalizada (opcional):", value="", placeholder="Ej: reclamos, unidades, GWh, etc.")
                if custom_unit.strip():
                    chosen_unit = custom_unit.strip()

            with col_c2:
                default_factor = float(db_mig_info.get("conversion_factor")) if (db_mig_info and db_mig_info.get("conversion_factor")) else effective_factor
                chosen_factor = st.number_input("Factor de Conversión:", value=float(default_factor), step=1.0, key=f"factor_{sel_report}")
                is_mixed = st.checkbox(
                    "🔀 Mapeo dinámico de Múltiples Hechos (Conteo, Porcentaje %, Monedas BOB/USD/UFV, etc.)",
                    value=effective_is_mixed,
                    key=f"cb_mixed_{sel_report}",
                    help="Detecta fila por fila si el valor corresponde a Porcentaje %, Moneda (BOB, USD, UFV), Tipo de Cambio, etc. y clasifica automáticamente cada fila."
                )
            if struct.get("detected_facts") and len(struct["detected_facts"]) > 1:
                facts_md = "\n".join([
                    f"**Hecho {i+1}:** `{f['metrica']}` · `{f['unidad']}` — {f.get('etiqueta', '')}"
                    for i, f in enumerate(struct["detected_facts"])
                ])
                st.info(
                    f"🎯 **{len(struct['detected_facts'])} Hechos / Métricas detectados automáticamente en este reporte:**\n\n{facts_md}\n\n"
                    f"_El mapeo dinámico está activo y clasificará cada fila según el texto de sus columnas._"
                )
            elif struct.get("has_multi_currency"):
                st.info(f"💱 **Múltiples monedas detectadas en las filas:** `{'`, `'.join(struct['detected_currencies'])}` (El robot asignará dinámicamente cada moneda a su respectiva fila).")

            st.markdown("#### 📋 Columnas Detectadas en SQLite y Estructura de Migración")
            st.success(f"**Columnas completas para PostgreSQL ({len(struct['all_columns'])}):** `{struct['all_columns']}`")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                st.markdown(f"• **Títulos:** `{struct['title_cols']}`")
                st.markdown(f"• **Jerarquías:** `{struct['nv_cols']}`")
            with col_s2:
                st.markdown(f"• **Tiempo y Valor:** `['fecha', 'valor']`")
                st.markdown(f"• **Columnas de Migración:** `['metrica', 'unidad_metrica']` *(se insertarán antes de `valor`)*")
            st.caption("ℹ️ *Nota: La columna `file` de SQLite se omite intencionalmente porque solo se usa como referencia local en la conversión y no pertenece a la tabla final de PostgreSQL.*")
            st.markdown("**Vista Previa de Datos Simulada:** *(Muestra cómo el robot clasificará cada fila con `metrica_preview` y `unidad_preview`)*")
            preview_df = struct["sample_df"].copy()
            if is_mixed:
                def preview_get_metric(row):
                    texts = [str(row.get(c, "")).upper() for c in reversed(struct["nv_cols"] + struct["title_cols"])]
                    combined = " ".join(texts)
                    for t in texts:
                        p_unit = parse_commodity_price_unit(t)
                        if p_unit:
                            return "precio"
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
                        words = set(re.split(r"[\s/()]+", t))
                        if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in t or "DEL EXTERIOR" in t:
                            return "moneda"
                        if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in t:
                            return "moneda"
                        if "UFV" in words:
                            return "moneda"
                    return chosen_metric

                def preview_get_unit(row):
                    texts = [str(row.get(c, "")).upper() for c in reversed(struct["nv_cols"] + struct["title_cols"])]
                    combined = " ".join(texts)
                    for t in texts:
                        p_unit = parse_commodity_price_unit(t)
                        if p_unit:
                            return p_unit
                    if any(tok in combined for tok in ["%", "PORCENTAJ", "PARTICIPACI", "PROPORCION"]):
                        return "%"
                    if "VECES" in combined or "RATIO" in combined:
                        return "veces"
                    match_base = re.search(r"(\d{4}\s*=\s*100)", combined)
                    if match_base:
                        return match_base.group(1).replace(" ", "")
                    for t in texts:
                        words = set(re.split(r"[\s/()]+", t))
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
                        words = set(re.split(r"[\s/()]+", t))
                        if "UFV" in words:
                            return "UFV"
                        if any(w in ["ME", "M.E.", "USD", "DOLARES", "DÓLARES", "$US"] for w in words) or "MONEDA EXTRANJERA" in t or "DEL EXTERIOR" in t:
                            return "USD"
                        if any(w in ["MN", "M.N.", "BOB", "BS", "BOLIVIANOS"] for w in words) or "MONEDA NACIONAL" in t:
                            return "BOB"
                    return chosen_unit

                # Si el Agente proporcionó código personalizado para get_metric y get_unit, usarlo en la simulación:
                if custom_m and custom_u:
                    try:
                        agent_ns = {}
                        exec(custom_m, {"pd": pd, "re": re}, agent_ns)
                        exec(custom_u, {"pd": pd, "re": re}, agent_ns)
                        if "get_metric" in agent_ns and "get_unit" in agent_ns:
                            preview_get_metric = agent_ns["get_metric"]
                            preview_get_unit = agent_ns["get_unit"]
                    except Exception as _ex_ag:
                        pass

                idx_val = preview_df.columns.get_loc("valor") if "valor" in preview_df.columns else len(preview_df.columns)
                preview_df.insert(idx_val, "metrica_preview", preview_df.apply(preview_get_metric, axis=1))
                preview_df.insert(idx_val + 1, "unidad_preview", preview_df.apply(preview_get_unit, axis=1))
            else:
                idx_val = preview_df.columns.get_loc("valor") if "valor" in preview_df.columns else len(preview_df.columns)
                preview_df.insert(idx_val, "metrica_preview", chosen_metric)
                preview_df.insert(idx_val + 1, "unidad_preview", chosen_unit)

            safe_dataframe(preview_df, use_container_width=True)
        sql_code = generate_migration_sql(struct["all_columns"])
        report_display_name = db_mig_info.get("name") if db_mig_info else struct["titles_text"]
        custom_m = agent_data.get("get_metric_code", "") if (agent_data and is_mixed) else ""
        custom_u = agent_data.get("get_unit_code", "") if (agent_data and is_mixed) else ""
        py_code = generate_migration_py(
            report_code=sel_report,
            report_name=report_display_name,
            columns=struct["all_columns"],
            metric=chosen_metric,
            unit=chosen_unit,
            factor=chosen_factor,
            has_mixed_rows=is_mixed,
            custom_metric_code=custom_m,
            custom_unit_code=custom_u
        )

        with tab_preview:
            st.subheader(f"📄 Archivos de Migración para `{sel_report}`")
            col_pr1, col_pr2 = st.columns(2)
            with col_pr1:
                st.markdown(f"**DDL SQL:** `{sel_report}.sql`")
                st.code(sql_code, language="sql")
            with col_pr2:
                st.markdown(f"**Robot Python:** `{sel_report}.py`")
                st.code(py_code, language="python")

        with tab_deploy:
            st.subheader("💾 Guardado Local y Despliegue")
            col_d1, col_d2 = st.columns(2)
            with col_d1:
                if st.button("💾 Guardar Archivos en models/migration/", type="primary", use_container_width=True):
                    saved_sql, saved_py = save_migration_files(
                        repo_path=new_repo,
                        parent_code=mig_parent_code,
                        report_code=sel_report,
                        sql_content=sql_code,
                        py_content=py_code
                    )
                    st.success(f"Archivos guardados exitosamente:\n- `{saved_sql}`\n- `{saved_py}`")

            with col_d2:
                st.markdown("#### 🚀 Despliegue Rápido por SSH")
                st.caption(f"Sube `{mig_parent_code}` al servidor, asigna permisos y ejecuta `main-generate.py` opción 3.")
                mig_ssh_pass = st.text_input("Contraseña SSH (datax-pds):", value=DEFAULT_SSH_PASS, type="password", key="mig_ssh_pass")
                
                if st.button(f"🚀 Desplegar {mig_parent_code} y Generar DAG en Servidor", use_container_width=True):
                    if not mig_ssh_pass:
                        st.error("Ingresa la contraseña de SSH para desplegar.")
                    else:
                        local_mig_dir = os.path.join(new_repo, "models", "migration", mig_parent_code)
                        save_migration_files(new_repo, mig_parent_code, sel_report, sql_code, py_code)
                        
                        with st.spinner("Desplegando en el servidor..."):
                            deploy_res = deploy_robot_to_server(
                                host=DEFAULT_SSH_HOST,
                                port=DEFAULT_SSH_PORT,
                                username=DEFAULT_SSH_USER,
                                password=mig_ssh_pass,
                                process_type="migration",
                                robot_code=mig_parent_code,
                                local_dir=local_mig_dir,
                                generate_dag=True
                            )
                        if deploy_res["success"]:
                            show_deploy_success_banner(mig_parent_code, process_type="Robot de Migración", dag_id=mig_parent_code)
                        else:
                            st.error(f"Error en despliegue: {deploy_res['error']}")
                        with st.expander("Ver logs de despliegue"):
                            st.text("\n".join(deploy_res["logs"]))

                st.markdown("---")
                st.markdown("#### ⚡ Disparar DAG en Airflow")
                st.caption("Ejecuta el DAG de migración en Airflow con la última conversión registrada.")

                latest_conv = get_latest_conversion_for_report(sel_report, engine) if (db_connected and engine is not None) else None
                if latest_conv:
                    st.info(
                        f"🎯 **Última Conversión detectada en BD:** ID `{latest_conv['id_conversion']}` | "
                        f"Corte: **`{latest_conv['converted_to']}`** (Registrada: `{latest_conv['conversion_date']}`)\n\n"
                        f"📁 Archivo: `{latest_conv['conversion_path']}`"
                    )
                    default_conv_id = latest_conv["id_conversion"]
                    default_conv_path = latest_conv["conversion_path"]
                else:
                    default_conv_id = 1
                    parts = mig_parent_code.split("_")
                    c_tag = parts[1] if len(parts) > 1 else "BO"
                    default_conv_path = f"/mnt/datos1/data_process/{c_tag}/{mig_parent_code.replace('M_', 'D_')}/{sel_report}.sqlite"

                col_mt1, col_mt2 = st.columns(2)
                with col_mt1:
                    trig_mig_code = st.text_input("Código reporte (--conf 'code'):", value=sel_report, key=f"trig_mig_code_{sel_report}")
                    trig_mig_id = st.number_input("ID conversión (--conf 'id_conversion'):", value=default_conv_id, step=1, key=f"trig_mig_id_{sel_report}")
                with col_mt2:
                    trig_mig_path = st.text_input("Ruta SQLite (--conf 'conversion_path'):", value=default_conv_path, key=f"trig_mig_path_{sel_report}")

                if st.button(f"▶️ Disparar DAG {mig_parent_code} en Airflow", use_container_width=True):
                    if not mig_ssh_pass:
                        st.error("Ingresa la contraseña de SSH arriba para conectar al servidor.")
                    else:
                        conf_payload = {
                            "code": trig_mig_code,
                            "id_conversion": int(trig_mig_id),
                            "conversion_path": trig_mig_path
                        }
                        corte_str = f" con corte {latest_conv['converted_to']}" if latest_conv else ""
                        with st.spinner(f"Disparando DAG {mig_parent_code} en Airflow worker{corte_str}..."):
                            trig_res = trigger_dag_on_server(
                                host=DEFAULT_SSH_HOST,
                                port=DEFAULT_SSH_PORT,
                                username=DEFAULT_SSH_USER,
                                password=mig_ssh_pass,
                                dag_id=mig_parent_code,
                                conf=conf_payload
                            )
                        if trig_res["success"]:
                            st.success(f"🎉 DAG `{mig_parent_code}` disparado exitosamente{corte_str}!")
                        else:
                            st.warning("El comando terminó con advertencias o error.")
                        with st.expander("Ver logs de disparo de Airflow", expanded=True):
                            st.code(trig_res["output"] or "Sin salida de terminal.")

    else:
        # ─── FLUJO ROBOT DE MIGRACIÓN EXISTENTE / YA EN V2 ────────────
        existing_migs = scan_existing_migration_robots(new_repo)
        
        sel_v2_mig_mode = st.radio(
            "Modo de selección de robot de migración:",
            ["📁 Seleccionar de robots en models/migration", "✍️ Ingresar código manualmente (Nuevo / GitHub)"],
            horizontal=True,
            key="sel_v2_mig_mode"
        )

        if sel_v2_mig_mode.startswith("📁") and existing_migs:
            fam_dict_v2 = {f["parent_code"]: f for f in existing_migs}
            col_vm1, col_vm2 = st.columns(2)
            with col_vm1:
                mig_parent_code = st.selectbox("1. Familia de Migración (M_...):", list(fam_dict_v2.keys()), key="v2_mig_parent_sel")
            fam_v2_info = fam_dict_v2[mig_parent_code]
            rep_v2_codes = [r["code"] for r in fam_v2_info["reports"]]
            with col_vm2:
                sel_report = st.selectbox("2. Reporte de Migración:", rep_v2_codes, key="v2_mig_rep_sel")
        else:
            if sel_v2_mig_mode.startswith("📁") and not existing_migs:
                st.info("No se encontraron carpetas `M_...` en `models/migration/` aún. Puedes ingresar los códigos manualmente:")
            col_vm1, col_vm2 = st.columns(2)
            with col_vm1:
                mig_parent_code = st.text_input("Familia de migración (ej. M_BO_000000017):", value="M_BO_000000017", key="v2_mig_inp_parent").strip()
            with col_vm2:
                sel_report = st.text_input("Reporte de migración (ej. D_BO_000000017_01):", value="D_BO_000000017_01", key="v2_mig_inp_rep").strip()

        # Cargar archivos existentes si existen
        loaded_mig = load_migration_robot_files(new_repo, mig_parent_code, sel_report)
        py_content_v2 = loaded_mig["py_content"]
        sql_content_v2 = loaded_mig["sql_content"]

        has_py = bool(py_content_v2.strip())
        has_sql = bool(sql_content_v2.strip())

        db_mig_info = get_migration_db_info(sel_report, engine) if (db_connected and engine is not None) else None
        if db_mig_info:
            st.info(
                f"📊 **Metadatos en BD:** Nombre: *{db_mig_info.get('name', 'N/A')}* | "
                f"Storage Table: `{db_mig_info.get('storage_table', 'N/A')}` | "
                f"Conversion Factor en BD: `{db_mig_info.get('conversion_factor', 'N/A')}` | "
                f"Decimal Separator: `{db_mig_info.get('decimal_separator', 'N/A')}`"
            )

        col_st1, col_st2, col_st3, col_st4 = st.columns(4)
        col_st1.metric("Familia", mig_parent_code)
        col_st2.metric("Reporte", sel_report)
        col_st3.metric("Robot .py", "🟢 Presente" if has_py else "🔴 Pendiente")
        col_st4.metric("DDL .sql", "🟢 Presente" if has_sql else "🔴 Pendiente")

        tab_vm_code, tab_vm_deploy = st.tabs([
            "📄 1. Previsualizar / Editar Código (.sql & .py)",
            "🚀 2. Guardar & Desplegar al Servidor"
        ])

        with tab_vm_code:
            st.subheader(f"Archivos de Migración para `{sel_report}` en `models/migration/{mig_parent_code}/`")
            col_vpr1, col_vpr2 = st.columns(2)
            with col_vpr1:
                st.markdown(f"**DDL SQL:** `{sel_report}.sql`")
                sql_input_v2 = st.text_area("Contenido SQL DDL:", value=sql_content_v2 if has_sql else "-- DDL SQL para tabla de PostgreSQL\n", height=380, key=f"ta_sql_v2_{sel_report}")
            with col_vpr2:
                st.markdown(f"**Robot Python:** `{sel_report}.py`")
                py_input_v2 = st.text_area("Contenido Python del Robot:", value=py_content_v2 if has_py else "# Robot de migración a PostgreSQL\n", height=380, key=f"ta_py_v2_{sel_report}")

            if st.button(f"💾 Guardar Archivos en models/migration/{mig_parent_code}/", type="primary", key=f"btn_save_v2_mig_{sel_report}"):
                saved_sql, saved_py = save_migration_files(
                    repo_path=new_repo,
                    parent_code=mig_parent_code,
                    report_code=sel_report,
                    sql_content=sql_input_v2,
                    py_content=py_input_v2
                )
                st.success(f"✨ Archivos guardados exitosamente:\n- `{saved_sql}`\n- `{saved_py}`")
                st.rerun()

        with tab_vm_deploy:
            st.subheader(f"Despliegue y Ejecución en Servidor para `{mig_parent_code}`")
            col_vd1, col_vd2 = st.columns(2)
            with col_vd1:
                dep_mig_host = st.text_input("Host Servidor:", value=DEFAULT_SSH_HOST, key=f"v2_dep_mig_host_{sel_report}")
                dep_mig_user = st.text_input("Usuario SSH:", value=DEFAULT_SSH_USER, key=f"v2_dep_mig_user_{sel_report}")
            with col_vd2:
                dep_mig_port = st.number_input("Puerto SSH:", value=DEFAULT_SSH_PORT, key=f"v2_dep_mig_port_{sel_report}")
                mig_ssh_pass_v2 = st.text_input("Contraseña SSH (datax-pds):", value=DEFAULT_SSH_PASS, type="password", key=f"v2_mig_ssh_pass_{sel_report}")

            if st.button(f"🚀 Desplegar {mig_parent_code} y Generar DAG en Servidor", type="primary", use_container_width=True, key=f"btn_dep_v2_mig_{sel_report}"):
                if not mig_ssh_pass_v2:
                    st.error("Ingresa la contraseña de SSH para desplegar.")
                else:
                    local_mig_dir = os.path.join(new_repo, "models", "migration", mig_parent_code)
                    if not os.path.isdir(local_mig_dir):
                        st.error(f"No existe la carpeta local `{local_mig_dir}`. Guarda los archivos en el paso 1 primero.")
                    else:
                        with st.spinner("Desplegando en el servidor..."):
                            deploy_res = deploy_robot_to_server(
                                host=dep_mig_host,
                                port=int(dep_mig_port),
                                username=dep_mig_user,
                                password=mig_ssh_pass_v2,
                                process_type="migration",
                                robot_code=mig_parent_code,
                                local_dir=local_mig_dir,
                                generate_dag=True
                            )
                        if deploy_res["success"]:
                            show_deploy_success_banner(mig_parent_code, process_type="Robot de Migración", dag_id=mig_parent_code)
                        else:
                            st.error(f"Error en despliegue: {deploy_res['error']}")
                        with st.expander("Ver logs de despliegue"):
                            st.text("\n".join(deploy_res["logs"]))

            st.markdown("---")
            st.markdown("#### ⚡ Disparar DAG en Airflow")
            st.caption("Ejecuta el DAG de migración en Airflow con la última conversión registrada o parámetros manuales.")

            latest_conv_v2 = get_latest_conversion_for_report(sel_report, engine) if (db_connected and engine is not None) else None
            if latest_conv_v2:
                st.info(
                    f"🎯 **Última Conversión detectada en BD:** ID `{latest_conv_v2['id_conversion']}` | "
                    f"Corte: **`{latest_conv_v2['converted_to']}`**\n\n"
                    f"📁 Archivo: `{latest_conv_v2['conversion_path']}`"
                )
                def_conv_id_v2 = latest_conv_v2["id_conversion"]
                def_conv_path_v2 = latest_conv_v2["conversion_path"]
            else:
                def_conv_id_v2 = 1
                parts = mig_parent_code.split("_")
                c_tag = parts[1] if len(parts) > 1 else "BO"
                def_conv_path_v2 = f"/mnt/datos1/data_process/{c_tag}/{mig_parent_code.replace('M_', 'D_')}/{sel_report}.sqlite"

            col_vmt1, col_vmt2 = st.columns(2)
            with col_vmt1:
                trig_code_v2 = st.text_input("Código reporte (--conf 'code'):", value=sel_report, key=f"v2_trig_code_{sel_report}")
                trig_id_v2 = st.number_input("ID conversión (--conf 'id_conversion'):", value=def_conv_id_v2, step=1, key=f"v2_trig_id_{sel_report}")
            with col_vmt2:
                trig_path_v2 = st.text_input("Ruta SQLite (--conf 'conversion_path'):", value=def_conv_path_v2, key=f"v2_trig_path_{sel_report}")

            if st.button(f"▶️ Disparar DAG {mig_parent_code} en Airflow", use_container_width=True, key=f"btn_trig_v2_mig_{sel_report}"):
                if not mig_ssh_pass_v2:
                    st.error("Ingresa la contraseña de SSH arriba para conectar al servidor.")
                else:
                    conf_payload_v2 = {
                        "code": trig_code_v2,
                        "id_conversion": int(trig_id_v2),
                        "conversion_path": trig_path_v2
                    }
                    corte_v2_str = f" con corte {latest_conv_v2['converted_to']}" if latest_conv_v2 else ""
                    with st.spinner(f"Disparando DAG {mig_parent_code} en Airflow worker{corte_v2_str}..."):
                        trig_res_v2 = trigger_dag_on_server(
                            host=dep_mig_host,
                            port=int(dep_mig_port),
                            username=dep_mig_user,
                            password=mig_ssh_pass_v2,
                            dag_id=mig_parent_code,
                            conf=conf_payload_v2
                        )
                    if trig_res_v2["success"]:
                        st.success(f"🎉 DAG `{mig_parent_code}` disparado exitosamente{corte_v2_str}!")
                    else:
                        st.warning("El comando terminó con advertencias o error.")
                    with st.expander("Ver logs de disparo de Airflow", expanded=True):
                        st.code(trig_res_v2["output"] or "Sin salida de terminal.")

# elif "Migración por Lote" in mode:
#     st.header("📊 Migración Masiva por Lote (Batch)")
#     st.caption("Migra múltiples robots de descarga o conversión de una sola vez.")
# 
#     batch_type = st.radio("Tipo de proceso a migrar en lote:", ["Descarga", "Conversión"], horizontal=True)
# 
#     if batch_type == "Descarga":
#         dl_robots = scan_old_download_robots(old_repo)
#         st.write(f"Total robots encontrados en repo antiguo: **{len(dl_robots)}**")
# 
#         if st.button("🚀 Iniciar Migración por Lote de Descarga", type="primary"):
#             progress_bar = st.progress(0)
#             status_text = st.empty()
#             results = []
# 
#             for i, r in enumerate(dl_robots):
#                 code = r["code"]
#                 status_text.write(f"Procesando {i+1}/{len(dl_robots)}: {code}...")
#                 if r["script_file"]:
#                     res = apply_download_migration(
#                         code=code,
#                         source_file=r["script_file"],
#                         new_repo_path=new_repo,
#                         skip_test=True, # Lote rápido
#                         skip_dag=True
#                     )
#                     results.append({"Código": code, "Estado": "🟢 OK" if res["success"] else "⚠️ Revisión"})
#                 progress_bar.progress((i + 1) / len(dl_robots))
# 
#             status_text.success("¡Proceso por lote completado!")
#             safe_dataframe(pd.DataFrame(results), use_container_width=True)



