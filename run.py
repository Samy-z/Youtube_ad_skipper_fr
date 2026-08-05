"""Lanceur double-cliquable : demarre skipper.py sans ouvrir de terminal.

Compile en run.exe (voir build_exe.py). Volontairement mince : il lance le vrai
script avec le Python du systeme au lieu de tout embarquer. L'executable reste
donc petit, et skipper.py demeure la seule source de verite -- modifier le
script suffit, sans recompiler.

Les arguments sont transmis tels quels, donc `run.exe --dry-run` fonctionne.
"""

from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
from pathlib import Path


def base_dir() -> Path:
    """Dossier de l'executable une fois compile, du script sinon."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def find_python() -> list[str] | None:
    """Commande Python utilisable, ou None s'il n'y en a pas.

    `py` est essaye en second : le lanceur officiel Windows fonctionne meme
    quand `python` renvoie vers le raccourci du Microsoft Store.
    """
    for command in (["python"], ["py", "-3"]):
        found = shutil.which(command[0])
        if not found:
            continue
        try:
            probe = subprocess.run([found, *command[1:], "--version"],
                                   capture_output=True, timeout=15)
        except Exception:
            continue
        if probe.returncode == 0:
            return [found, *command[1:]]
    return None


def owns_console() -> bool:
    """Vrai si la fenetre disparaitra en sortant, donc lance par double-clic.

    Depuis un terminal deja ouvert, la console compte aussi le shell : inutile
    d'attendre une touche dans ce cas.
    """
    try:
        buffer = (ctypes.c_uint * 4)()
        count = ctypes.windll.kernel32.GetConsoleProcessList(buffer, 4)
        return count <= 1
    except Exception:
        return False


def hold_window(message: str = "Appuyez sur Entree pour fermer...") -> None:
    if owns_console():
        try:
            input(f"\n{message}")
        except (EOFError, KeyboardInterrupt):
            pass


def main() -> int:
    here = base_dir()
    script = here / "skipper.py"

    if not script.exists():
        print(f"skipper.py est introuvable a cote de l'executable ({here}).")
        print("Placez run.exe dans le dossier du projet.")
        hold_window()
        return 1

    python = find_python()
    if python is None:
        print("Aucun Python utilisable n'a ete trouve dans le PATH.")
        print("Installez Python 3.10 ou plus recent depuis https://python.org")
        print("en cochant \"Add Python to PATH\", puis relancez.")
        hold_window()
        return 1

    try:
        code = subprocess.call([*python, str(script), *sys.argv[1:]], cwd=str(here))
    except KeyboardInterrupt:
        # Ctrl+C touche aussi ce lanceur ; skipper.py s'est deja arrete
        # proprement, inutile d'afficher une trace par-dessus.
        code = 0

    hold_window()
    return code


if __name__ == "__main__":
    sys.exit(main())
