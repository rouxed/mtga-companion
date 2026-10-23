"""Tests del cierre cooperativo de hilos."""
from __future__ import annotations

from mtga_companion.thread_registry import register_thread, stop_all_threads


class _FakeThread:
    def __init__(self):
        self.running = True
        self.stop_called = False
        self.quit_called = False
        self.terminate_called = False
        self.wait_called = False

    def isRunning(self):
        return self.running

    def stop(self):
        self.stop_called = True

    def quit(self):
        self.quit_called = True

    def wait(self, timeout_ms):
        self.wait_called = True
        self.running = False
        return True

    def terminate(self):
        self.terminate_called = True


def test_stop_all_threads_is_cooperative_and_never_terminates():
    thread = _FakeThread()
    register_thread(thread)

    stop_all_threads(timeout_ms=10)

    assert thread.stop_called is True
    assert thread.quit_called is True
    assert thread.wait_called is True
    assert thread.terminate_called is False
