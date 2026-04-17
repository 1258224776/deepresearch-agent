from __future__ import annotations

import ast
import builtins
import contextlib
import importlib.util
import io
import json
import socket
import sys
import traceback
from pathlib import Path


_BASE_ALLOWED_MODULES = {
    "base64",
    "collections",
    "csv",
    "datetime",
    "io",
    "itertools",
    "json",
    "math",
    "statistics",
}
_OPTIONAL_ALLOWED_MODULES = {
    "numpy",
    "pandas",
    "matplotlib",
}
_BLOCKED_NAMES = {
    "__builtins__",
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "globals",
    "help",
    "input",
    "locals",
    "open_code",
    "os",
    "pathlib",
    "socket",
    "subprocess",
    "sys",
    "type",
}
_BLOCKED_CALLS = {
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "input",
    "locals",
    "setattr",
    "delattr",
    "vars",
}


def _available_allowed_modules() -> set[str]:
    modules = set(_BASE_ALLOWED_MODULES)
    for name in _OPTIONAL_ALLOWED_MODULES:
        if importlib.util.find_spec(name) is not None:
            modules.add(name)
    return modules


class _SandboxValidator(ast.NodeVisitor):
    def __init__(self, allowed_modules: set[str]) -> None:
        self._allowed_modules = {name.split(".", 1)[0] for name in allowed_modules}

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            module_name = (alias.name or "").split(".", 1)[0]
            if module_name not in self._allowed_modules:
                raise RuntimeError(f"disallowed import: {alias.name}")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module_name = str(node.module or "").split(".", 1)[0]
        if not module_name or module_name not in self._allowed_modules:
            raise RuntimeError(f"disallowed import: {node.module}")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if str(node.attr or "").startswith("__"):
            raise RuntimeError("dunder attribute access is not allowed in sandbox")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in _BLOCKED_NAMES:
            raise RuntimeError(f"disallowed name in sandbox: {node.id}")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name) and node.func.id in _BLOCKED_CALLS:
            raise RuntimeError(f"disallowed call in sandbox: {node.func.id}")
        self.generic_visit(node)


def _safe_import_factory(allowed_modules: set[str]):
    allowed_top_level = {name.split(".", 1)[0] for name in allowed_modules}
    real_import = builtins.__import__

    def _safe_import(name: str, globals=None, locals=None, fromlist=(), level=0):
        top_level = str(name or "").split(".", 1)[0]
        if top_level not in allowed_top_level:
            raise RuntimeError(f"disallowed import in sandbox: {name}")
        return real_import(name, globals, locals, fromlist, level)

    return _safe_import


def _safe_open_factory(work_dir: Path):
    real_open = builtins.open

    def _safe_open(file, mode="r", *args, **kwargs):
        path = Path(file)
        if not path.is_absolute():
            path = (work_dir / path).resolve()
        else:
            path = path.resolve()

        writes = any(flag in mode for flag in ("w", "a", "x", "+"))
        if writes and work_dir not in path.parents and path != work_dir:
            raise RuntimeError(f"sandbox write blocked outside working directory: {path}")
        return real_open(path, mode, *args, **kwargs)

    return _safe_open


def _blocked_network(*args, **kwargs):
    raise RuntimeError("network access is disabled inside sandbox")


def _safe_builtins(work_dir: Path, allowed_modules: set[str]) -> dict[str, object]:
    safe_open = _safe_open_factory(work_dir)
    return {
        "__import__": _safe_import_factory(allowed_modules),
        "abs": abs,
        "all": all,
        "any": any,
        "bool": bool,
        "dict": dict,
        "enumerate": enumerate,
        "Exception": Exception,
        "float": float,
        "filter": filter,
        "int": int,
        "isinstance": isinstance,
        "len": len,
        "list": list,
        "map": map,
        "max": max,
        "min": min,
        "object": object,
        "open": safe_open,
        "print": print,
        "range": range,
        "round": round,
        "set": set,
        "sorted": sorted,
        "str": str,
        "sum": sum,
        "tuple": tuple,
        "ValueError": ValueError,
        "zip": zip,
    }


def _validate_code(code: str, allowed_modules: set[str]) -> None:
    tree = ast.parse(code, filename="coder_script.py")
    _SandboxValidator(allowed_modules).visit(tree)


def _execute_user_code(code: str, input_payload: dict, work_dir: Path) -> None:
    allowed_modules = _available_allowed_modules()
    _validate_code(code, allowed_modules)

    safe_open = _safe_open_factory(work_dir)
    original_open = builtins.open
    original_socket = socket.socket
    original_create_connection = socket.create_connection

    builtins.open = safe_open
    socket.socket = _blocked_network
    socket.create_connection = _blocked_network
    try:
        globals_dict = {
            "__builtins__": _safe_builtins(work_dir, allowed_modules),
            "__name__": "__sandbox__",
            "INPUT_PAYLOAD": input_payload,
        }
        exec(compile(code, "coder_script.py", "exec"), globals_dict, globals_dict)
        maybe_main = globals_dict.get("main")
        if callable(maybe_main):
            maybe_main()
    finally:
        builtins.open = original_open
        socket.socket = original_socket
        socket.create_connection = original_create_connection


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit("usage: sandbox_worker.py <script_path> <input_path> <output_path>")

    script_path = Path(sys.argv[1]).resolve()
    input_path = Path(sys.argv[2]).resolve()
    output_path = Path(sys.argv[3]).resolve()
    work_dir = output_path.parent.resolve()

    code = script_path.read_text(encoding="utf-8")
    input_payload = json.loads(input_path.read_text(encoding="utf-8"))

    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()

    payload: dict[str, object]
    with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
        try:
            _execute_user_code(code, input_payload, work_dir)
            result_path = work_dir / "result.json"
            if not result_path.exists():
                raise RuntimeError("sandbox code must write result.json")

            manifest = json.loads(result_path.read_text(encoding="utf-8"))
            payload = {
                "ok": True,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
                "manifest": manifest,
            }
        except Exception as exc:
            payload = {
                "ok": False,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }

    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
