# 🚀 Datax Migration Studio (Web)

Plataforma Web gráfica desarrollada en **Streamlit** para migrar robots de **Descarga (`D_...`)** y **Conversión (`C_...`)** desde la versión antigua (V1) a la **Plataforma V2** (Airflow 3, PostgreSQL 17).

---

## ⚡ Cómo Ejecutar la Plataforma

### Opción 1: Con doble clic (Windows)
Haz doble clic sobre el archivo **`run.bat`**.

### Opción 2: Desde la terminal
```bash
pip install -r requirements.txt
streamlit run app.py
```

La plataforma se abrirá automáticamente en tu navegador en: `http://localhost:8501`.

---

## 🌟 Funcionalidades Incluidas

1. **📥 Robots de Descarga:**
   - Escaneo automático de robots en el repositorio antiguo.
   - Consulta de metadatos en `platform_db`.
   - Comparativa lado a lado (Side-by-Side Diff) del código original vs código refactorizado V2.
   - Simulación (Dry-Run) y botón de migración con test unitario automático y generación del DAG.

2. **🔄 Robots de Conversión:**
   - Detección de familias `C_BO_...` y sub-reportes `D_BO_..._XX`.
   - Copia automática de archivos de muestra (`.pdf`, `.xlsx`) para pruebas unitarias.
   - Configuración automática de la tabla `columns_to_review` en los SQLite (Paso 8 del manual).
   - Generación del DAG de conversión.

3. **🐙 Integración con GitHub (Pull Requests de Pasantes):**
   - Conexión directa al repositorio privado `datax-platform/data-processing-modules`.
   - Consulta y filtrado automático de Pull Requests abiertos por código de reporte.
   - Carga con 1-clic del script `.py` enviado por el pasante.
   - Detección y descarga automática de archivos de muestra (`.xlsx`, `.pdf`, `.csv`) incluidos en el PR.

4. **📊 Migración por Lote (Batch):**
   - Migración desatendida con barra de progreso y tabla de resumen de estados.

5. **☁️ Despliegue al Servidor:**
   - Despliegue seguro por SFTP/SSH y generación automática de DAGs en Docker.
   - Disparo remoto de pruebas en Airflow (`airflow dags trigger`).

---

## 🔑 Configuración de GitHub (Opcional)
Para consultar Pull Requests del repositorio privado de pasantes:
1. Crea un **Personal Access Token (PAT)** en GitHub con permiso de lectura sobre repositorios (`repo`).
2. Ingrésalo en la barra lateral de la app en **🐙 Conexión GitHub** y presiona **💾 Guardar .env**, o colócalo en un archivo `.env` en la raíz:
   ```env
   GITHUB_REPO=datax-platform/data-processing-modules
   GITHUB_TOKEN=ghp_tutokenaqui...
   ```
