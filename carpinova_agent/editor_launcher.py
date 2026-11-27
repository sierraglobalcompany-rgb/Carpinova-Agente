"""Human launcher for the existing local D19 review editor."""
from __future__ import annotations

import argparse
from pathlib import Path
import secrets
import sys

from .room_editor_local import (
    EditorError, _read_d19_with_manifest, _read_input, _serve_session,
)


def _gui_modules():
    try:
        import tkinter as tk
        from tkinter import filedialog, simpledialog
    except (ImportError, RuntimeError):
        return None
    return tk, filedialog, simpledialog


def _choose_input(gui) -> Path | None:
    if gui is None:
        raise EditorError(
            'No está disponible el selector de archivos. Use: '
            'python -m carpinova_agent.editor_launcher --input "ruta.zip" '
            '(para JSON, agregue --y-mm N).'
        )
    tk, filedialog, _simpledialog = gui
    root = tk.Tk()
    root.withdraw()
    try:
        selected = filedialog.askopenfilename(
            title="Abrir proyecto CarpiNova para revisión",
            filetypes=(("Proyecto CarpiNova (D19 ZIP o JSON)", "*.zip *.json"),
                       ("Todos los archivos", "*.*")),
        )
    finally:
        root.destroy()
    return Path(selected) if selected else None


def _ask_section(gui) -> int | None:
    if gui is None:
        return None
    tk, _filedialog, simpledialog = gui
    root = tk.Tk()
    root.withdraw()
    try:
        return simpledialog.askinteger(
            "Cota de sección para revisión",
            "Indica la altura de corte horizontal ya acordada (mm):",
            minvalue=0, maxvalue=20000, parent=root,
        )
    finally:
        root.destroy()


def _output_root(requested: Path | None) -> Path:
    if requested is None:
        repo_root = Path(__file__).resolve().parents[1]
        target = repo_root / "work" / "editor-local"
        for directory in (target.parent, target):
            if directory.exists():
                if (not directory.is_dir() or directory.is_symlink()
                        or (hasattr(directory, "is_junction") and directory.is_junction())):
                    raise EditorError("La carpeta local de salida no es un directorio seguro")
            else:
                directory.mkdir()
            if directory.resolve(strict=True) != directory:
                raise EditorError("La carpeta local de salida no es una ruta real")
        return target.resolve(strict=True)

    if not requested.is_absolute() or requested.is_symlink():
        raise EditorError("--output-root debe ser una carpeta absoluta real")
    if hasattr(requested, "is_junction") and requested.is_junction():
        raise EditorError("--output-root no puede ser una junction")
    if not requested.is_dir() or requested.resolve(strict=True) != requested:
        raise EditorError("--output-root debe existir y ser un directorio real")
    return requested


def _new_session_dir(output_root: Path) -> Path:
    for _attempt in range(8):
        candidate = output_root / f"editor-session-{secrets.token_hex(8)}"
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise EditorError("No se encontró un nombre nuevo para la sesión local")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Abrir una revisión nominal local de CarpiNova")
    parser.add_argument("--input", type=Path, help="Archivo D19 ZIP o solicitud JSON validada")
    parser.add_argument("--y-mm", type=int, help="Cota de sección explícita para entrada JSON")
    parser.add_argument("--output-root", type=Path,
                        help="Carpeta absoluta existente para archivos de esta sesión")
    parser.add_argument("--no-browser", action="store_true",
                        help="Inicia el host y muestra la URL sin abrir navegador")
    args = parser.parse_args(argv)
    gui = _gui_modules()

    try:
        input_path = args.input if args.input is not None else _choose_input(gui)
        if input_path is None:
            return 0
        if input_path.suffix.lower() == ".zip":
            source_request, manifest = _read_d19_with_manifest(input_path)
            y_mm = manifest["section_y_mm"]
            if args.y_mm is not None and args.y_mm != y_mm:
                raise EditorError("Un D19 conserva la sección validada del manifiesto")
        elif input_path.suffix.lower() == ".json":
            source_request = _read_input(input_path)
            y_mm = args.y_mm if args.y_mm is not None else _ask_section(gui)
            if type(y_mm) is not int or not 0 <= y_mm <= 20000:
                raise EditorError("JSON requiere --y-mm explícito o una sección válida en el diálogo")
        else:
            raise EditorError("Seleccione un archivo .zip D19 o .json")

        output_root = _output_root(args.output_root)
        output_dir = _new_session_dir(output_root)
        return _serve_session(source_request, output_dir, y_mm,
                              open_browser=not args.no_browser)
    except (EditorError, OSError, ValueError) as exc:
        print(f"CarpiNova: {str(exc)[:300]}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
