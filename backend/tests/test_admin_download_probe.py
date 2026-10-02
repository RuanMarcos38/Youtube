import unittest
from concurrent.futures import Future
from unittest.mock import Mock, patch

from app.routers import admin


class AdminDownloadProbeTests(unittest.TestCase):
    def test_start_returns_pending_and_reuses_running_probe(self):
        future = Future()
        executor = Mock()
        executor.submit.return_value = future
        with patch.object(admin, "_download_probe_future", None), patch.object(admin, "_download_probe_executor", executor):
            self.assertEqual(admin.test_download_auth(background=True, _=None), {"pending": True})
            self.assertEqual(admin.test_download_auth(background=True, _=None), {"pending": True})
            executor.submit.assert_called_once_with(admin.run_and_store_download_probe)
            self.assertEqual(admin.download_test_status(_=None), {"pending": True})
            future.set_result({"ok": True, "mode": "cookies"})
            self.assertEqual(admin.download_test_status(_=None), {"ok": True, "mode": "cookies"})

    def test_failed_probe_reports_real_failure_without_success_claim(self):
        future = Future()
        future.set_result({"ok": False, "bot_blocked": True, "error": "Sign in to confirm you are not a bot"})
        with patch.object(admin, "_download_probe_future", future):
            with self.assertRaises(admin.HTTPException) as caught:
                admin.download_test_status(_=None)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertIn("IP/sessão", caught.exception.detail)
        self.assertNotIn("já foi renovada", caught.exception.detail)

    def test_probe_without_start_is_not_a_cached_success(self):
        with patch.object(admin, "_download_probe_future", None):
            with self.assertRaises(admin.HTTPException) as caught:
                admin.download_test_status(_=None)
        self.assertEqual(caught.exception.status_code, 409)

    def test_unexpected_worker_error_is_safely_reported(self):
        future = Future()
        future.set_exception(RuntimeError("private internal detail"))
        with patch.object(admin, "_download_probe_future", future):
            with self.assertRaises(admin.HTTPException) as caught:
                admin.download_test_status(_=None)
        self.assertEqual(caught.exception.status_code, 503)
        self.assertNotIn("private internal detail", caught.exception.detail)
