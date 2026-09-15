"""Configuraciones y conexiones de la plataforma DataX Migration Studio."""

import os
from sqlalchemy import create_engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_OLD_REPO = r"E:\DATAX\data-processing-platform-nico"
DEFAULT_NEW_REPO = r"E:\DATAX\data-processing-platform-dev-nico"
DEFAULT_DB_HOST = "10.0.0.16"
DEFAULT_DB_PORT = 5434
DEFAULT_DB_USER = "postgres"
DEFAULT_DB_PASS = "datax"
DEFAULT_DB_NAME = "platform_db"

DEFAULT_GITHUB_REPO = os.getenv("GITHUB_REPO", "datax-platform/data-processing-modules")
DEFAULT_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

def get_engine(host=DEFAULT_DB_HOST, port=DEFAULT_DB_PORT, user=DEFAULT_DB_USER, password=DEFAULT_DB_PASS, database=DEFAULT_DB_NAME):
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}")
