"""
Robot de conversión de ejemplo oficial - DATAX Platform.
Muestra de buenas prácticas:
- Clase con exactamente 2 métodos (sin __init__).
- Jerarquía de 5 niveles con nv1 como concepto maestro.
- Fechas dinámicas de corte temporal mensual.
- Reconciliación matemática en validate_data_results().
"""

import os
import re
import calendar
import openpyxl
import pandas as pd
from typing import Tuple

from conversion_tools import to_numeric_datax

try:
    from models.conversion import Conversion_Base
except ImportError:
    Conversion_Base = object


class Robot(Conversion_Base):
    """Robot de conversión para tablas Excel multijerárquicas."""

    def extraction(
        self,
        file_path: str,
        key_words: str = "",
        template_path: str = "",
        page_number: int = 1,
        format: str = "%Y-%m-%d",
    ) -> Tuple[dict, pd.DataFrame]:
        file_name = os.path.basename(file_path)

        # 1. Determinar corte temporal dinámico desde el nombre de archivo
        cut_year, cut_month = 2026, 12
        date_match = re.search(r"(\d{4})-(\d{2})-(\d{2})", file_name)
        if date_match:
            cut_year = int(date_match.group(1))
            cut_month = int(date_match.group(2))

        # 2. Cargar archivo Excel
        wb = openpyxl.load_workbook(file_path, data_only=True)
        sheet_name = "Saldo" if "Saldo" in wb.sheetnames else wb.sheetnames[0]
        ws = wb[sheet_name]

        sheet_title = str(ws.cell(2, 1).value or "Reporte Financiero").strip()

        # 3. Mapear columnas temporales (ejemplo fila 6)
        month_map = {
            "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
        }

        col_dates = {}
        header_row = 6
        for col in range(2, 15):
            val = ws.cell(header_row, col).value
            if not val:
                continue
            h_str = str(val).strip().lower()

            m_yr = re.search(r"([a-z]{3})[-_ ]?(\d{2,4})", h_str)
            if m_yr:
                m_str = m_yr.group(1)
                yr = int(m_yr.group(2))
                if yr < 100:
                    yr += 2000
                m_num = month_map.get(m_str)
            else:
                m_num = month_map.get(h_str[:3])
                yr = cut_year

            if m_num and (yr < cut_year or (yr == cut_year and m_num <= cut_month)):
                last_day = calendar.monthrange(yr, m_num)[1]
                col_dates[col] = f"{yr:04d}-{m_num:02d}-{last_day:02d}"

        records = []

        # Función auxiliar ANIDADA dentro de extraction (Regla de 2 métodos)
        def append_row_records(row_idx, nv1, nv2, nv3, nv4, nv5):
            for col, dt in col_dates.items():
                raw_val = ws.cell(row_idx, col).value
                records.append({
                    "nv1": str(nv1) if nv1 is not None else None,
                    "nv2": str(nv2) if nv2 is not None else None,
                    "nv3": str(nv3) if nv3 is not None else None,
                    "nv4": str(nv4) if nv4 is not None else None,
                    "nv5": str(nv5) if nv5 is not None else None,
                    "fecha": dt,
                    "valor": raw_val,
                })

        # 4. Recorrer filas y aplanar jerarquía
        master_title = "Total Cartera Financiera"
        curr_sector = None
        curr_entity = None

        for r in range(7, ws.max_row + 1):
            cell = ws.cell(r, 1)
            val = cell.value
            if not val:
                continue

            text = str(val).strip()
            if text.lower().startswith(("(p)", "nota", "fuente", "elaboraci")):
                break

            bold = cell.font.bold if cell.font else False
            indent = cell.alignment.indent if cell.alignment else 0
            leading_spaces = len(str(val)) - len(str(val).lstrip(" "))

            # Fila de Total General o Sector
            if bold and indent == 0 and leading_spaces == 0:
                if "total" in text.lower():
                    append_row_records(r, text, None, None, None, None)
                else:
                    curr_sector = text
                    curr_entity = None
                continue

            # Subsector / Entidad
            if bold and indent >= 1:
                curr_entity = text
                continue

            # Instrumentos individuales
            if not bold and curr_sector:
                append_row_records(r, master_title, curr_sector, curr_entity, text, None)

        df_data = pd.DataFrame(records)
        df_data["valor"] = to_numeric_datax(df_data["valor"], decimal_separator=",").round()

        metadata_dict = {
            "file_name": file_name,
            "titles": [sheet_title],
            "page_number": int(page_number),
        }

        return metadata_dict, df_data

    def validate_data_results(
        self,
        dataframe: pd.DataFrame,
        decimal_separator: str = ",",
        TOLERANCE: float = 6.0,
    ) -> bool:
        """Valida que los instrumentos componentes sumen el Total General."""
        try:
            if not isinstance(dataframe, pd.DataFrame) or dataframe.empty:
                return True
            if "valor" not in dataframe.columns or "fecha" not in dataframe.columns:
                return True

            df = dataframe.copy()
            df["valor_num"] = to_numeric_datax(df["valor"], decimal_separator)

            for dt, group in df.groupby("fecha"):
                total_mask = group["nv2"].isna()
                if not total_mask.any():
                    return True

                expected_total = group.loc[total_mask, "valor_num"].iloc[0]
                leaves = group.loc[~total_mask]
                calculated_sum = leaves["valor_num"].sum()

                if abs(calculated_sum - expected_total) > TOLERANCE:
                    return True

            return False
        except Exception:
            return True
