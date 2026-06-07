"""Launcher GUI (D-XXX): ventana para no-tecnicos.

Pensada para ser el entry del `.exe` distribuible. Triple de botones que
cubren los 3 flujos utiles para un usuario final:

  - Renderizar video  ->  `pipeline render <slug>`  (lo mas comun)
  - Abrir Studio       ->  `pipeline studio --no-open`  (iterar keyframes)
  - Abrir carpeta      ->  Explorer en `projects/<slug>/`  (ver el video)

Sin args en la CLI -> esta GUI. Con args -> la CLI (`__main__.py` despacha).

Diseno minimalista: Tkinter (stdlib, no agrega deps al .exe), un Thread por
subprocess para no freezear la UI, y un Text widget con scroll para el log
en vivo. ANSI codes se filtran (el pipeline usa `rich` con colores).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
from pathlib import Path
from tkinter import Tk, StringVar, ttk, Text, Scrollbar, END, DISABLED, NORMAL
from typing import Iterable

import yaml

from . import __version__


# --- descubrimiento del workspace (D-XXX) ------------------------------------

def find_workspace_root() -> Path:
    """Donde estan `config/`, `projects/`, `.env`.

    Prioridad:
      1. `$PIPELINE_WORKSPACE` (para tests/CI)
      2. Carpeta del ejecutable SI tiene `projects/` al lado (señal de bundle
         distribuido: el .exe vive junto a su workspace)
      3. CWD (modo dev con `uv run`)

    Sin la guarda del paso 2, `uv run python -c ...` resuelve a `.venv/Scripts`
    y cree que ese es el workspace. Asi el mismo binario funciona double-click
    (carpeta del .exe) y dev (`uv run pipeline` desde la raiz del repo).
    """
    env = os.environ.get("PIPELINE_WORKSPACE")
    if env:
        return Path(env).resolve()
    exe_dir = Path(sys.executable).resolve().parent
    if (exe_dir / "projects").exists() or (exe_dir / "workspace").exists():
        return exe_dir
    return Path.cwd()


# --- ANSI stripper (la consola de `rich` se imprime en el Text) -------------

_ANSI = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def strip_ansi(s: str) -> str:
    return _ANSI.sub("", s)


# --- lista de proyectos (lo que el humano va a renderizar) -----------------

def list_projects(workspace: Path) -> list[str]:
    projects_dir = workspace / "projects"
    if not projects_dir.exists():
        return []
    return sorted(p.name for p in projects_dir.iterdir() if (p / "project.yaml").exists())


def load_project_meta(workspace: Path, slug: str) -> dict:
    """Lee `title`, `style`, conteo de escenas y duracion del project.yaml."""
    spec = yaml.safe_load((workspace / "projects" / slug / "project.yaml").read_text(encoding="utf-8"))
    scenes = spec.get("scenes") or []
    total = sum(s.get("duration_s") or 0 for s in scenes)
    return {
        "title": spec.get("title") or slug,
        "style": spec.get("style") or "?",
        "n_scenes": len(scenes),
        "duration_s": total,
    }


# --- coroutine de subprocess que streamea al Text widget --------------------

class JobRunner:
    """Lanza un sub-comando `pipeline` y va poniendo stdout/stderr en el log.

    Pensado para correr en un Thread (no async) — Tkinter no es async-friendly
    y `subprocess.Popen` con `bufsize=1` + `readline` es la forma mas simple
    de streamear sin冻结ar la UI.
    """

    def __init__(self, app: "LauncherApp", cmd: list[str], cwd: Path, on_done=None):
        self.app = app
        self.cmd = cmd
        self.cwd = cwd
        self.on_done = on_done
        self.proc: subprocess.Popen | None = None

    def start(self) -> None:
        t = threading.Thread(target=self._run, daemon=True)
        t.start()

    def _run(self) -> None:
        try:
            # env sin PYTHONHOME/prefix raros del venv (el .exe ya viene con todo)
            env = os.environ.copy()
            env.setdefault("PYTHONIOENCODING", "utf-8")
            self.proc = subprocess.Popen(
                self.cmd,
                cwd=str(self.cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert self.proc.stdout is not None
            for line in self.proc.stdout:
                self.app.log(strip_ansi(line.rstrip()))
            rc = self.proc.wait()
            self.app.job_finished(rc, self.on_done)
        except Exception as exc:  # noqa: BLE001 — el GUI no puede morir por un subprocess
            self.app.log(f"[error lanzando subprocess] {type(exc).__name__}: {exc}")
            self.app.job_finished(-1, self.on_done)


# --- la app ----------------------------------------------------------------

class LauncherApp:
    def __init__(self, root: Tk, workspace: Path):
        self.root = root
        self.workspace = workspace
        self.projects = list_projects(workspace)
        if not self.projects:
            self._fatal_sin_proyectos()
            return

        self.slug_var = StringVar(value=self.projects[0])
        self.status_var = StringVar(value="Inactivo")
        self.runner: JobRunner | None = None

        root.title(f"Video Pipeline v{__version__} · {workspace.name}")
        root.geometry("780x600")
        root.minsize(620, 460)

        self._build_ui()
        self._refresh_meta()

    # ---- construccion -----------------------------------------------------

    def _build_ui(self) -> None:
        pad = {"padx": 12, "pady": 6}

        info = ttk.LabelFrame(self.root, text="Proyecto")
        info.pack(fill="x", **pad)
        ttk.Label(info, text="Slug:").grid(row=0, column=0, sticky="w", padx=8, pady=6)
        self.slug_combo = ttk.Combobox(
            info, textvariable=self.slug_var, values=self.projects, state="readonly", width=32,
        )
        self.slug_combo.grid(row=0, column=1, sticky="w", padx=8, pady=6)
        self.slug_combo.bind("<<ComboboxSelected>>", lambda _e: self._refresh_meta())
        self.meta_lbl = ttk.Label(info, text="")
        self.meta_lbl.grid(row=1, column=0, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        actions = ttk.LabelFrame(self.root, text="Acciones")
        actions.pack(fill="x", **pad)
        self.btn_render = ttk.Button(actions, text="Renderizar video", command=self._on_render)
        self.btn_render.grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        self.btn_studio = ttk.Button(actions, text="Abrir Studio (web)", command=self._on_studio)
        self.btn_studio.grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        self.btn_folder = ttk.Button(actions, text="Abrir carpeta del proyecto", command=self._on_folder)
        self.btn_folder.grid(row=0, column=2, padx=8, pady=8, sticky="ew")
        actions.columnconfigure(0, weight=1)
        actions.columnconfigure(1, weight=1)
        actions.columnconfigure(2, weight=1)

        status = ttk.Frame(self.root)
        status.pack(fill="x", **pad)
        ttk.Label(status, text="Estado:").pack(side="left")
        self.status_dot = ttk.Label(status, text="\u25CB", foreground="gray")  # ○
        self.status_dot.pack(side="left", padx=(6, 2))
        self.status_lbl = ttk.Label(status, textvariable=self.status_var)
        self.status_lbl.pack(side="left")

        log_frame = ttk.LabelFrame(self.root, text="Log")
        log_frame.pack(fill="both", expand=True, **pad)
        self.log_text = Text(log_frame, wrap="word", height=14, state=DISABLED,
                            bg="#111", fg="#ddd", insertbackground="#ddd",
                            font=("Consolas", 9))
        self.log_text.pack(side="left", fill="both", expand=True, padx=(6, 0), pady=6)
        scroll = Scrollbar(log_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y", padx=(0, 6), pady=6)
        self.log_text.config(yscrollcommand=scroll.set)

    # ---- metadata del proyecto seleccionado -------------------------------

    def _refresh_meta(self) -> None:
        slug = self.slug_var.get()
        try:
            m = load_project_meta(self.workspace, slug)
            self.meta_lbl.config(
                text=f"titulo: {m['title']}   estilo: {m['style']}   "
                     f"escenas: {m['n_scenes']}   duracion: {m['duration_s']:.0f}s"
            )
        except Exception as exc:  # noqa: BLE001
            self.meta_lbl.config(text=f"[no se pudo leer project.yaml: {exc}]")

    # ---- handlers de los botones -----------------------------------------

    def _on_render(self) -> None:
        self._launch_subcommand(["render", self.slug_var.get()])

    def _on_studio(self) -> None:
        # `studio` es interactivo (servidor web); lo lanzo en segundo plano y
        # anuncio la URL en el log para que el usuario la abra en su browser.
        self._launch_subcommand(["studio", "--no-open"], on_done=lambda rc: self.log(
            f"[studio] proceso termino (rc={rc}). Si no se abrio el browser, "
            f"andá a http://127.0.0.1:8765 manualmente."
        ))

    def _on_folder(self) -> None:
        folder = self.workspace / "projects" / self.slug_var.get()
        if not folder.exists():
            self.log(f"[carpeta no existe: {folder}]")
            return
        # `os.startfile` es Windows; `open` es macOS; `xdg-open` es Linux.
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except Exception as exc:  # noqa: BLE001
            self.log(f"[no se pudo abrir el explorador: {exc}]")
            self.log(f"  ruta: {folder}")

    # ---- subprocess + UI thread ------------------------------------------

    def _launch_subcommand(self, sub: list[str], on_done=None) -> None:
        if self.runner is not None:
            self.log("[ya hay un job corriendo; espera a que termine]")
            return
        cmd = [sys.executable, *sub]
        self.log(f"$ {' '.join(cmd)}")
        self._set_status("Corriendo", "orange")
        self._set_actions_enabled(False)
        self.runner = JobRunner(self, cmd, self.workspace, on_done=on_done)
        self.runner.start()

    def job_finished(self, rc: int, on_done=None) -> None:
        self.runner = None
        self._set_actions_enabled(True)
        if rc == 0:
            self._set_status("Listo", "green")
            out = self.workspace / "projects" / self.slug_var.get() / "runs"
            latest = _latest_run_dir(out)
            if latest:
                self.log(f"[ok] ultimo run: {latest}")
        else:
            self._set_status(f"Error (rc={rc})", "red")
        if on_done is not None:
            try:
                on_done(rc)
            except Exception as exc:  # noqa: BLE001
                self.log(f"[on_done error: {exc}]")

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_dot.config(foreground=color)
        if color == "orange":
            self.status_dot.config(text="\u25CF")  # ●
        elif color == "green":
            self.status_dot.config(text="\u25CF")
        elif color == "red":
            self.status_dot.config(text="\u25D2")  # ◒
        else:
            self.status_dot.config(text="\u25CB")  # ○

    def _set_actions_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for b in (self.btn_render, self.btn_studio, self.btn_folder):
            b.config(state=state)
        self.slug_combo.config(state="readonly" if enabled else "disabled")

    def log(self, msg: str) -> None:
        # Tk no es thread-safe: enrutar al hilo main con `after`.
        self.root.after(0, self._log_now, msg)

    def _log_now(self, msg: str) -> None:
        self.log_text.config(state=NORMAL)
        self.log_text.insert(END, msg + "\n")
        self.log_text.see(END)
        self.log_text.config(state=DISABLED)

    # ---- errores fatales --------------------------------------------------

    def _fatal_sin_proyectos(self) -> None:
        ttk.Label(
            self.root,
            text=f"No encontre proyectos en:\n  {self.workspace / 'projects'}\n\n"
                 f"Ejecuta el .exe desde una carpeta que tenga `projects/<slug>/project.yaml`\n"
                 f"(o copia el bundle con el workspace incluido).",
            justify="left", foreground="red",
        ).pack(padx=20, pady=40)


def _latest_run_dir(runs_dir: Path) -> Path | None:
    if not runs_dir.exists():
        return None
    dirs = sorted(d for d in runs_dir.iterdir() if d.is_dir())
    return dirs[-1] if dirs else None


# --- entry -----------------------------------------------------------------

def launch_gui() -> int:
    workspace = find_workspace_root()
    try:
        root = Tk()
    except Exception as exc:  # noqa: BLE001 — si no hay display (SSH etc.)
        print(f"[launcher] Tk no disponible ({exc}); no puedo abrir la GUI.", file=sys.stderr)
        print(f"[launcher] workspace detectado: {workspace}", file=sys.stderr)
        return 2
    LauncherApp(root, workspace)
    root.mainloop()
    return 0
