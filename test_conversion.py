import os
import glob
import sqlite3
import unittest
import pandas as pd
from robot import Robot
from conversion_tools import insert_metadata, verify_values, is_all_string_or_nan

def resolve_file_path() -> str:
    """
    Resuelve la ruta del archivo de muestra:
    1. Si hay archivos soportados en la carpeta 'attachtments/', toma el más reciente.
    2. En su defecto, usa FILE_PATH por defecto.
    """
    default_path = r"./attachtments/202607_BMU_PonderacionActivos D_BO_000000320.XLS"
    attachments_dir = os.path.join(os.path.dirname(__file__), "attachtments")
    if os.path.exists(attachments_dir):
        patterns = ["*.xls", "*.xlsx", "*.pdf", "*.csv"]
        found = []
        for pattern in patterns:
            found.extend(glob.glob(os.path.join(attachments_dir, pattern)))
        found = [f for f in found if not os.path.basename(f).startswith("~$")]
        if found:
            # Seleccionar el archivo modificado más recientemente en attachtments
            found.sort(key=os.path.getmtime, reverse=True)
            return found[0]
    return default_path


FILE_PATH = resolve_file_path()
TEMPLATE_PATH = ""
PAGE_NUMBER = 1
KEY_WORDS = ""
DECIMAL_SEPARATOR = ","
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "output")


class TestConversion(unittest.TestCase):

    def setUp(self):
        self.robot = Robot()

    def test_conversion(self):
        print(f"\n[TestConversion] Usando archivo: {FILE_PATH}")
        # Test data extraction
        report_dict, report_df = self.robot.extraction(
            file_path=FILE_PATH,
            key_words=KEY_WORDS,
            template_path=TEMPLATE_PATH,
            page_number=PAGE_NUMBER
        )
        report_df: pd.DataFrame = report_df

        # Validate report_dict structure and content
        expected_report_keys = {'file_name', 'titles', 'page_number'}
        self.assertIsInstance(report_dict, dict, "The first returned element should be a dictionary")
        self.assertSetEqual(
            set(report_dict.keys()), 
            expected_report_keys,
            f"The report information must contain these keys: {expected_report_keys}"
        )

        # Validate file_name
        self.assertIsInstance(report_dict['file_name'], str, "File name should be a string")
        self.assertTrue(len(report_dict['file_name']) > 0, "File name should not be empty")

        # Validate titles
        self.assertIsInstance(report_dict['titles'], list, "Titles should be a list")

        # Validate page number
        self.assertIsInstance(report_dict['page_number'], int, "Page number should be an integer")
        self.assertTrue(report_dict['page_number'] > 0, "Page number should be greater than zero")

        # Validate report DataFrame
        self.assertIsInstance(report_df, pd.DataFrame, "Report should be a DataFrame")
        self.assertFalse(report_df.empty, "DataFrame should not be empty")
        self.assertTrue(len(report_df.columns) > 2, "DataFrame should have more than two columns")

        # Verify DataFrame values
        verify_values(data_df=report_df)

        # Validate date column
        self.assertEqual("fecha", report_df.columns[-2], f"The 'fecha' column must be the second-to-last column in the DataFrame (found: {report_df.columns[-2]}")
        try:
            report_df['fecha'] = report_df['fecha'].replace('-', pd.NA)
            pd.to_datetime(report_df['fecha'].dropna(), errors='raise', format='%Y-%m-%d')
        except ValueError as e:
            self.fail(f"Date format validation failed: {str(e)}")

        # Validate data type
        self.assertTrue(is_all_string_or_nan(dataframe=report_df), "All columns, except for the 'valor' column, must contain only string or NaN values.")

        # Metadata insertion
        final_df = insert_metadata(dataframe=report_df, titles=report_dict['titles'], file_name=report_dict['file_name'])

        # Export to SQLite for intern inspection
        self._export_to_sqlite(report_dict, final_df)

        # Validate data results
        has_error = self.robot.validate_data_results(
            dataframe=final_df,
            decimal_separator=DECIMAL_SEPARATOR
        )
        self.assertFalse(has_error, "Data validation failed - sums should equal zero")

    def _export_to_sqlite(self, report_dict: dict, final_df: pd.DataFrame):
        """Exporta los resultados a una base SQLite en output/ para inspección del pasante."""
        try:
            os.makedirs(OUTPUT_DIR, exist_ok=True)
            robot_name = self.robot.__class__.__name__
            if robot_name == "Robot":
                # Intentar deducir el código o nombre del archivo
                base_name = os.path.splitext(os.path.basename(FILE_PATH))[0]
                db_filename = f"{base_name}.sqlite"
            else:
                db_filename = f"{robot_name}.sqlite"

            sqlite_path = os.path.join(OUTPUT_DIR, db_filename)
            with sqlite3.connect(sqlite_path) as conn:
                final_df.to_sql("data_melted", conn, if_exists="replace", index=False)

            print(f"[SQLite Export] Base de datos guardada exitosamente en:\n  -> {sqlite_path}")
            print(f"[SQLite Export] Tabla 'data_melted' ({len(final_df)} filas) lista para revisión.")
        except Exception as e:
            print(f"[SQLite Export Warning] No se pudo exportar a SQLite: {e}")


if __name__ == '__main__':
    unittest.main()