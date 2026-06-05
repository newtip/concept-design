"""Atomic YAML writes for orchestrator-owned index files."""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator

import yaml


@contextmanager
def file_lock(path: Path, timeout_seconds: float = 10.0) -> Iterator[None]:
    lock_path = path.with_suffix(path.suffix + ".lock")
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise TimeoutError(f"timed out waiting for index lock: {lock_path}")
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def atomic_write_yaml(path: str | Path, data: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    rendered = yaml.safe_dump(data, allow_unicode=True, sort_keys=False)
    with file_lock(target):
        tmp.write_text(rendered, encoding="utf-8")
        tmp.replace(target)


def locked_index_update(path: str | Path, update_fn: Callable[[dict], dict], timeout_seconds: float = 10.0) -> dict:
    target = Path(path)
    with file_lock(target, timeout_seconds=timeout_seconds):
        data = {}
        if target.exists():
            data = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        updated = update_fn(data)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(yaml.safe_dump(updated, allow_unicode=True, sort_keys=False), encoding="utf-8")
        os.replace(tmp, target)
        return updated
