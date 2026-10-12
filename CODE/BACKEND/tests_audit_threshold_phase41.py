"""Phase 4.1 audit tests — C-F-5 (threshold survival) + C-F-6 (engine audit).

Run with stdlib unittest (no pytest):
    python tests_audit_threshold_phase41.py

Covers:
  * valid per-language thresholds survive a missing/malformed GLOBAL entry;
  * missing/invalid settings follow the documented fallback (global default);
  * unexpected parse errors are LOGGED, never silently swallowed;
  * a valid language-specific threshold is never overridden by the global one;
  * engine change writes ONE audit_logs row with the correct fields;
  * a failed engine change is NOT recorded as a success;
  * production models/tuned_threshold.json sha256 is unchanged (read-only).

SAFETY: no production engine switch (engine stays 'legacy'), no threshold
artifact writes, no production DB writes (audit tests use a temp sqlite file).
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import model_adapter as ma  # noqa: E402

TUNED_PATH = BACKEND_DIR / "models" / "tuned_threshold.json"
EXPECTED_TUNED_SHA256 = (
    "f31f4975d29a151f3f8737ae18875f6a5d11c2ee8719d126c587f7b339285c54")


class _Env:
    """Context manager: override env vars, restore them exactly on exit."""

    def __init__(self, **kw):
        self.kw = kw
        self.saved: dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self.kw.items():
            self.saved[k] = os.environ.get(k)
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return False


def _cfg_from_text(text: str, default_threshold: str = "0.5"):
    """Build a ModelConfig from raw tuned-file text (temp file, then dropped)."""
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "tuned.json"
        p.write_text(text, encoding="utf-8")
        with _Env(AURA_MODEL_TUNED_THRESHOLD=str(p),
                  AURA_MODEL_THRESHOLD=default_threshold):
            return ma.ModelConfig()


def _cfg_from_obj(obj, default_threshold: str = "0.5"):
    return _cfg_from_text(json.dumps(obj), default_threshold)


# ---------------------------------------------------------------------------
# 1) C-F-5 — per-language thresholds survive a bad global entry
# ---------------------------------------------------------------------------
class TestPerLanguageSurvivesBadGlobal(unittest.TestCase):
    def test_missing_global_keeps_valid_per_language(self):
        cfg = _cfg_from_obj({"per_language": {"en": 0.55, "ta": 0.40}})
        self.assertEqual(cfg.per_language, {"en": 0.55, "ta": 0.40},
                         "valid per-language thresholds were discarded because "
                         "the GLOBAL entry was missing (C-F-5 regression)")
        self.assertEqual(cfg.threshold_for("en"), 0.55)
        self.assertEqual(cfg.threshold_for("ta"), 0.40)
        # documented fallback for the global value: AURA_MODEL_THRESHOLD (0.5)
        self.assertEqual(cfg.threshold, 0.5)
        self.assertEqual(cfg.threshold_source, "default")
        self.assertTrue(cfg.threshold_rationale)

    def test_malformed_global_keeps_valid_per_language(self):
        cfg = _cfg_from_obj({"threshold": "not-a-number",
                             "per_language": {"en": 0.55, "hi": 0.35},
                             "rationale": "n/a"})
        self.assertEqual(cfg.per_language, {"en": 0.55, "hi": 0.35})
        self.assertEqual(cfg.threshold_for("en"), 0.55)
        self.assertEqual(cfg.threshold, 0.5)          # documented fallback
        self.assertEqual(cfg.threshold_source, "default")

    def test_out_of_range_global_keeps_valid_per_language(self):
        # also exercises the old AttributeError path (rationale never set)
        cfg = _cfg_from_obj({"threshold": 1.5, "per_language": {"en": 0.55}})
        self.assertEqual(cfg.per_language, {"en": 0.55})
        self.assertEqual(cfg.threshold_for("en"), 0.55)
        self.assertEqual(cfg.threshold, 0.5)
        self.assertEqual(cfg.threshold_source, "default")
        self.assertIn("per-language thresholds applied", cfg.threshold_rationale)
        # as_dict() must not explode (rationale/source always defined)
        d = cfg.as_dict()
        self.assertEqual(d["per_language_thresholds"], {"en": 0.55})

    def test_missing_global_documented_fallback(self):
        cfg = _cfg_from_obj({"rationale": "no global, no languages"})
        self.assertEqual(cfg.per_language, {})
        self.assertEqual(cfg.threshold, 0.5)
        self.assertEqual(cfg.threshold_source, "default")
        self.assertEqual(cfg.threshold_rationale,
                         "default 0.5 (not tuned yet)")
        self.assertEqual(cfg.threshold_for("ta"), 0.5)

    def test_empty_file_documented_fallback(self):
        cfg = _cfg_from_text("{}")
        self.assertEqual(cfg.per_language, {})
        self.assertEqual(cfg.threshold, 0.5)
        self.assertEqual(cfg.threshold_source, "default")

    def test_unexpected_parse_error_logged_not_swallowed(self):
        with self.assertLogs(level="WARNING") as cm:
            cfg = _cfg_from_text("{ this is not valid json")
        joined = "\n".join(cm.output)
        self.assertIn("tuned threshold", joined.lower())
        self.assertIn("cannot parse", joined.lower())
        # documented fallback still applied
        self.assertEqual(cfg.per_language, {})
        self.assertEqual(cfg.threshold, 0.5)
        self.assertEqual(cfg.threshold_source, "default")

    def test_non_object_payload_logged_not_swallowed(self):
        with self.assertLogs(level="WARNING") as cm:
            cfg = _cfg_from_text('["not", "an", "object"]')
        self.assertTrue(any("not a JSON object" in line for line in cm.output))
        self.assertEqual(cfg.per_language, {})
        self.assertEqual(cfg.threshold, 0.5)

    def test_valid_language_threshold_never_overridden_by_global(self):
        cfg = _cfg_from_obj({"threshold": 0.25,
                             "per_language": {"en": 0.55, "ta": 0.40},
                             "rationale": "global vs language"})
        self.assertEqual(cfg.threshold, 0.25)          # global for others
        self.assertEqual(cfg.threshold_for("en"), 0.55)  # language WINS
        self.assertEqual(cfg.threshold_for("ta"), 0.40)
        self.assertEqual(cfg.threshold_for("te"), 0.25)  # unlisted -> global

    def test_deployed_artifact_still_reads_correctly(self):
        with _Env(AURA_MODEL_TUNED_THRESHOLD=str(TUNED_PATH)):
            cfg = ma.ModelConfig()
        self.assertEqual(cfg.threshold, 0.35)
        self.assertEqual(cfg.per_language,
                         {"en": 0.55, "ta": 0.4, "ta-Latn": 0.3,
                          "hi": 0.35, "bn": 0.3, "ur": 0.4})
        self.assertEqual(cfg.threshold_source, "tuned_validation")
        self.assertEqual(cfg.threshold_for("te"), 0.35)  # global fallback


# ---------------------------------------------------------------------------
# 2) C-F-6 — set_engine writes an audit_logs row (isolated temp sqlite)
# ---------------------------------------------------------------------------
class TestEngineAudit(unittest.TestCase):
    def setUp(self):
        import backend
        self.backend = backend
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_db = backend.DB_PATH
        self._saved_env = os.environ.get("AURA_PREDICTION_ENGINE")
        backend.DB_PATH = Path(self._tmp.name) / "audit_test.db"
        c = backend.db()
        c.executescript(
            "CREATE TABLE IF NOT EXISTS audit_logs(id INTEGER PRIMARY KEY "
            "AUTOINCREMENT,user_id TEXT,action TEXT NOT NULL,details TEXT,"
            "created_at TEXT NOT NULL);"
            "CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, "
            "value TEXT);")
        c.execute("INSERT INTO settings(key,value) "
                  "VALUES('prediction_engine','legacy')")
        c.commit()
        c.close()
        os.environ["AURA_PREDICTION_ENGINE"] = "legacy"

    def tearDown(self):
        self.backend.DB_PATH = self._saved_db
        if self._saved_env is None:
            os.environ.pop("AURA_PREDICTION_ENGINE", None)
        else:
            os.environ["AURA_PREDICTION_ENGINE"] = self._saved_env
        self._tmp.cleanup()

    def _rows(self):
        c = self.backend.db()
        rows = c.execute("SELECT user_id,action,details,created_at "
                         "FROM audit_logs ORDER BY id").fetchall()
        c.close()
        return [dict(r) for r in rows]

    def test_engine_still_legacy_after_test(self):
        """Guard: this suite must never leave anything but legacy."""
        self.assertEqual(os.environ.get("AURA_PREDICTION_ENGINE"), "legacy")

    def test_audit_row_written_on_success(self):
        rv = self.backend.set_engine("legacy", actor="admin")
        self.assertEqual(rv, "legacy")
        self.assertEqual(os.environ.get("AURA_PREDICTION_ENGINE"), "legacy")
        rows = self._rows()
        self.assertEqual(len(rows), 1, "exactly one audit row per change")
        row = rows[0]
        self.assertEqual(row["user_id"], "admin")
        self.assertEqual(row["action"], "ENGINE_CHANGE")
        datetime.fromisoformat(row["created_at"])   # existing now() convention
        details = json.loads(row["details"])
        self.assertEqual(details["previous_engine"], "legacy")
        self.assertEqual(details["requested_engine"], "legacy")
        self.assertEqual(details["resulting_engine"], "legacy")
        self.assertIs(details["success"], True)
        raw = row["details"].lower()
        self.assertNotIn("admin@1234", raw)         # no secrets in audit rows
        self.assertNotIn("password", raw)

    def test_audit_not_written_as_success_on_invalid_engine(self):
        with self.assertRaises(Exception):
            self.backend.set_engine("bogus_engine", actor="admin")
        # production engine untouched
        self.assertEqual(os.environ.get("AURA_PREDICTION_ENGINE"), "legacy")
        rows = self._rows()
        successes = [r for r in rows
                     if json.loads(r["details"]).get("success") is True]
        self.assertEqual(successes, [],
                         "a FAILED engine change was logged as success")
        if rows:
            details = json.loads(rows[0]["details"])
            self.assertIs(details["success"], False)
            self.assertEqual(details["resulting_engine"], "legacy")
            self.assertEqual(details["requested_engine"], "bogus_engine")

    def test_audit_not_written_as_success_on_db_failure(self):
        # point the DB at something sqlite cannot open -> settings write fails
        self.backend.DB_PATH = Path(self._tmp.name)   # a directory, not a file
        with self.assertRaises(Exception):
            self.backend.set_engine("legacy", actor="admin")
        self.assertEqual(os.environ.get("AURA_PREDICTION_ENGINE"), "legacy")

    def test_no_duplicate_rows_for_one_change(self):
        self.backend.set_engine("legacy", actor="admin")
        self.backend.set_engine("legacy", actor="admin")  # idempotent re-apply
        rows = self._rows()
        # one row per CHANGE ATTEMPT, never two rows inside one attempt
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["action"], "ENGINE_CHANGE")
        # a single attempt must produce a single row (checked in success test)
        self.assertEqual(
            [json.loads(r["details"])["success"] for r in rows], [True, True])

    def test_actor_is_optional_and_row_written(self):
        self.backend.set_engine("legacy")   # no actor available
        rows = self._rows()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["user_id"])
        self.assertIs(json.loads(rows[0]["details"])["success"], True)


# ---------------------------------------------------------------------------
# 3) Read-only artifact guard
# ---------------------------------------------------------------------------
class TestTunedThresholdArtifactUntouched(unittest.TestCase):
    def test_production_tuned_threshold_sha256_unchanged(self):
        digest = hashlib.sha256(TUNED_PATH.read_bytes()).hexdigest()
        self.assertEqual(digest, EXPECTED_TUNED_SHA256,
                         "models/tuned_threshold.json was modified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
