"""Safe cooperative operation execution for long-running desktop work."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Callable, Generic, TypeVar


T = TypeVar("T")


class OperationCancelled(RuntimeError):
    """Raised when an operation is cancelled before its safe commit point."""


class CancellationToken:
    """Thread-safe cooperative cancellation signal."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._progress: float | None = None
        self._detail = ""
        self._iteration: int | None = None

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def update(
        self, *, progress: float | None = None, detail: str = "", iteration: int | None = None
    ) -> None:
        if progress is not None and not 0.0 <= progress <= 1.0:
            raise ValueError("operation progress must be between zero and one")
        with self._lock:
            self._progress = progress
            self._detail = detail
            self._iteration = iteration

    @property
    def progress(self) -> float | None:
        with self._lock:
            return self._progress

    @property
    def detail(self) -> str:
        with self._lock:
            return self._detail

    @property
    def iteration(self) -> int | None:
        with self._lock:
            return self._iteration

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise OperationCancelled("operation cancelled before project state was changed")


@dataclass(frozen=True)
class OperationSnapshot:
    name: str
    state: str
    elapsed_seconds: float
    error: str | None = None
    progress: float | None = None
    detail: str = ""
    iteration: int | None = None


class OperationHandle(Generic[T]):
    """Observable future with safe cancellation semantics."""

    def __init__(self, name: str, token: CancellationToken, future: Future[T], started: float):
        self.name = name
        self.token = token
        self.future = future
        self.started = started

    def cancel(self) -> None:
        self.token.cancel()
        self.future.cancel()

    def snapshot(self) -> OperationSnapshot:
        elapsed = time.perf_counter() - self.started
        if self.future.cancelled():
            return OperationSnapshot(self.name, "cancelled", elapsed)
        if not self.future.done():
            return OperationSnapshot(
                self.name,
                "cancelling" if self.token.cancelled else "running",
                elapsed,
                progress=self.token.progress,
                detail=self.token.detail,
                iteration=self.token.iteration,
            )
        try:
            error = self.future.exception()
        except BaseException as exc:  # pragma: no cover - defensive future handling
            return OperationSnapshot(self.name, "failed", elapsed, str(exc))
        if isinstance(error, OperationCancelled):
            state = "cancelled"
        else:
            state = "failed" if error is not None else "complete"
        return OperationSnapshot(
            self.name,
            state,
            elapsed,
            str(error) if error else None,
            self.token.progress,
            self.token.detail,
            self.token.iteration,
        )


class OperationExecutor:
    """One-worker executor used by the desktop to avoid concurrent project writes."""

    def __init__(self) -> None:
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nix-ert")

    def submit(self, name: str, operation: Callable[[CancellationToken], T]) -> OperationHandle[T]:
        token = CancellationToken()
        started = time.perf_counter()

        def guarded() -> T:
            token.raise_if_cancelled()
            result = operation(token)
            token.raise_if_cancelled()
            return result

        future = self._executor.submit(guarded)
        return OperationHandle(name, token, future, started)

    def shutdown(self, *, wait: bool = True) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=True)


__all__ = [
    "CancellationToken",
    "OperationCancelled",
    "OperationExecutor",
    "OperationHandle",
    "OperationSnapshot",
]
