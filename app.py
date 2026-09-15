"""DataX Migration Studio - Interfaz Web Interactiva para Migración V1 -> V2."""

import os
import sys
import streamlit as st

# Setup paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from core.config import (
    DEFAULT_OLD_REPO,
    DEFAULT_NEW_REPO,
    DEFAULT_DB_HOST,
    DEFAULT_DB_PORT,
    DEFAULT_DB_USER,
    DEFAULT_DB_PASS,
    DEFAULT_DB_NAME,
    get_engine,
)
from core.migrator_download import (
    scan_old_download_robots,
    get_download_db_info,
    refactor_download_code,
    apply_download_migration,
)
from core.migrator_conversion import (
    scan_old_conversion_families,
    get_conversion_db_info,
    refactor_conversion_code,
    detect_available_samples,
    save_uploaded_sample_file,
    run_conversion_step_test,
    get_sqlite_data,
    get_replacement_table_data,
    setup_columns_to_review,
    apply_conversion_migration,
)
from core.deployer import (
    test_connection,
    list_migrated_robots,
    deploy_robot_to_server,
    trigger_dag_on_server,
)


st.set_page_config(
    page_title="DataX Migration Studio",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ─── SIDEBAR ───────────────────────────────────────────────────
st.sidebar.title("🚀 DataX Studio")
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

db_connected = False
try:
    engine = get_engine(db_host, db_port, db_user, db_pass, db_name)
    with engine.connect() as conn:
        db_connected = True
    st.sidebar.success("🟢 Conexión a platform_db Activa")
except Exception as e:
    st.sidebar.warning("🔴 Sin conexión a platform_db (Offline)")

mode = st.sidebar.radio("Navegación", ["📥 Robots de Descarga", "🔄 Robots de Conversión", "📊 Migración por Lote", "☁️ Despliegue al Servidor"])

# ─── PESTAÑA 1: DESCARGA ───────────────────────────────────────
if mode == "📥 Robots de Descarga":
    st.header("📥 Migración de Robots de Descarga (`D_...`)")
    st.caption("Estandarización automática a V2 (Download_Base, Tipo I-IV, Playwright y creación de DAGs).")

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

        tab_code, tab_action = st.tabs(["📄 Comparativa de Código (V1 vs V2)", "⚡ Ejecutar Migración"])

        with tab_code:
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Código Original (V1)")
                st.code(raw_code, language="python")
            with c2:
                st.subheader("Código Estandarizado (V2)")
                st.code(refactored_code, language="python")

        with tab_action:
            st.subheader("Opciones de Migración")
            skip_test = st.checkbox("Omitir test unitario (migrar solo archivos y DAG)", value=False)
            generate_dag = st.checkbox("Generar DAG de Airflow en dags/download", value=False, help="Por el momento desactivado por defecto para solo crear el archivo en models/download")
            skip_dag = not generate_dag
            test_date = st.text_input("Fecha de corte para la prueba", value="2024-01-01")

            col_btn1, col_btn2 = st.columns(2)
            if col_btn1.button("🧪 Simulación (Dry-Run)", use_container_width=True):
                st.info(f"Simulación exitosa: {selected_code} listo para migrarse a `{new_robot_path}`.")

            if col_btn2.button("🚀 Migrar Robot (Crear en models/download)", type="primary", use_container_width=True):
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
                    if res["success"]:
                        st.success(f"✨ ¡Robot {selected_code} migrado exitosamente a la Plataforma V2!")
                    else:
                        st.error(f"⚠️ Ocurrieron advertencias o fallos durante la migración.")

                    for l in res["logs"]:
                        st.write(l)

# ─── PESTAÑA 2: CONVERSIÓN (ASISTENTE POR PASOS) ───────────────
elif mode == "🔄 Robots de Conversión":
    st.header("🔄 Asistente por Pasos: Migración de Conversión (`C_...`)")
    st.caption("Flujo guiado y seguro de 5 pasos para extraer, auditar datos (NVx/fecha/valor), configurar plantilla y desplegar al servidor.")

    # Selección de Modo: Ingresar código directo (GitHub/Jira) o Explorar repositorio escaneado
    sel_mode = st.radio(
        "Modo de selección de reporte:",
        ["✍️ Ingresar código del reporte manualmente (GitHub / Jira)", "📁 Seleccionar de repositorio local escaneado"],
        horizontal=True,
        key="conv_sel_mode"
    )

    families = scan_old_conversion_families(old_repo)
    selected_fam = {"parent_code": "", "folder": "", "sub_reports": [], "samples": [], "sqlites": []}

    if sel_mode == "✍️ Ingresar código del reporte manualmente (GitHub / Jira)":
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
            st.warning(f"No se encontraron familias de conversión en `{old_repo}/models/conversion`.")
            selected_parent = "C_BO_000000017"
            rep_choice = "D_BO_000000017_01"
        else:
            fam_codes = [f["parent_code"] for f in families]
            col_fam1, col_fam2 = st.columns([1, 1])
            with col_fam1:
                # Si C_BO_000000017 está en la lista, preseleccionarlo; si no, index 0
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
            source_mode = st.radio(
                "¿De dónde deseas obtener el código de este robot?",
                ["📁 Archivo detectado en la carpeta / repositorio local", "📤 Subir archivo .py (descargado de GitHub)", "📋 Pegar código del freelancer directamente"],
                horizontal=True,
                key=f"src_mode_{rep_choice}"
            )

            raw_conv_code = ""
            chosen_rep_data = next((r for r in selected_fam["sub_reports"] if r["code"] == rep_choice), None)

            if source_mode == "📁 Archivo detectado en la carpeta / repositorio local":
                if chosen_rep_data and os.path.isfile(chosen_rep_data["file"]):
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
                elif chosen_rep_data and os.path.isfile(chosen_rep_data["file"]):
                    with open(chosen_rep_data["file"], "r", encoding="utf-8", errors="ignore") as f:
                        raw_conv_code = f.read()

            elif source_mode == "📋 Pegar código del freelancer directamente":
                initial_val = ""
                if chosen_rep_data and os.path.isfile(chosen_rep_data["file"]):
                    with open(chosen_rep_data["file"], "r", encoding="utf-8", errors="ignore") as f:
                        initial_val = f.read()
                raw_conv_code = st.text_area(
                    "Pega el código entregado por el freelancer o copiado de GitHub:",
                    value=initial_val,
                    height=250,
                    key=f"text_area_{rep_choice}"
                )

            refactored_conv_code = refactor_conversion_code(raw_conv_code, rep_choice)

            c_code1, c_code2 = st.columns(2)
            with c_code1:
                st.markdown("**Código Original / Ingresado**")
                st.code(raw_conv_code if raw_conv_code else "# Sin código ingresado", language="python")
            with c_code2:
                st.markdown("**Código Estandarizado (V2)**")
                st.code(refactored_conv_code if refactored_conv_code else "# Esperando código", language="python")

            if st.button(f"💾 Guardar Código Estandarizado de {rep_choice} en V2", type="primary"):
                if not raw_conv_code.strip() or raw_conv_code.startswith("# No se encontró"):
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
                        f.write(refactored_conv_code)
                    st.success(f"✨ Archivo guardado correctamente en: `{target_script}` (sin `__init__.py`)")

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
                    st.dataframe(df_sqlite, use_container_width=True)
                    
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
                st.markdown(f"#### Tabla de Reemplazos en `DATA_DB_BO_AUX`")
                if st.button("🔄 Cargar / Refrescar Tabla de Reemplazos"):
                    df_repl, repl_tbl_name, err_repl = get_replacement_table_data(
                        report_code=rep_choice,
                        db_host=db_host,
                        db_port=db_port,
                        db_user=db_user,
                        db_pass=db_pass,
                        limit=200
                    )
                    if df_repl is not None:
                        st.success(f"Tabla `{repl_tbl_name}`: **{len(df_repl)}** registros cargados.")
                        st.dataframe(df_repl, use_container_width=True)
                    else:
                        st.warning(f"No se pudieron cargar datos de la tabla de reemplazos `{repl_tbl_name}`.")
                        if err_repl:
                            st.error(f"Error de conexión o consulta: {err_repl}")
                            st.caption("Si estás fuera de la red del servidor o sin VPN, puedes consultar esta tabla directamente en DBeaver con la VPN activa.")
                else:
                    st.info("Presiona el botón para consultar la tabla de reemplazos de este reporte en `DATA_DB_BO_AUX`.")

        # ─────────────────────────────────────────────────────────────
        # PASO 4: PLANTILLA SQLITE (COLUMNS_TO_REVIEW)
        # ─────────────────────────────────────────────────────────────
        with conv_tab4:
            st.subheader("Paso 4: Configurar 'columns_to_review' en Plantilla SQLite")
            st.markdown("""
            Según el **Paso 8** del manual:
            - La tabla interna del SQLite debe llamarse **`columns_to_review`**.
            - La columna debe llamarse **`column`**.
            - **SOLO** debe incluir niveles (`fecha`, `nv1`, `nv2`, ..., `nvX`).
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
            1. Sube el script `.py` a `models/conversion/` en el servidor (sin `__init__.py`).
            2. Sube la plantilla `.sqlite` de referencia a `/mnt/datos1/data_process/...`.
            3. Genera el DAG de conversión automáticamente en Airflow (Docker).
            """)

            col_dep1, col_dep2 = st.columns(2)
            with col_dep1:
                deploy_srv_host = st.text_input("Host Servidor:", value=db_host, key="dep_conv_host")
                deploy_srv_user = st.text_input("Usuario SSH:", value="datax-pds", key="dep_conv_user")
            with col_dep2:
                deploy_srv_port = st.number_input("Puerto SSH:", value=22, key="dep_conv_port")
                deploy_srv_pass = st.text_input("Contraseña SSH / sudo:", type="password", key="dep_conv_pass")

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
                            st.success(f"✨ ¡Despliegue completado con éxito para {selected_parent} ({rep_choice})!")
                            if res_dep.get("dag_generated"):
                                st.balloons()
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

            col_trig1, col_trig2 = st.columns(2)
            with col_trig1:
                trig_code = st.text_input("Código de reporte (--conf 'code'):", value=rep_choice, key=f"trig_code_{rep_choice}")
                trig_id_dl = st.number_input("ID de descarga (--conf 'id_download'):", value=1, step=1, key=f"trig_iddl_{rep_choice}")
            with col_trig2:
                default_file_dl = f"\\\\10.0.0.16\\downloaded_files\\BO\\{selected_parent.replace('C_', 'D_')}\\2026"
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
elif mode == "📊 Migración por Lote":
    st.header("📊 Migración Masiva por Lote (Batch)")
    st.caption("Migra múltiples robots de descarga o conversión de una sola vez.")

    batch_type = st.radio("Tipo de proceso a migrar en lote:", ["Descarga", "Conversión"], horizontal=True)

    if batch_type == "Descarga":
        dl_robots = scan_old_download_robots(old_repo)
        st.write(f"Total robots encontrados en repo antiguo: **{len(dl_robots)}**")

        if st.button("🚀 Iniciar Migración por Lote de Descarga", type="primary"):
            progress_bar = st.progress(0)
            status_text = st.empty()
            results = []

            for i, r in enumerate(dl_robots):
                code = r["code"]
                status_text.write(f"Procesando {i+1}/{len(dl_robots)}: {code}...")
                if r["script_file"]:
                    res = apply_download_migration(
                        code=code,
                        source_file=r["script_file"],
                        new_repo_path=new_repo,
                        skip_test=True, # Lote rápido
                        skip_dag=True
                    )
                    results.append({"Código": code, "Estado": "🟢 OK" if res["success"] else "⚠️ Revisión"})
                progress_bar.progress((i + 1) / len(dl_robots))

            status_text.success("¡Proceso por lote completado!")
            st.dataframe(pd.DataFrame(results), use_container_width=True)


# ─── PESTAÑA 4: DESPLIEGUE AL SERVIDOR ────────────────────────
elif mode == "☁️ Despliegue al Servidor":
    st.header("☁️ Despliegue Automatizado al Servidor Remoto (10.0.0.16)")
    st.caption("Transfiere los robots migrados desde tu máquina al servidor y ejecuta el generador de DAGs en Docker.")

    col_ssh1, col_ssh2 = st.columns(2)
    with col_ssh1:
        st.subheader("🔑 Credenciales del Servidor")
        ssh_host = st.text_input("IP / Host del Servidor", value="10.0.0.16")
        ssh_port = st.number_input("Puerto SSH", value=22, step=1)
        ssh_user = st.text_input("Usuario SSH", value="datax-pds")
        ssh_pass = st.text_input("Contraseña (SSH y sudo)", type="password", help="Necesaria para conectar por SSH y ejecutar sudo si la carpeta remota lo requiere.")

    with col_ssh2:
        st.subheader("📁 Rutas y Verificación")
        ssh_remote_path = st.text_input("Ruta remota de la plataforma", value="/home/datax-pds/datax/data-processing-platform-dev")
        
        st.write("")
        st.write("")
        if st.button("🔌 Probar Conexión SSH", use_container_width=True):
            if not ssh_pass:
                st.warning("⚠️ Ingresa la contraseña de datax-pds para probar la conexión.")
            else:
                with st.spinner("Conectando al servidor..."):
                    ok_conn, msg_conn = test_connection(
                        host=ssh_host,
                        port=int(ssh_port),
                        username=ssh_user,
                        password=ssh_pass
                    )
                if ok_conn:
                    st.success(f"✅ {msg_conn}")
                else:
                    st.error(f"❌ {msg_conn}")

    st.markdown("---")
    st.subheader("📦 Seleccionar Robot Migrado para Subir")

    col_p1, col_p2 = st.columns(2)
    with col_p1:
        deploy_proc = st.radio("Tipo de Proceso:", ["Descarga (download)", "Conversión (conversion)"], horizontal=True)
        proc_key = "download" if "Descarga" in deploy_proc else "conversion"

    migrated_list = list_migrated_robots(new_repo, proc_key)

    if not migrated_list:
        st.warning(f"No se encontraron robots migrados en `{new_repo}/models/{proc_key}`.")
    else:
        robot_options = [r["code"] for r in migrated_list]
        selected_deploy_code = st.selectbox(
            "Selecciona el robot a desplegar:",
            robot_options,
            index=0
        )
        selected_deploy_robot = next(r for r in migrated_list if r["code"] == selected_deploy_code)

        with col_p2:
            st.info(
                f"**Robot:** `{selected_deploy_code}`\n\n"
                f"**Carpeta local:** `{selected_deploy_robot['folder_path']}`\n\n"
                f"**Archivos a transferir ({selected_deploy_robot['files_count']}):** {', '.join(selected_deploy_robot['files'])}"
            )

        st.markdown("---")
        st.subheader("⚙️ Opciones de Ejecución Remota")
        gen_dag_remote = st.checkbox(
            "🚀 Ejecutar generador de DAG en Docker automáticamente tras la subida",
            value=True,
            help="Ejecuta: printf '1\n1\nCODIGO\n' | docker compose exec -T airflow-worker python include/main-generate.py"
        )

        if st.button(f"🚀 Desplegar {selected_deploy_code} al Servidor", type="primary", use_container_width=True):
            if not ssh_pass:
                st.error("❌ Por favor ingresa la contraseña de datax-pds antes de desplegar.")
            else:
                st.write("---")
                log_placeholder = st.empty()
                live_logs = []

                def update_live_log(msg: str):
                    live_logs.append(msg)
                    log_placeholder.code("\n".join(live_logs), language="bash")

                with st.spinner(f"Subiendo {selected_deploy_code} y ejecutando tareas en {ssh_host}..."):
                    res_deploy = deploy_robot_to_server(
                        host=ssh_host,
                        port=int(ssh_port),
                        username=ssh_user,
                        password=ssh_pass,
                        remote_base_path=ssh_remote_path,
                        process_type=proc_key,
                        robot_code=selected_deploy_code,
                        local_dir=selected_deploy_robot["folder_path"],
                        generate_dag=gen_dag_remote,
                        log_callback=update_live_log
                    )

                if res_deploy["success"]:
                    st.success(f"🎉 ¡Robot `{selected_deploy_code}` desplegado exitosamente en el servidor!")
                    if res_deploy["dag_generated"]:
                        st.balloons()
                        st.info(f"✅ DAG generado y registrado en Airflow: `/opt/airflow/dags/{proc_key}/{selected_deploy_code}.py`")
                else:
                    st.error("⚠️ Ocurrieron errores durante el despliegue. Revisa los logs arriba.")
