"""Configuraciones y conexiones de la plataforma DataX Migration Studio."""

import os
from sqlalchemy import create_engine

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DEFAULT_OLD_REPO = os.getenv("OLD_REPO_PATH", r"tu ruta")
DEFAULT_NEW_REPO = os.getenv("NEW_REPO_PATH", r"tu ruta")
DEFAULT_DB_HOST = os.getenv("DB_HOST", "10.0.0.16")
DEFAULT_DB_PORT = int(os.getenv("DB_PORT", 5434))
DEFAULT_DB_USER = os.getenv("DB_USER", "postgres")
DEFAULT_DB_PASS = os.getenv("DB_PASS", "datax")
DEFAULT_DB_NAME = os.getenv("DB_NAME", "platform_db")

DEFAULT_GITHUB_REPO = os.getenv("GITHUB_REPO", "datax-platform/data-processing-modules")
DEFAULT_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DEFAULT_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_engine(host=DEFAULT_DB_HOST, port=DEFAULT_DB_PORT, user=DEFAULT_DB_USER, password=DEFAULT_DB_PASS, database=DEFAULT_DB_NAME):
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}")
