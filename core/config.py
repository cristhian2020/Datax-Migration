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
# Fallbacks genéricos para credenciales y host
_GENERIC_HOST = os.getenv("HOST", "10.0.0.16")
_GENERIC_USER = os.getenv("USER", "")
_GENERIC_PASS = os.getenv("PASSWORD", "")

# Base de datos
DEFAULT_DB_HOST = os.getenv("DB_HOST", _GENERIC_HOST)
DEFAULT_DB_PORT = int(os.getenv("DB_PORT", 5434))
DEFAULT_DB_USER = os.getenv("DB_USER", _GENERIC_USER or "postgres")
DEFAULT_DB_PASS = os.getenv("DB_PASS", _GENERIC_PASS or "datax")
DEFAULT_DB_NAME = os.getenv("DB_NAME", "platform_db")

# Servidor Remoto (SSH / Despliegue / Airflow)
DEFAULT_SSH_HOST = os.getenv("SSH_HOST", _GENERIC_HOST)
DEFAULT_SSH_PORT = int(os.getenv("SSH_PORT", os.getenv("PORT", 22)))
DEFAULT_SSH_USER = os.getenv("SSH_USER", os.getenv("SSH_USERNAME", _GENERIC_USER or "datax-pds"))
DEFAULT_SSH_PASS = os.getenv("SSH_PASS", os.getenv("SSH_PASSWORD", _GENERIC_PASS or ""))

DEFAULT_GITHUB_REPO = os.getenv("GITHUB_REPO", "datax-platform/data-processing-modules")
DEFAULT_GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

DEFAULT_GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

def get_engine(host=DEFAULT_DB_HOST, port=DEFAULT_DB_PORT, user=DEFAULT_DB_USER, password=DEFAULT_DB_PASS, database=DEFAULT_DB_NAME):
    return create_engine(f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}")
