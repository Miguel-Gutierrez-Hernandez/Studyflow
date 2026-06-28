"""
utils/proyecto.py — Gestión de la estructura de carpetas de cada proyecto.

Estructura de un proyecto:
    proyectos/
    └── nombre_proyecto/
        ├── proyecto.json        ← metadatos (nombre, fecha, documentos procesados)
        ├── documentos/          ← archivos originales subidos por el usuario
        ├── procesado/           ← texto extraído y transcripciones (.txt por archivo)
        └── output/
            └── index.html       ← HTML final generado
"""

import json
import shutil
from datetime import datetime
from pathlib import Path

from config import PROYECTOS_DIR


class Proyecto:
    """Representa un proyecto de estudio en disco."""

    def __init__(self, nombre: str):
        self.nombre = nombre
        self.ruta: Path = PROYECTOS_DIR / nombre
        self.ruta_documentos: Path = self.ruta / "documentos"
        self.ruta_procesado: Path = self.ruta / "procesado"
        self.ruta_output: Path = self.ruta / "output"
        self.ruta_meta: Path = self.ruta / "proyecto.json"

    # ── Ciclo de vida ─────────────────────────────────────────────────────────

    def crear(self, sobrescribir: bool = False) -> "Proyecto":
        """Crea la estructura de carpetas en disco."""
        if self.ruta.exists() and not sobrescribir:
            raise FileExistsError(
                f"El proyecto '{self.nombre}' ya existe en {self.ruta}. "
                "Usa sobrescribir=True para forzar."
            )
        for carpeta in (self.ruta_documentos, self.ruta_procesado, self.ruta_output):
            carpeta.mkdir(parents=True, exist_ok=True)
        self._guardar_meta()
        return self

    def eliminar(self) -> None:
        """Elimina el proyecto completo del disco. Irreversible."""
        if self.ruta.exists():
            shutil.rmtree(self.ruta)

    # ── Documentos ────────────────────────────────────────────────────────────

    def añadir_documento(self, ruta_origen: Path) -> Path:
        """
        Copia un archivo a la carpeta documentos/ del proyecto.
        Devuelve la ruta destino dentro del proyecto.
        """
        ruta_origen = Path(ruta_origen)
        if not ruta_origen.exists():
            raise FileNotFoundError(f"No se encuentra el archivo: {ruta_origen}")
        destino = self.ruta_documentos / ruta_origen.name
        shutil.copy2(ruta_origen, destino)
        self._registrar_documento(ruta_origen.name)
        return destino

    def documentos(self) -> list[Path]:
        """Lista todos los archivos en documentos/."""
        if not self.ruta_documentos.exists():
            return []
        return [p for p in self.ruta_documentos.iterdir() if p.is_file()]

    def procesados(self) -> list[Path]:
        """Lista todos los archivos de texto extraído en procesado/."""
        if not self.ruta_procesado.exists():
            return []
        return [p for p in self.ruta_procesado.iterdir() if p.suffix == ".txt"]

    # ── Output ────────────────────────────────────────────────────────────────

    def guardar_html(self, html: str) -> Path:
        """Escribe el HTML generado en output/index.html."""
        self.ruta_output.mkdir(parents=True, exist_ok=True)
        ruta_html = self.ruta_output / "index.html"
        ruta_html.write_text(html, encoding="utf-8")
        self._actualizar_meta({"ultimo_html": datetime.now().isoformat()})
        return ruta_html

    def html_existe(self) -> bool:
        return (self.ruta_output / "index.html").exists()

    def leer_html(self) -> str | None:
        ruta = self.ruta_output / "index.html"
        return ruta.read_text(encoding="utf-8") if ruta.exists() else None

    # ── Metadatos ─────────────────────────────────────────────────────────────

    def _guardar_meta(self) -> None:
        meta = {
            "nombre": self.nombre,
            "creado": datetime.now().isoformat(),
            "documentos": [],
            "ultimo_html": None,
        }
        self.ruta_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def _actualizar_meta(self, cambios: dict) -> None:
        meta = self._leer_meta()
        meta.update(cambios)
        self.ruta_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def _registrar_documento(self, nombre: str) -> None:
        meta = self._leer_meta()
        if nombre not in meta.get("documentos", []):
            meta.setdefault("documentos", []).append(nombre)
        self.ruta_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    def _leer_meta(self) -> dict:
        if self.ruta_meta.exists():
            return json.loads(self.ruta_meta.read_text(encoding="utf-8"))
        return {}

    def meta(self) -> dict:
        return self._leer_meta()

    def __repr__(self) -> str:
        return f"<Proyecto '{self.nombre}' en {self.ruta}>"


# ── Funciones de utilidad ─────────────────────────────────────────────────────

def listar_proyectos() -> list[Proyecto]:
    """Devuelve todos los proyectos existentes en PROYECTOS_DIR."""
    if not PROYECTOS_DIR.exists():
        return []
    return [
        Proyecto(p.name)
        for p in PROYECTOS_DIR.iterdir()
        if p.is_dir() and (p / "proyecto.json").exists()
    ]


def cargar_proyecto(nombre: str) -> Proyecto:
    """Carga un proyecto existente. Lanza error si no existe."""
    proyecto = Proyecto(nombre)
    if not proyecto.ruta.exists():
        raise FileNotFoundError(
            f"El proyecto '{nombre}' no existe en {PROYECTOS_DIR}. "
            "Crea uno nuevo con Proyecto(nombre).crear()"
        )
    return proyecto
