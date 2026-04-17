from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from pydantic import BaseModel, Field


SANDBOX_ROOT = Path(__file__).resolve().parent / "data" / "sandbox"
SANDBOX_WORKER_PATH = Path(__file__).resolve().with_name("sandbox_worker.py")
SANDBOX_INPUT_FILENAME = "input_payload.json"
SANDBOX_OUTPUT_FILENAME = "sandbox_output.json"
SANDBOX_SCRIPT_FILENAME = "coder_script.py"
SANDBOX_TIMEOUT_SECONDS = 20

_BASE_ALLOWED_MODULES = (
    "base64",
    "collections",
    "csv",
    "datetime",
    "io",
    "itertools",
    "json",
    "math",
    "statistics",
)
_OPTIONAL_ALLOWED_MODULES = (
    "numpy",
    "pandas",
    "matplotlib",
)


class SandboxArtifactResult(BaseModel):
    artifact_id: str
    kind: str
    title: str
    content: str
    filename: str = ""


class SandboxExecutionResult(BaseModel):
    summary: str
    stdout: str = ""
    stderr: str = ""
    artifacts: list[SandboxArtifactResult] = Field(default_factory=list)


def get_available_sandbox_modules() -> list[str]:
    modules = list(_BASE_ALLOWED_MODULES)
    for name in _OPTIONAL_ALLOWED_MODULES:
        if importlib.util.find_spec(name) is not None:
            modules.append(name)
    return modules


def _data_url_for_png(file_path: Path) -> str:
    encoded = base64.b64encode(file_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _sandbox_env(work_dir: Path) -> dict[str, str]:
    env: dict[str, str] = {
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "MPLBACKEND": "Agg",
        "MPLCONFIGDIR": str(work_dir),
        "HOME": str(work_dir),
        "USERPROFILE": str(work_dir),
        "TMP": str(work_dir),
        "TEMP": str(work_dir),
    }
    for key in ("PATH", "SYSTEMROOT", "WINDIR"):
        value = os.getenv(key)
        if value:
            env[key] = value
    return env


def _load_artifact_content(work_dir: Path, artifact_entry: dict[str, str]) -> SandboxArtifactResult:
    relative_path = str(artifact_entry.get("path") or "").strip()
    if not relative_path:
        raise RuntimeError("sandbox artifact path is required")

    file_path = (work_dir / relative_path).resolve()
    if not file_path.exists():
        raise RuntimeError(f"sandbox artifact not found: {relative_path}")

    artifact_kind = str(artifact_entry.get("kind") or "").strip() or "text"
    artifact_id = str(artifact_entry.get("artifact_id") or "").strip() or file_path.stem
    title = str(artifact_entry.get("title") or "").strip() or artifact_id

    if artifact_kind == "image_png":
        content = _data_url_for_png(file_path)
    else:
        content = file_path.read_text(encoding="utf-8")

    return SandboxArtifactResult(
        artifact_id=artifact_id,
        kind=artifact_kind,
        title=title,
        content=content,
        filename=file_path.name,
    )


def run_coder_sandbox(
    *,
    code: str,
    input_payload: dict,
    run_id: str,
    node_id: str,
    timeout_seconds: int = SANDBOX_TIMEOUT_SECONDS,
) -> SandboxExecutionResult:
    work_dir = SANDBOX_ROOT / f"{run_id}-{node_id}-{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)

    script_path = work_dir / SANDBOX_SCRIPT_FILENAME
    input_path = work_dir / SANDBOX_INPUT_FILENAME
    output_path = work_dir / SANDBOX_OUTPUT_FILENAME

    try:
        script_path.write_text(code, encoding="utf-8")
        input_path.write_text(json.dumps(input_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        try:
            subprocess.run(
                [
                    sys.executable,
                    str(SANDBOX_WORKER_PATH),
                    str(script_path),
                    str(input_path),
                    str(output_path),
                ],
                cwd=work_dir,
                env=_sandbox_env(work_dir),
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"sandbox timed out after {timeout_seconds}s") from exc

        if not output_path.exists():
            raise RuntimeError("sandbox did not produce an output manifest")

        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            error_text = str(payload.get("error") or "sandbox execution failed")
            stderr = str(payload.get("stderr") or "").strip()
            if stderr:
                error_text = f"{error_text}: {stderr}"
            raise RuntimeError(error_text)

        manifest = payload.get("manifest") or {}
        artifacts = [
            _load_artifact_content(work_dir, artifact_entry)
            for artifact_entry in manifest.get("artifacts", []) or []
        ]
        return SandboxExecutionResult(
            summary=str(manifest.get("summary") or "").strip(),
            stdout=str(payload.get("stdout") or ""),
            stderr=str(payload.get("stderr") or ""),
            artifacts=artifacts,
        )
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
