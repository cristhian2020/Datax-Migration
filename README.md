# 🚀 DataX Migration Studio (Web)

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

3. **📊 Migración por Lote (Batch):**
   - Migración desatendida con barra de progreso y tabla de resumen de estados.
