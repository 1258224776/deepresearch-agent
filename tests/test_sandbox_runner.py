from __future__ import annotations

import pytest


def test_run_coder_sandbox_collects_text_and_png_artifacts():
    from sandbox_runner import run_coder_sandbox

    code = """
import base64
import json

PNG_DATA = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO7Z0j8AAAAASUVORK5CYII="

def main():
    with open("analysis.md", "w", encoding="utf-8") as handle:
        handle.write("# Analysis\\n\\nSandbox execution succeeded.")
    with open("chart.png", "wb") as handle:
        handle.write(base64.b64decode(PNG_DATA))
    with open("result.json", "w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": "Generated analysis artifacts.",
                "artifacts": [
                    {
                        "artifact_id": "code_analysis",
                        "kind": "text_markdown",
                        "title": "Code analysis",
                        "path": "analysis.md",
                    },
                    {
                        "artifact_id": "code_chart",
                        "kind": "image_png",
                        "title": "Generated chart",
                        "path": "chart.png",
                    },
                ],
            },
            handle,
        )
"""

    result = run_coder_sandbox(
        code=code,
        input_payload={"question": "Plot a trend"},
        run_id="run-sandbox-success",
        node_id="coder",
        timeout_seconds=5,
    )

    assert result.summary == "Generated analysis artifacts."
    assert [artifact.artifact_id for artifact in result.artifacts] == ["code_analysis", "code_chart"]
    assert result.artifacts[0].content.startswith("# Analysis")
    assert result.artifacts[1].content.startswith("data:image/png;base64,")


def test_run_coder_sandbox_blocks_disallowed_import():
    from sandbox_runner import run_coder_sandbox

    code = """
import os

def main():
    with open("result.json", "w", encoding="utf-8") as handle:
        handle.write("{}")
"""

    with pytest.raises(RuntimeError, match="disallowed import"):
        run_coder_sandbox(
            code=code,
            input_payload={"question": "Should fail"},
            run_id="run-sandbox-blocked",
            node_id="coder",
            timeout_seconds=5,
        )
