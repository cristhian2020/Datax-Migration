"""Cliente para integración con la API de GitHub (Pull Requests de pasantes)."""

import os
from typing import Dict, List, Optional, Tuple
import requests

GITHUB_API_URL = "https://api.github.com"


def _get_headers(token: str) -> Dict[str, str]:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Datax-Migration-Studio",
    }
    if token and token.strip():
        # Bearer o token funcionan en la API de GitHub
        clean_token = token.strip()
        headers["Authorization"] = f"Bearer {clean_token}"
    return headers


def test_github_access(token: str, repo: str = "datax-platform/data-processing-modules") -> Tuple[bool, str, Dict]:
    """Verifica si el token tiene acceso al repositorio especificado."""
    if not token or not token.strip():
        return False, "No se ha proporcionado un GitHub Personal Access Token (PAT).", {}

    url = f"{GITHUB_API_URL}/repos/{repo.strip()}"
    try:
        resp = requests.get(url, headers=_get_headers(token), timeout=25)
        if resp.status_code == 200:
            data = resp.json()
            is_priv = "Privado" if data.get("private") else "Público"
            user_res = requests.get(f"{GITHUB_API_URL}/user", headers=_get_headers(token), timeout=25)
            user_login = user_res.json().get("login", "desconocido") if user_res.status_code == 200 else "autenticado"
            return True, f"Conexión exitosa como @{user_login} a {data.get('full_name')} ({is_priv}).", data
        elif resp.status_code == 401:
            return False, "Error 401: Token inválido o sin autorización en GitHub.", {}
        elif resp.status_code == 404:
            return False, f"Error 404: El repositorio '{repo}' no fue encontrado o el token no tiene permisos de lectura sobre él.", {}
        else:
            return False, f"GitHub API respondió con código {resp.status_code}: {resp.text[:200]}", {}
    except Exception as e:
        return False, f"Error de conexión con GitHub: {str(e)}", {}


def list_pull_requests(
    token: str,
    repo: str = "datax-platform/data-processing-modules",
    state: str = "open",
    search_query: str = ""
) -> List[Dict]:
    """Obtiene la lista de Pull Requests abiertos en el repositorio."""
    if not token or not token.strip():
        return []

    url = f"{GITHUB_API_URL}/repos/{repo.strip()}/pulls"
    params = {
        "state": state,
        "per_page": 100,
        "sort": "updated",
        "direction": "desc"
    }

    try:
        resp = requests.get(url, headers=_get_headers(token), params=params, timeout=15)
        if resp.status_code != 200:
            return []

        prs_data = resp.json()
        results = []
        q = search_query.strip().lower() if search_query else ""

        for p in prs_data:
            title = p.get("title", "")
            branch = p.get("head", {}).get("ref", "")
            author = p.get("user", {}).get("login", "")
            body = p.get("body", "") or ""

            matched = False
            if q:
                if q in title.lower() or q in branch.lower() or q in body.lower():
                    matched = True

            results.append({
                "number": p.get("number"),
                "title": title,
                "author": author,
                "branch": branch,
                "html_url": p.get("html_url", ""),
                "updated_at": p.get("updated_at", ""),
                "created_at": p.get("created_at", ""),
                "matched": matched,
                "head_sha": p.get("head", {}).get("sha", ""),
            })

        # Si hay búsqueda, ordenar primero los que coincidan con el código buscado
        if q:
            results.sort(key=lambda x: not x["matched"])

        return results
    except Exception:
        return []


def get_pr_files(
    token: str,
    repo: str = "datax-platform/data-processing-modules",
    pull_number: int = 0
) -> List[Dict]:
    """Obtiene los archivos modificados en un Pull Request."""
    if not token or not pull_number:
        return []

    url = f"{GITHUB_API_URL}/repos/{repo.strip()}/pulls/{pull_number}/files"
    params = {"per_page": 100}

    try:
        resp = requests.get(url, headers=_get_headers(token), params=params, timeout=15)
        if resp.status_code != 200:
            return []

        files_data = resp.json()
        results = []

        for f in files_data:
            fname = f.get("filename", "")
            lower = fname.lower()
            is_py = lower.endswith(".py")
            is_sample = lower.endswith((".xlsx", ".xls", ".pdf", ".csv", ".zip", ".rar"))

            results.append({
                "filename": fname,
                "status": f.get("status", ""),
                "additions": f.get("additions", 0),
                "deletions": f.get("deletions", 0),
                "raw_url": f.get("raw_url", ""),
                "contents_url": f.get("contents_url", ""),
                "is_py": is_py,
                "is_sample": is_sample,
            })

        return results
    except Exception:
        return []


def download_github_file(token: str, raw_url: str, contents_url: str = "") -> bytes:
    """
    Descarga el contenido de un archivo (código o binario) desde un repositorio privado.
    Intenta primero raw_url con Authorization header, y si falla usa la API de contents.
    """
    headers = _get_headers(token)

    # 1. Intentar descargar mediante raw_url
    if raw_url:
        try:
            r = requests.get(raw_url, headers=headers, timeout=20)
            if r.status_code == 200:
                return r.content
        except Exception:
            pass

    # 2. Fallback: API de contents con Accept raw
    if contents_url:
        try:
            c_headers = dict(headers)
            c_headers["Accept"] = "application/vnd.github.v3.raw"
            r2 = requests.get(contents_url, headers=c_headers, timeout=20)
            if r2.status_code == 200:
                return r2.content
        except Exception:
            pass

    return b""
