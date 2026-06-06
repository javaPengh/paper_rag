"""测试夹具和临时目录清理。"""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _cleanup_project_pytest_tmp() -> None:
    """删除项目内的 pytest 临时根目录。"""
    temp_root = Path(".paper_rag") / "pytest-tmp"
    if temp_root.exists():
        shutil.rmtree(temp_root, ignore_errors=True)


def _schedule_project_pytest_tmp_cleanup() -> None:
    """启动一个独立进程，在 pytest 退出后删除临时根目录。"""
    temp_root = (Path.cwd() / ".paper_rag" / "pytest-tmp").resolve()
    if not temp_root.exists():
        return

    cleanup_script = (
        "import ctypes\n"
        "import shutil\n"
        "from pathlib import Path\n"
        f"parent_pid = {os.getpid()}\n"
        f"temp_root = Path(r'{temp_root}')\n"
        "kernel32 = ctypes.windll.kernel32\n"
        "handle = kernel32.OpenProcess(0x00100000 | 0x00001000, False, parent_pid)\n"
        "if handle:\n"
        "    kernel32.WaitForSingleObject(handle, 0xFFFFFFFF)\n"
        "    kernel32.CloseHandle(handle)\n"
        "shutil.rmtree(temp_root, ignore_errors=True)\n"
    )
    subprocess.Popen(
        [sys.executable, "-c", cleanup_script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        close_fds=True,
    )


atexit.register(_cleanup_project_pytest_tmp)


def pytest_unconfigure(config) -> None:  # type: ignore[override]
    """在 pytest 完整卸载后尝试删除项目内的临时根目录。"""
    _cleanup_project_pytest_tmp()
    _schedule_project_pytest_tmp_cleanup()