"""
Safe Tkinter `after(...)` scheduling helpers.

Use this mixin in UI classes to avoid stale callback errors when widgets are
destroyed while periodic timers are still scheduled.
"""

import tkinter as tk


class SafeAfterMixin:
    """Utility mixin for keyed, cancel-safe `after(...)` jobs."""

    def _init_after_manager(self, widget: tk.Misc):
        self._after_widget = widget
        self._after_jobs: dict[str, str] = {}
        self._after_closed = False

    def _after_schedule(self, key: str, ms: int, callback):
        """Schedule/re-schedule a keyed callback and return the job id."""
        if self._after_closed:
            return None

        self._after_cancel(key)
        try:
            job_id = self._after_widget.after(ms, callback)
            self._after_jobs[key] = job_id
            return job_id
        except tk.TclError:
            self._after_jobs.pop(key, None)
            return None

    def _after_cancel(self, key: str):
        """Cancel one keyed callback if present."""
        job_id = self._after_jobs.pop(key, None)
        if not job_id:
            return
        try:
            self._after_widget.after_cancel(job_id)
        except tk.TclError:
            pass

    def _after_cancel_all(self):
        """Cancel all tracked callbacks."""
        for key in list(self._after_jobs.keys()):
            self._after_cancel(key)

    def _after_mark_closing(self):
        """Stop future schedules and cancel all queued callbacks."""
        self._after_closed = True
        self._after_cancel_all()

    def _after_is_closing(self) -> bool:
        return self._after_closed
