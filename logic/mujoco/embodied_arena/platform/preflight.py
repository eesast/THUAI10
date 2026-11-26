"""Trusted script supplied with `python -c` INSIDE the isolated policy container.

It does not import contestant code until every Python file has compiled. The
fixed runtime image can be reused; the host runner source hash records this file.
"""

import pathlib
import runpy
import sys
import traceback

sys.path.insert(0, "/runtime")
from protocol import dumps

try:
    root = pathlib.Path("/submission")
    total = 0
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".py")
    if len(files) > 2048:
        raise ValueError("Too many Python files")
    for path in files:
        content = path.read_bytes()
        total += len(content)
        if total > 16 * 1024 * 1024:
            raise ValueError("Python source exceeds the 16 MB compilation limit")
        compile(content, path.relative_to(root).as_posix(), "exec", dont_inherit=True)
except Exception:
    sys.stdout.buffer.write(
        dumps(
            {
                "id": 0,
                "error": "包内 Python 编译失败：\n" + traceback.format_exc(limit=5)[-3500:],
                "phase": "compile",
            }
        )
    )
    sys.stdout.buffer.flush()
    raise SystemExit(1)

runpy.run_path("/runtime/agent.py", run_name="__main__")
