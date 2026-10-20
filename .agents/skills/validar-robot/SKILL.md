---
name: validar-robot
description: Ejecuta la suite de verificación automatizada sobre robot.py y diagnostica fallas contra los estándares oficiales de DATAX (Conversión y Descarga Tipos I, II, III y IV).
---

# 🧪 Skill: Validar Robot (DATAX)

Usa esta skill para comprobar si el robot en `robot.py` cumple al 100% las reglas de arquitectura y calidad antes de subirlo a Git.

---

## 🔍 Detección y Verificaciones Automáticas

El validador inspecciona la interfaz implementada en `robot.py` y detecta automáticamente el tipo de robot:

### A. Si es Robot de CONVERSIÓN (`extraction`)
1. **Regla Estricta de 2 Métodos**:
   - Únicamente `extraction()` y `validate_data_results()`.
   - Prohibido `__init__` o métodos auxiliares en `self`.
2. **Control de Fechas**:
   - Detecta si hay fechas fijas quemadas en declaraciones `return`.
3. **Prueba Unitaria**:
   - Ejecuta `test_conversion.py`.
4. **Reconciliación Contable**:
   - Comprueba que `validate_data_results(df)` retorne `False` (sin discrepancias).

### B. Si es Robot de DESCARGA (Tipos I, II, III o IV)
- **Tipo I**: Detecta `get_file_url` y comprueba presencia obligatoria de `compare_files`. Ejecuta `test_download_type_i.py`.
- **Tipo II**: Detecta `verify_download` y comprueba presencia obligatoria de `compare_files`. Ejecuta `test_download_type_ii.py`.
- **Tipo III**: Detecta `check_new_data`. Ejecuta `test_download_type_iii.py`.
- **Tipo IV**: Detecta `get_data`. Ejecuta `test_download_type_iv.py`.

---

## 💻 Comando de Ejecución
```bash
python validate_robot.py
```
O ejecutando el test específico:
```bash
# Conversión:
python -m unittest test_conversion.py

# Descarga:
python -m unittest test_download_type_i.py
python -m unittest test_download_type_ii.py
python -m unittest test_download_type_iii.py
python -m unittest test_download_type_iv.py
```
