import subprocess
from pathlib import Path


def test_practice_voice_helpers_run_in_node():
    script = Path(__file__).with_name("test_practice_voices.js")
    result = subprocess.run(
        ["node", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ok" in result.stdout
