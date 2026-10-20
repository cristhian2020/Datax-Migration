"""Validador y ejecutor dinámico para el bucle de auto-corrección de robots generados."""

import os
import sys
import types
import tempfile
import traceback
import importlib.util
from typing import Dict, Any, Tuple, Optional
import pandas as pd


def _ensure_platform_mock_modules():
    """Garantiza que los imports oficiales de data-processing-platform funcionen durante el testeo dinámico."""
    try:
        import conversion_tools
    except ImportError:
        conversion_tools = None

    try:
        import download_tools
    except ImportError:
        download_tools = None

    class Conversion_Base:
        pass

    class Download_Base:
        pass

    for mod_name in ["models", "models.conversion", "models.conversion.tools", "models.download", "models.download.tools"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)

    cb_mod = types.ModuleType("models.conversion.Conversion_Base")
    cb_mod.Conversion_Base = Conversion_Base
    sys.modules["models.conversion.Conversion_Base"] = cb_mod

    if conversion_tools:
        sys.modules["models.conversion.tools.conversion_tools"] = conversion_tools

    db_mod = types.ModuleType("models.download.Download_Base")
    db_mod.Download_Base = Download_Base
    sys.modules["models.download.Download_Base"] = db_mod

    if download_tools:
        sys.modules["models.download.tools.download_tools"] = download_tools


def test_conversion_robot_code(
    code_str: str,
    robot_code: str,
    sample_file_path: str,
    key_words: str = "",
    page_number: int = 1,
    decimal_separator: str = ","
) -> Dict[str, Any]:
    """Ejecuta dinámicamente el código del robot de conversión contra un archivo muestra."""
    _ensure_platform_mock_modules()

    if not os.path.isfile(sample_file_path):
        return {
            "success": False,
            "stage": "precheck",
            "error": f"El archivo muestra '{sample_file_path}' no existe en disco."
        }

    # Guardar en archivo temporal
    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
        tmp_file.write(code_str)
        tmp_path = tmp_file.name

    try:
        # Cargar módulo dinámicamente
        module_name = f"dynamic_robot_{robot_code}"
        spec = importlib.util.spec_from_file_location(module_name, tmp_path)
        if not spec or not spec.loader:
            return {"success": False, "stage": "import", "error": "No se pudo crear spec para el módulo."}

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Buscar la clase Robot o con el nombre del robot_code
        robot_cls = getattr(module, "Robot", None) or getattr(module, robot_code, None)
        if not robot_cls:
            return {
                "success": False,
                "stage": "class_lookup",
                "error": f"No se encontró la clase '{robot_code}' ni el alias 'Robot' en el código generado."
            }

        # Instanciar robot
        robot_instance = robot_cls()

        # Validar métodos requeridos
        if not hasattr(robot_instance, "extraction"):
            return {"success": False, "stage": "methods", "error": "El robot no tiene el método 'extraction'."}
        if not hasattr(robot_instance, "validate_data_results"):
            return {"success": False, "stage": "methods", "error": "El robot no tiene el método 'validate_data_results'."}

        # Ejecutar extraction
        extraction_res = robot_instance.extraction(
            file_path=sample_file_path,
            key_words=key_words,
            page_number=page_number
        )

        if not isinstance(extraction_res, tuple) or len(extraction_res) != 2:
            return {
                "success": False,
                "stage": "extraction_contract",
                "error": f"extraction() debe retornar una tupla (metadata_dict, df_melted). Retornó: {type(extraction_res)}"
            }

        metadata_dict, df_melted = extraction_res

        if not isinstance(metadata_dict, dict) or set(metadata_dict.keys()) != {"titles", "file_name", "page_number"}:
            return {
                "success": False,
                "stage": "metadata_contract",
                "error": f"metadata_dict debe contener exactamente las llaves: {{'titles', 'file_name', 'page_number'}}. Llaves recibidas: {set(metadata_dict.keys()) if isinstance(metadata_dict, dict) else type(metadata_dict)}"
            }

        if not isinstance(metadata_dict.get("titles"), list):
            return {
                "success": False,
                "stage": "metadata_contract",
                "error": "metadata_dict['titles'] debe ser una LISTA de strings (ej: ['Título']). No un string suelto."
            }

        if not isinstance(df_melted, pd.DataFrame):
            return {
                "success": False,
                "stage": "extraction_contract",
                "error": f"df_melted debe ser un pandas DataFrame. Retornó: {type(df_melted)}"
            }

        if df_melted.empty:
            return {
                "success": False,
                "stage": "extraction_data",
                "error": "El DataFrame resultante está vacío (0 filas extraídas)."
            }

        # Comprobar columnas mínimas requeridas: al menos una de nv, fecha y valor
        cols = list(df_melted.columns)
        if "fecha" not in cols or "valor" not in cols:
            return {
                "success": False,
                "stage": "columns",
                "error": f"El DataFrame debe contener las columnas 'fecha' y 'valor'. Columnas encontradas: {cols}"
            }

        # Ejecutar validate_data_results
        val_error = robot_instance.validate_data_results(df_melted, decimal_separator=decimal_separator)
        if val_error:
            return {
                "success": False,
                "stage": "validate_data_results",
                "error": "validate_data_results() retornó True (indicando discrepancias matemáticas o sumas contables erróneas)."
            }

        # Éxito completo
        return {
            "success": True,
            "stage": "completed",
            "metadata": metadata_dict,
            "total_rows": len(df_melted),
            "columns": cols,
            "sample_rows": df_melted.head(10).to_dict(orient="records"),
            "df": df_melted
        }

    except Exception as exc:
        tb_str = traceback.format_exc()
        return {
            "success": False,
            "stage": "runtime",
            "error": f"{exc}\n\nTraceback:\n{tb_str}"
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def validate_download_robot_structure(code_str: str, robot_code: str, download_type: str) -> Dict[str, Any]:
    """Verifica que el código del robot de descarga tenga la estructura y métodos según su tipo."""
    _ensure_platform_mock_modules()

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as tmp_file:
        tmp_file.write(code_str)
        tmp_path = tmp_file.name

    try:
        module_name = f"dynamic_dl_robot_{robot_code}"
        spec = importlib.util.spec_from_file_location(module_name, tmp_path)
        if not spec or not spec.loader:
            return {"success": False, "error": "No se pudo crear spec para el módulo."}

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        robot_cls = getattr(module, "Robot", None) or getattr(module, robot_code, None)
        if not robot_cls:
            return {"success": False, "error": f"No se encontró la clase '{robot_code}' ni el alias 'Robot'."}

        inst = robot_cls()
        if "Tipo I" in download_type:
            required = ["get_file_url", "compare_files"]
        elif "Tipo II" in download_type:
            required = ["verify_download", "compare_files"]
        elif "Tipo III" in download_type:
            required = ["check_new_data"]
        elif "Tipo IV" in download_type:
            required = ["get_data"]
        else:
            required = ["get_file_url"]

        missing = [m for m in required if not hasattr(inst, m)]
        if missing:
            return {
                "success": False,
                "error": f"Al robot de {download_type} le faltan los métodos obligatorios: {missing}"
            }

        return {"success": True, "error": None, "methods": required}

    except Exception as exc:
        tb_str = traceback.format_exc()
        return {"success": False, "error": f"{exc}\n\nTraceback:\n{tb_str}"}
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
