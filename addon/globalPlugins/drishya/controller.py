"""Job generations prevent closed or cancelled dialogs receiving stale data."""
import threading
from .assets import Cancelled


class JobController:
    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.busy = False
        self.alive = True
        self.generation = 0
        self.event = threading.Event()
        self.thread = None

    @property
    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, work, on_result, on_error):
        if not self.alive:
            raise RuntimeError("Drishya has closed.")
        if self.busy or self.running:
            raise RuntimeError("A Drishya job is running or still cancelling. Please try again in a moment.")
        self.generation += 1
        generation = self.generation
        self.event = event = threading.Event()
        self.busy = True

        def deliver(value, failed):
            if self.alive and generation == self.generation and not event.is_set():
                self.busy = False
                (on_error if failed else on_result)(value)

        def run():
            try:
                value = work(event)
            except Cancelled:
                return
            except Exception as error:
                self.dispatch(lambda error=error: deliver(error, True))
            else:
                self.dispatch(lambda: deliver(value, False))

        self.thread = threading.Thread(target=run, daemon=True, name="Drishya job")
        self.thread.start()

    def cancel(self):
        was_busy = self.busy
        self.event.set()
        self.generation += 1
        self.busy = False
        return was_busy

    def close(self):
        self.cancel()
        self.alive = False
