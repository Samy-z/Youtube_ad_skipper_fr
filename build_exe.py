"""Compile run.py en run.exe, a cote du projet.

    python build_exe.py

Seul le lanceur est embarque, pas le projet : inutile de recompiler apres avoir
modifie skipper.py ou detect.py. Les fichiers intermediaires sont ecrits dans un
dossier temporaire puis supprimes, pour ne laisser que run.exe.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller est absent. Installez-le avec :")
        print("    python -m pip install pyinstaller")
        return 1

    with tempfile.TemporaryDirectory(prefix="skipper-build-") as scratch:
        command = [
            sys.executable, "-m", "PyInstaller",
            "--onefile",            # un seul fichier a deplacer
            "--console",            # la fenetre affiche les detections
            "--name", "run",
            "--distpath", str(HERE),
            "--workpath", str(Path(scratch) / "work"),
            "--specpath", str(Path(scratch) / "spec"),
            "--noconfirm",
            str(HERE / "run.py"),
        ]
        print(" ".join(command), "\n")
        result = subprocess.call(command)

    if result != 0:
        print("\nLa compilation a echoue.")
        return result

    exe = HERE / "run.exe"
    if not exe.exists():
        print("\nrun.exe est introuvable apres la compilation.")
        return 1

    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)
    print(f"\nrun.exe cree ({exe.stat().st_size / 1_048_576:.1f} Mo) dans {HERE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
