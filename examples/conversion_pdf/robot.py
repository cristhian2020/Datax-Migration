import os
import re
import pandas as pd
import pdfplumber
from conversion_tools import to_numeric_datax

class Robot:
    """
    Robot de conversión de ejemplo para archivos PDF usando pdfplumber.
    """

    def extraction(self, file_path, key_words, template_path="", page_number=1, format='%Y-%m-%d'):
        file_name = os.path.basename(file_path)

        # 1. Extraer fecha desde el nombre de archivo
        m = re.search(r'(\d{4}-\d{2}-\d{2})', file_name)
        fecha = m.group(1) if m else pd.Timestamp.now().strftime(format)

        # 2. Extraer tabla con pdfplumber
        records = []
        with pdfplumber.open(file_path) as pdf:
            page_idx = max(0, int(page_number) - 1)
            page = pdf.pages[page_idx]
            table = page.extract_table()

            if table:
                for row in table[1:]: # Ignorar encabezado
                    if not row or not row[0]:
                        continue
                    categoria = str(row[0]).strip()
                    valor_mn = row[1]
                    records.append({
                        "nv1": "Cartera de Inversiones",
                        "nv2": categoria,
                        "fecha": fecha,
                        "valor": valor_mn
                    })

        df_melted = pd.DataFrame(records)
        df_melted['valor'] = to_numeric_datax(df_melted['valor'], decimal_separator='.')

        metadata_dict = {
            "file_name": file_name,
            "titles": ["Boletín Diario de Inversiones"],
            "page_number": int(page_number) if page_number else 1
        }

        return metadata_dict, df_melted

    def validate_data_results(self, dataframe, decimal_separator=".", TOLERANCE=6.0):
        return False
