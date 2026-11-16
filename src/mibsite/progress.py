"""Build progress output: a live counter on a terminal, sparse lines in CI logs."""
from __future__ import annotations

import sys
import time
from contextlib import contextmanager


def _fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s" if m else f"{s}s"


class Progress:
    """Counter for one long step. On a TTY it redraws one line; otherwise (CI) it prints a line
    at every 10% or every 30 s, whichever comes first, so logs stay short."""

    def __init__(self, label: str, total: int, stream=None):
        self.label, self.total, self.n = label, total, 0
        self.out = stream or sys.stdout
        self.tty = self.out.isatty()
        self.t0 = self._last = time.monotonic()
        self._next_pct = 10

    def _line(self) -> str:
        pct = 100 * self.n // self.total if self.total else 100
        return f"  {self.label}: {self.n:,}/{self.total:,} ({pct}%) {_fmt(time.monotonic() - self.t0)}"

    def step(self, n: int = 1) -> None:
        self.n += n
        now = time.monotonic()
        if self.tty:
            if now - self._last >= 0.2 or self.n == self.total:
                print("\r" + self._line(), end="", file=self.out, flush=True)
                self._last = now
        elif self.total and (100 * self.n // self.total >= self._next_pct or now - self._last >= 30):
            print(self._line(), file=self.out, flush=True)
            self._next_pct = 100 * self.n // self.total // 10 * 10 + 10
            self._last = now

    def close(self) -> None:
        if self.tty:
            print("\r" + self._line(), file=self.out, flush=True)


@contextmanager
def phase(label: str, stream=None):
    """Print `label...` and, when the block ends, how long it took."""
    out = stream or sys.stdout
    print(f"{label}...", file=out, flush=True)
    t0 = time.monotonic()
    yield
    print(f"  done in {_fmt(time.monotonic() - t0)}", file=out, flush=True)
