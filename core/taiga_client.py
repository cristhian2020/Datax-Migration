"""Cliente y utilidades para interactuar con la API REST de Taiga Kanban."""

import os
import re
import requests
from typing import Dict, List, Optional, Tuple, Any

from core.config import (
    DEFAULT_TAIGA_HOST,
    DEFAULT_TAIGA_USER,
    DEFAULT_TAIGA_PASS,
    DEFAULT_TAIGA_PROJECT_SLUG,
)


class TaigaClient:
    """Cliente para la API de Taiga."""

    def __init__(
        self,
        host: str = DEFAULT_TAIGA_HOST,
        username: str = DEFAULT_TAIGA_USER,
        password: str = DEFAULT_TAIGA_PASS,
        project_slug: str = DEFAULT_TAIGA_PROJECT_SLUG,
    ):
        self.host = host.rstrip("/")
        self.username = username
        self.password = password
        self.project_slug = project_slug
        self.auth_token: Optional[str] = None
        self.user_id: Optional[int] = None
        self.project_id: Optional[int] = None
        self.project_name: Optional[str] = None

    def authenticate(self) -> Tuple[bool, str]:
        """Inicia sesión en Taiga y guarda el Bearer token."""
        if not self.username or not self.password:
            return False, "Usuario o contraseña de Taiga no configurados."

        url = f"{self.host}/api/v1/auth"
        try:
            res = requests.post(
                url,
                json={"type": "normal", "username": self.username, "password": self.password},
                timeout=12,
            )
            if res.status_code == 200:
                data = res.json()
                self.auth_token = data.get("auth_token")
                self.user_id = data.get("id")
                return True, "Autenticación exitosa."
            return False, f"Error {res.status_code} al autenticar: {res.text}"
        except Exception as exc:
            return False, f"Excepción de conexión con Taiga: {exc}"

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    def get_project_info(self) -> Tuple[bool, str, Dict[str, Any]]:
        """Obtiene la información del proyecto por slug."""
        if not self.auth_token:
            ok, msg = self.authenticate()
            if not ok:
                return False, msg, {}

        url = f"{self.host}/api/v1/projects/by_slug?slug={self.project_slug}"
        try:
            res = requests.get(url, headers=self._headers(), timeout=12)
            if res.status_code == 200:
                data = res.json()
                self.project_id = data.get("id")
                self.project_name = data.get("name")
                return True, "Proyecto encontrado.", data
            return False, f"Error {res.status_code} al buscar proyecto: {res.text}", {}
        except Exception as exc:
            return False, f"Excepción al buscar proyecto: {exc}", {}

    def get_statuses(self) -> List[Dict[str, Any]]:
        """Lista los estados disponibles para User Stories en el proyecto."""
        if not self.project_id:
            ok, _, _ = self.get_project_info()
            if not ok:
                return []

        url = f"{self.host}/api/v1/userstory-statuses?project={self.project_id}"
        try:
            res = requests.get(url, headers=self._headers(), timeout=12)
            if res.status_code == 200:
                return res.json()
            return []
        except Exception:
            return []

    def get_user_stories(
        self,
        status_name: Optional[str] = None,
        only_assigned_to_me: bool = False,
    ) -> List[Dict[str, Any]]:
        """Obtiene las historias de usuario del proyecto con filtros opcionales."""
        if not self.project_id:
            ok, _, _ = self.get_project_info()
            if not ok:
                return []

        all_stories = []
        page = 1
        try:
            while True:
                url = f"{self.host}/api/v1/userstories?project={self.project_id}&page={page}&page_size=100&order_by=-created_date"
                res = requests.get(url, headers=self._headers(), timeout=15)
                if res.status_code != 200:
                    break
                page_data = res.json()
                if not isinstance(page_data, list) or not page_data:
                    break
                all_stories.extend(page_data)
                if len(page_data) < 100:
                    break
                page += 1

            filtered = []
            for s in all_stories:
                # Filtro por estado
                if status_name and status_name.lower() != "todos":
                    st_name = s.get("status_extra_info", {}).get("name", "")
                    if st_name.lower() != status_name.lower():
                        continue

                # Filtro asignado a mí
                if only_assigned_to_me and self.user_id:
                    assigned = s.get("assigned_to")
                    if assigned != self.user_id:
                        continue

                filtered.append(s)

            # Ordenar: New, In progress, Revision, Ready for test primero, luego Done y Archived
            status_priority = {
                "new": 0,
                "in progress": 1,
                "revision": 2,
                "ready for test": 3,
                "done": 10,
                "archived": 20
            }
            filtered.sort(
                key=lambda item: (
                    status_priority.get(item.get("status_extra_info", {}).get("name", "").lower(), 5),
                    -int(item.get("ref", 0))
                )
            )
            return filtered
        except Exception:
            return all_stories

    def get_story_detail(self, story_ref: int) -> Tuple[bool, str, Dict[str, Any]]:
        """Obtiene el detalle completo de una historia por su número de referencia."""
        if not self.project_id:
            ok, _, _ = self.get_project_info()
            if not ok:
                return False, "No se pudo obtener el proyecto.", {}

        url = f"{self.host}/api/v1/userstories/by_ref?ref={story_ref}&project={self.project_id}"
        try:
            res = requests.get(url, headers=self._headers(), timeout=12)
            if res.status_code == 200:
                data = res.json()
                # Traer adjuntos si los hay
                story_id = data.get("id")
                att_url = f"{self.host}/api/v1/userstories/attachments?object_id={story_id}"
                att_res = requests.get(att_url, headers=self._headers(), timeout=12)
                attachments = att_res.json() if att_res.status_code == 200 else []
                data["all_attachments"] = attachments
                return True, "Detalle obtenido.", data
            return False, f"Error {res.status_code}: {res.text}", {}
        except Exception as exc:
            return False, f"Excepción obteniendo detalle: {exc}", {}

    @staticmethod
    def parse_story_metadata(story_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Extrae de forma limpia todos los campos técnicos estructurados de la descripción."""
        subject = story_dict.get("subject", "")
        desc = story_dict.get("description", "") or ""

        # Identificar tipo de robot
        subject_lower = subject.lower()
        desc_lower = desc.lower()
        if "[conversion]" in subject_lower or "código de reporte" in desc_lower:
            task_type = "conversion"
        elif "[download]" in subject_lower or "código de archivo" in desc_lower or "tipo / descarga" in desc_lower:
            task_type = "download"
        else:
            task_type = "unknown"

        status_info = story_dict.get("status_extra_info") or {}
        assigned_info = story_dict.get("assigned_to_extra_info") or {}
        meta: Dict[str, Any] = {
            "ref": story_dict.get("ref"),
            "subject": subject,
            "task_type": task_type,
            "status": status_info.get("name", "Unknown"),
            "assigned_to": assigned_info.get("full_name_display") or assigned_info.get("username"),
            "raw_description": desc,
            "attachments": story_dict.get("all_attachments", []),
        }

        # Extraer campos con regex
        # Código
        code_match = re.search(r"\*\*(?:Código de reporte|Código de archivo):\*\*\s*`?([A-Za-z0-9_]+)`?", desc, re.IGNORECASE)
        if not code_match:
            # Fallback en subject (ej. D_BO_000000051_01)
            code_match = re.search(r"\(([A-Za-z0-9_]+)\)", subject)
        meta["robot_code"] = code_match.group(1).strip() if code_match else ""

        # Nombre
        name_match = re.search(r"\*\*(?:Nombre reporte|Nombre):\*\*\s*(.+)", desc, re.IGNORECASE)
        meta["report_name"] = name_match.group(1).strip() if name_match else ""

        # URL (para descarga)
        url_match = re.search(r"\*\*URL:\*\*\s*(https?://[^\s]+)", desc, re.IGNORECASE)
        meta["main_url"] = url_match.group(1).strip() if url_match else ""

        # Tipo de Descarga (Tipo I, II, III, IV)
        tipo_match = re.search(r"\*\*Tipo\s*/\s*Descarga:\*\*\s*(.+)", desc, re.IGNORECASE)
        if tipo_match:
            tipo_raw = tipo_match.group(1).strip()
            if "Tipo I" in tipo_raw: meta["download_type"] = "Tipo I"
            elif "Tipo II" in tipo_raw: meta["download_type"] = "Tipo II"
            elif "Tipo III" in tipo_raw: meta["download_type"] = "Tipo III"
            elif "Tipo IV" in tipo_raw: meta["download_type"] = "Tipo IV"
            else: meta["download_type"] = tipo_raw
        else:
            meta["download_type"] = "Tipo I"

        # Página (para conversión)
        page_match = re.search(r"\*\*Página:\*\*\s*(\d+)", desc, re.IGNORECASE)
        meta["page_number"] = int(page_match.group(1)) if page_match else 1

        # Hoja de cálculo específica si se menciona en la descripción
        sheet_match = re.search(r"(?:sobre la hoja|en la hoja|hoja):\s*\*\*?([^\*\n\r]+)\*\*?", desc, re.IGNORECASE)
        meta["target_sheet"] = sheet_match.group(1).strip() if sheet_match else ""

        # Separador decimal
        dec_match = re.search(r"\*\*Separador decimal:\*\*\s*([,\.])", desc, re.IGNORECASE)
        meta["decimal_separator"] = dec_match.group(1) if dec_match else ","

        # Factor de conversión
        fac_match = re.search(r"\*\*Factor de conversión:\*\*\s*(.+)", desc, re.IGNORECASE)
        meta["conversion_factor"] = fac_match.group(1).strip() if fac_match else "None"

        # Palabras clave
        kw_match = re.search(r"\*\*Palabras clave:\*\*\s*(.+)", desc, re.IGNORECASE)
        meta["key_words"] = kw_match.group(1).strip() if kw_match else ""

        # Periodicidad
        per_match = re.search(r"\*\*Periodicidad(?: reporte| archivo)?:\*\*\s*(.+)", desc, re.IGNORECASE)
        meta["periodicity"] = per_match.group(1).strip() if per_match else "Diario"

        # Actualizado a (fecha de referencia)
        up_match = re.search(r"\*\*Actualizado a:\*\*\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", desc, re.IGNORECASE)
        meta["updated_to"] = up_match.group(1).strip() if up_match else "2024-01-01"

        return meta

    def download_attachment(self, attachment_url: str, dest_path: str) -> Tuple[bool, str]:
        """Descarga un archivo adjunto de Taiga en disco local."""
        dest_dir = os.path.dirname(dest_path)
        if dest_dir:
            os.makedirs(dest_dir, exist_ok=True)
        try:
            res = requests.get(attachment_url, headers=self._headers(), stream=True, timeout=30)
            if res.status_code == 200:
                with open(dest_path, "wb") as f:
                    for chunk in res.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return True, f"Descargado exitosamente en {dest_path}"
            return False, f"Error {res.status_code} al descargar adjunto."
        except Exception as exc:
            return False, f"Excepción al descargar: {exc}"
