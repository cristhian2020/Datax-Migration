# 📘 Guía Completa de Desarrollo de Robots de Conversión

Bienvenido al equipo de ingeniería de datos de DATAX. Esta guía detalla cómo transformar archivos tabulares o reportes desestructurados (Excel y PDF) en el estándar oficial de datos de la plataforma.

---

## 1. ¿Qué es una Tabla "Melted" o Vertical?
En DATAX no almacenamos tablas con matrices de doble entrada. Toda tabla debe ser des-pivotada a formato vertical:

### Formato Original (Horizontal):
| Entidad | Caja de Ahorro | Plazo 30 días | Plazo 60 días |
|---|---|---|---|
| Banco A | 2.5% | 4.0% | 5.0% |

### Formato DATAX (Vertical / Melted):
| nv1 | nv2 | nv3 | fecha | valor |
|---|---|---|---|---|
| Tasas Activas | Banco A | Caja de Ahorro | 2026-09-06 | 2.5 |
| Tasas Activas | Banco A | Plazo 30 días | 2026-09-06 | 4.0 |
| Tasas Activas | Banco A | Plazo 60 días | 2026-09-06 | 5.0 |

---

## 2. Esquema Jerárquico de Niveles y Colores
- **`nv1` (Naranja)**: Concepto maestro / Total general que unifica el reporte.
- **`nv2` (Celeste)**: Sectores o agrupadores mayores.
- **`nv3` (Verde)**: Entidades o subsectores institucionales.
- **`nv4` (Amarillo)**: Instrumentos o tipos de valor individuales.
- **`nv5` (Sub-instrumento)**: Nivel de detalle específico cuando aplica.

---

## 3. Regla Estricta de la Clase Robot
La clase `Robot` debe tener **única y exclusivamente dos métodos**:
1. `extraction()`
2. `validate_data_results()`

❌ **Sin `__init__`**: Cualquier función de soporte se define anidada dentro de `extraction()`.

---

## 4. Reconciliación Matemática (`validate_data_results`)
La función debe comprobar por cada fecha de corte que:
$$\sum 	ext{Componentes (Amarillos)} = 	ext{Total General (Naranja)}$$
- Retorna `False` cuando los datos cuadran dentro de la tolerancia admitida (`TOLERANCE=6.0`).
- Retorna `True` si existe una discrepancia o error numérico.

---

## 5. Catálogo de Errores Comunes ("Gotchas")

### ❌ Gotcha 1: Fallback con fecha quemada
```python
# INCORRECTO:
except Exception:
    return "2026-08-16"  # ¡NUNCA! Rompe la detección de reportes nuevos en Airflow.

# CORRECTO:
m = re.search(r'(\d{4}-\d{2}-\d{2})', file_name)
if m:
    return m.group(1)
```

### ❌ Gotcha 2: Importar desde plataformas externas
```python
# INCORRECTO:
from models.conversion.tools.conversion_tools import to_numeric_datax

# CORRECTO (Autosuficiente en data-processing-modules):
from conversion_tools import to_numeric_datax
```
