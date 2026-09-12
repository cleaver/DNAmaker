"""Windows SnapGene adapter implementing agent.adapters.SnapGeneService.

Validation belongs to WorkflowManager: ConstructRef contains no validation token.
CLI jobs require SnapGene to be closed. Never kill a user's desktop session.
"""

from __future__ import annotations

import csv
import ctypes
from ctypes import wintypes
from contextlib import contextmanager
import io
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time

from agent.errors import WorkflowError
from agent.models import ConstructRef


_THREAD_LOCK = threading.Lock()
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_FORMATS = {"snapgene": "SnapGene", "genbank": "GenBank - SnapGene", "fasta": "FASTA"}
_EXTENSIONS = {"snapgene": {".dna"}, "genbank": {".gb", ".gbk", ".genbank"}, "fasta": {".fa", ".fas", ".fasta"}}


class DesktopSnapGeneService:
    def __init__(self, workspace: str | Path | None = None, executable: str | Path | None = None,
                 timeout: float = 45, open_timeout: float = 20):
        self.workspace = Path(workspace or Path.cwd()).resolve()
        configured = executable or os.environ.get("SNAPGENE_EXE")
        self.executable = Path(configured or Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "SnapGene/SnapGene.exe")
        if timeout <= 0 or open_timeout <= 0:
            raise ValueError("Timeouts must be positive")
        self.timeout = timeout
        self.open_timeout = open_timeout

    def _check_installation(self):
        if os.name != "nt":
            raise WorkflowError("snapgene_platform_unsupported", "The MVP SnapGene adapter requires Windows.")
        if not self.executable.is_file():
            raise WorkflowError("snapgene_not_found", "Set SNAPGENE_EXE to the installed SnapGene.exe.")

    def _path(self, value: str) -> Path:
        if not value or not isinstance(value, str):
            raise WorkflowError("snapgene_invalid_path", "A nonempty workspace-relative path is required.")
        path = (self.workspace / value).resolve()
        if not path.is_relative_to(self.workspace):
            raise WorkflowError("snapgene_invalid_path", "Artifact paths must stay inside the workspace.")
        return path

    def _input(self, construct: ConstructRef) -> Path:
        if construct.format not in _FORMATS:
            raise WorkflowError("snapgene_format_unsupported", "Provide GenBank, FASTA, or SnapGene; serialize JSON through the biology adapter first.")
        path = self._path(construct.path)
        if not path.is_file():
            raise WorkflowError("snapgene_input_not_found", f"Input does not exist: {construct.path}")
        self._verify_artifact(path, construct.format)
        return path

    def _output(self, value: str, format: str) -> Path:
        path = self._path(value)
        suffixes = {"png": {".png"}, **_EXTENSIONS}
        if path.suffix.lower() not in suffixes[format]:
            raise WorkflowError("snapgene_invalid_output", f"Output extension must match {format}.")
        if path.exists():
            raise WorkflowError("snapgene_output_exists", f"Choose a new output path: {value}")
        return path

    @staticmethod
    def _verify_artifact(path: Path, format: str):
        if not path.is_file() or path.stat().st_size == 0:
            raise WorkflowError("snapgene_output_missing", "SnapGene did not produce a nonempty artifact.")
        with path.open("rb") as stream:
            header = stream.read(128)
        valid = {
            "snapgene": header.startswith(b"\x09\x00\x00\x00\x0eSnapGene"),
            "genbank": header.lstrip().startswith(b"LOCUS"),
            "fasta": header.lstrip().startswith(b">"),
            "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        }[format]
        if not valid:
            raise WorkflowError("snapgene_invalid_artifact", f"File is not a recognizable {format} artifact: {path.name}")

    def _process_ids(self) -> set[int]:
        result = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {self.executable.name}", "/FO", "CSV", "/NH"],
            capture_output=True, text=True, errors="replace", timeout=10,
            creationflags=_NO_WINDOW,
        )
        if result.returncode:
            raise WorkflowError("snapgene_process_check_failed", "Could not determine whether SnapGene is running.")
        return {int(row[1]) for row in csv.reader(io.StringIO(result.stdout))
                if len(row) > 1 and row[0].casefold() == self.executable.name.casefold() and row[1].isdigit()}

    def _document_windows(self) -> list[dict]:
        """Inspect visible windows belonging to SnapGene; no input injection."""
        pids = self._process_ids()
        windows = []
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        user32.IsWindowVisible.argtypes = [wintypes.HWND]
        user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]

        @callback_type
        def collect(hwnd, _):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value in pids and user32.IsWindowVisible(hwnd):
                text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(hwnd) + 1)
                user32.GetWindowTextW(hwnd, text, len(text))
                if text.value:
                    windows.append({"title": text.value, "pid": pid.value})
            return True

        user32.EnumWindows(collect, 0)
        return windows

    @contextmanager
    def _job(self, *, requires_closed: bool = True):
        self._check_installation()
        if not _THREAD_LOCK.acquire(blocking=False):
            raise WorkflowError("snapgene_busy", "Another SnapGene operation is in progress.")
        try:
            import msvcrt
            # OS releases this byte-range lock even if the process crashes.
            with (self.workspace / ".snapgene.lock").open("a+b") as lock:
                lock.seek(0, 2)
                if lock.tell() == 0:
                    lock.write(b"0")
                    lock.flush()
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                except OSError as error:
                    raise WorkflowError("snapgene_busy", "Another process is using the SnapGene bridge.") from error
                try:
                    if requires_closed and self._process_ids():
                        raise WorkflowError("snapgene_busy", "Save your work and close SnapGene, then retry. Convert and render before opening.")
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        except WorkflowError:
            raise
        except (OSError, subprocess.SubprocessError) as error:
            raise WorkflowError("snapgene_operation_failed", str(error)) from error
        finally:
            _THREAD_LOCK.release()

    def _produce(self, source: Path, destination: Path, format: str, args: list[str]):
        with self._job():
            destination.parent.mkdir(parents=True, exist_ok=True)
            # SnapGene writes to staging; publish only a verified artifact.
            with tempfile.TemporaryDirectory(prefix=".snapgene-", dir=destination.parent) as temp:
                # SnapGene normalizes GenBank to .gbk and FASTA to .fa.
                suffix = {"genbank": ".gbk", "fasta": ".fa", "snapgene": ".dna", "png": ".png"}[format]
                staged = Path(temp) / (destination.stem + suffix)
                command = [str(self.executable), *args, "--input", str(source), "--output", str(staged)]
                try:
                    result = subprocess.run(command, capture_output=True, text=True, errors="replace",
                                            timeout=self.timeout, creationflags=_NO_WINDOW)
                except subprocess.TimeoutExpired as error:
                    raise WorkflowError("snapgene_timeout", f"SnapGene exceeded {self.timeout:g} seconds.") from error
                if result.returncode:
                    raise WorkflowError("snapgene_command_failed", "SnapGene could not complete the command.",
                                        {"returncode": result.returncode, "stderr": result.stderr[-2000:], "stdout": result.stdout[-2000:]})
                self._verify_artifact(staged, format)
                try:
                    with destination.open("xb") as output:
                        try:
                            with staged.open("rb") as data:
                                shutil.copyfileobj(data, output)
                        except OSError:
                            output.close()
                            destination.unlink()  # Only the new file owned by this operation.
                            raise
                except FileExistsError as error:
                    raise WorkflowError("snapgene_output_exists", "Output was created by another operation; choose a new path.") from error

    def convert(self, construct: ConstructRef, *, output_path: str) -> ConstructRef:
        """Convert an already validated construct to a NEW SnapGene artifact."""
        return self.export(construct, output_path=output_path, output_format="snapgene")

    def export(self, construct: ConstructRef, *, output_path: str, output_format: str = "genbank") -> ConstructRef:
        """Additional local utility; not an extension of the shared MCP contract."""
        if output_format not in _FORMATS:
            raise WorkflowError("snapgene_format_unsupported", f"Unsupported output format: {output_format}")
        source = self._input(construct)
        destination = self._output(output_path, output_format)
        self._produce(source, destination, output_format, ["--convert", _FORMATS[output_format]])
        return ConstructRef(destination.relative_to(self.workspace).as_posix(), output_format, construct.name)

    def render_map(self, construct: ConstructRef, *, output_path: str, size: int = 1200) -> str:
        """Export a real PNG through SnapGene; returns its workspace-relative path."""
        if construct.format != "snapgene":
            raise WorkflowError("snapgene_format_unsupported", "Convert to .dna before rendering a map.")
        if not isinstance(size, int) or not 100 <= size <= 4096:
            raise WorkflowError("snapgene_invalid_size", "Map size must be 100–4096 pixels.")
        source = self._input(construct)
        destination = self._output(output_path, "png")
        self._produce(source, destination, "png", ["--createPreview", "--size", f"{size},{size}", "--ppi", "96"])
        return destination.relative_to(self.workspace).as_posix()

    def open(self, construct: ConstructRef) -> None:
        """Open and wait for the requested document's title; never dismiss dialogs."""
        source = self._input(construct)
        with self._job(requires_closed=False):
            process = subprocess.Popen([str(self.executable), str(source)], stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, close_fds=True)
            # The GUI intentionally outlives this call. Reap it on eventual exit
            # without blocking the MCP request or terminating the application.
            threading.Thread(target=process.wait, daemon=True, name="snapgene-desktop-reaper").start()
            deadline = time.monotonic() + self.open_timeout
            windows = []
            while time.monotonic() < deadline:
                windows = self._document_windows()
                if any(w["title"].casefold().startswith(source.name.casefold() + " ")
                       or w["title"].casefold() == source.name.casefold() for w in windows):
                    return
                if process.poll() not in (None, 0):
                    raise WorkflowError("snapgene_open_failed", "SnapGene exited before the document opened.")
                time.sleep(0.3)
            raise WorkflowError("snapgene_open_unconfirmed", "The document window was not confirmed. Inspect SnapGene for a dialog; no dialog was dismissed.",
                                {"windows": windows})

    def health(self) -> dict:
        self._check_installation()
        return {"available": True, "executable": str(self.executable), "running": bool(self._process_ids()),
                "workspace": str(self.workspace)}


def create_service() -> DesktopSnapGeneService:
    return DesktopSnapGeneService(workspace=os.environ.get("DNA_MAKER_WORKSPACE"))
