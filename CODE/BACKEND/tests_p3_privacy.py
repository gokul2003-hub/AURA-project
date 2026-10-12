"""P3 / P3b / P3c test suite (AURA Phase 4.13).

Run:  python tests_p3_privacy.py

Synthetic fixtures only.  No dataset is read, no RUHSOLD data is processed, no
frozen split or manifest is recomputed, no database is opened, and no network
is used.

Covers: redaction-before-dedup ordering, deterministic normalisation, version
changes, salt handling, PII fixtures, and exclusion of ambiguous labels.
"""
from __future__ import annotations

import re
import sys
import unicodedata
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import p3_privacy as p3  # noqa: E402

SALT_A = p3.generate_salt()
SALT_B = p3.generate_salt()

HANDLE_TEXT = "meet me @alice and @bob about @carol"
URL_TEXT = "see https://example.com/a?b=1 and www.foo.org/x now"
EMAIL_TEXT = "contact admin@example.com or j.doe+tag@sub.domain.co"
PHONE_TEXT = "call +1 (212) 555-0199 or 020 7946 0958"
ID_TEXT = "ref 9876543210 and 12345678"
PII_FIXTURE = " ".join([HANDLE_TEXT, URL_TEXT, EMAIL_TEXT, PHONE_TEXT, ID_TEXT])

# NFKC-sensitive: ligature and full-width forms.
LIGATURE = "ﬁle"          # U+FB01 -> "fi"
FULLWIDTH = "ＡＢＣ１２３"  # U+FF21.. -> "ABC123"


class TestP3Redaction(unittest.TestCase):
    def test_handles_urls_emails_phones_ids_are_redacted(self) -> None:
        self.assertNotIn("@alice", p3.redact(HANDLE_TEXT))
        self.assertEqual(p3.redact(HANDLE_TEXT).count("[USER]"), 3)
        self.assertNotIn("https://example.com", p3.redact(URL_TEXT))
        self.assertIn("[URL]", p3.redact(URL_TEXT))
        self.assertNotIn("admin@example.com", p3.redact(EMAIL_TEXT))
        self.assertIn("[EMAIL]", p3.redact(EMAIL_TEXT))
        self.assertNotIn("212) 555-0199", p3.redact(PHONE_TEXT))
        self.assertIn("[PHONE]", p3.redact(PHONE_TEXT))
        self.assertNotIn("9876543210", p3.redact(ID_TEXT))
        self.assertIn("[ID]", p3.redact(ID_TEXT))

    def test_no_identifier_survives_in_full_fixture(self) -> None:
        out = p3.redact(PII_FIXTURE)
        for needle in ("@alice", "@bob", "@carol", "example.com", "foo.org",
                       "admin@example.com", "212", "555", "9876543210",
                       "12345678"):
            self.assertNotIn(needle, out, f"identifier survived: {needle}")

    def test_ordinary_prose_is_untouched(self) -> None:
        prose = "this is a perfectly normal comment about weather"
        self.assertEqual(p3.redact(prose), prose)

    def test_urls_are_redacted_before_emails_so_no_double_tokenising(self) -> None:
        out = p3.redact("mail me at https://mail.example.com/u/7")
        self.assertIn("[URL]", out)
        self.assertNotIn("[EMAIL]", out)

    def test_none_and_non_string_are_safe(self) -> None:
        self.assertEqual(p3.redact(None), "")
        self.assertEqual(p3.normalise(None), "")


class TestOrdering(unittest.TestCase):
    """P3 mandates redaction BEFORE deduplication."""

    def test_records_differing_only_by_identifier_collapse_to_one(self) -> None:
        rows = [
            "meet me @alice at https://a.example/x",
            "meet me @bob at https://b.example/y",
        ]
        out = p3.prepare(rows, SALT_A)
        self.assertEqual(len(out), 1,
                         "redaction did not precede deduplication")

    def test_distinct_content_is_not_over_deduplicated(self) -> None:
        rows = ["completely different first comment",
                "totally unrelated second comment",
                "completely different first comment"]
        out = p3.prepare(rows, SALT_A)
        self.assertEqual(len(out), 2, "exact duplicate should collapse once")

    def test_dedup_key_is_identical_for_identifier_only_difference(self) -> None:
        self.assertEqual(
            p3.dedup_key("pay @alice now", SALT_A),
            p3.dedup_key("pay @zzzzzz now", SALT_A),
        )

    def test_hash_never_contains_raw_identifier(self) -> None:
        out = p3.prepare(["email me at secret.person@corp.example"], SALT_A)
        self.assertEqual(len(out), 1)
        self.assertNotIn("secret.person", out[0]["normalised"])
        self.assertNotIn("@", out[0]["normalised"])
        self.assertRegex(out[0]["text_hash"], r"^[0-9a-f]{64}$")


class TestDeterministicNormalisation(unittest.TestCase):
    def test_nfkc_is_the_configured_form(self) -> None:
        self.assertEqual(p3.UNICODE_NORMALIZATION, "NFKC")

    def test_nfkc_folds_ligature_and_fullwidth(self) -> None:
        self.assertEqual(unicodedata.normalize("NFKC", LIGATURE), "file")
        self.assertIn("file", p3.normalise(LIGATURE))
        self.assertIn("ABC123", p3.normalise(FULLWIDTH).upper())

    def test_casefold_collapses_case(self) -> None:
        self.assertEqual(p3.normalise("CAFÉ Comment"), p3.normalise("café comment"))

    def test_whitespace_is_collapsed(self) -> None:
        self.assertEqual(p3.normalise("  a \n\t b   c  "), "a b c")

    def test_repeat_calls_are_identical(self) -> None:
        for sample in (PII_FIXTURE, LIGATURE, FULLWIDTH, "Mixed CASE 123"):
            self.assertEqual(p3.normalise(sample), p3.normalise(sample))

    def test_pipeline_is_idempotent(self) -> None:
        once = p3.normalise(PII_FIXTURE)
        self.assertEqual(p3.normalise(once), once)

    def test_hash_is_deterministic_for_same_input(self) -> None:
        self.assertEqual(p3.text_hash("abc", SALT_A), p3.text_hash("abc", SALT_A))


class TestVersionChanges(unittest.TestCase):
    def test_fingerprint_carries_explicit_version(self) -> None:
        fp = p3.preprocess_fingerprint()
        self.assertEqual(fp["preprocess_version"], p3.PREPROCESS_VERSION)
        self.assertEqual(fp["unicode_normalization"], "NFKC")
        self.assertTrue(fp["rules_version"])
        self.assertTrue(fp["pinned_regex_version"])

    def test_version_bump_changes_fingerprint(self) -> None:
        """A changed pipeline must yield a detectably different fingerprint."""
        original = p3.PREPROCESS_VERSION
        try:
            before = p3.preprocess_fingerprint()
            p3.PREPROCESS_VERSION = "9.9.9"
            after = p3.preprocess_fingerprint()
        finally:
            p3.PREPROCESS_VERSION = original
        self.assertNotEqual(before["preprocess_version"],
                            after["preprocess_version"])
        self.assertNotEqual(before, after)

    def test_fingerprint_is_embedded_in_prepared_records(self) -> None:
        out = p3.prepare(["hello world"], SALT_A)
        self.assertEqual(out[0]["fingerprint"], p3.preprocess_fingerprint())

    def test_every_prepared_record_shares_one_fingerprint(self) -> None:
        out = p3.prepare(["one", "two", "three"], SALT_A)
        fingerprints = {str(r["fingerprint"]) for r in out}
        self.assertEqual(len(fingerprints), 1)

    def test_unicode_norm_is_not_silently_nfc(self) -> None:
        """The legacy engine uses NFC; this path must stay on approved NFKC."""
        self.assertNotEqual(p3.UNICODE_NORMALIZATION, "NFC")


class TestSaltHandling(unittest.TestCase):
    def test_hash_is_64_hex_chars(self) -> None:
        self.assertRegex(p3.text_hash("x", SALT_A), r"^[0-9a-f]{64}$")

    def test_same_salt_and_text_give_same_hash(self) -> None:
        self.assertEqual(p3.text_hash("t", SALT_A), p3.text_hash("t", SALT_A))

    def test_different_salt_gives_different_hash(self) -> None:
        self.assertNotEqual(p3.text_hash("t", SALT_A), p3.text_hash("t", SALT_B))

    def test_salt_is_actually_used_not_ignored(self) -> None:
        """Guard against a implementation that hashes only the text."""
        self.assertNotEqual(p3.text_hash("t", SALT_A), p3.text_hash("t", "x"))

    def test_empty_or_missing_salt_is_refused(self) -> None:
        for bad in ("", "   ", None, 123, b"bytes"):
            with self.subTest(salt=bad):
                with self.assertRaises(p3.P3Error):
                    p3.text_hash("t", bad)
                with self.assertRaises(p3.P3Error):
                    p3.dedup_key("t", bad)
                with self.assertRaises(p3.P3Error):
                    p3.prepare(["t"], bad)

    def test_no_salt_is_hardcoded_in_the_module(self) -> None:
        source = Path(p3.__file__).read_text(encoding="utf8")
        literals = re.findall(r'"([0-9a-f]{32,})"', source)
        self.assertEqual(literals, [], "a literal salt appears in source")
        self.assertIn("secrets.token_hex", source)

    def test_generated_salts_are_unique_and_strong(self) -> None:
        salts = {p3.generate_salt() for _ in range(50)}
        self.assertEqual(len(salts), 50)
        self.assertTrue(all(len(s) >= 64 for s in salts))
        with self.assertRaises(p3.P3Error):
            p3.generate_salt(8)


class TestAmbiguousLabelExclusion(unittest.TestCase):
    """M3: Profane/Untargeted stays excluded/unknown, never a verified negative."""

    def test_class_4_is_excluded_and_unknown(self) -> None:
        out = p3.map_label(4)
        self.assertEqual(out["status"], "excluded_pending_adjudication")
        self.assertEqual(out["truth"], "unknown")
        self.assertIsNone(out["toxic"])
        self.assertFalse(out["counts_as_verified_negative"])
        self.assertFalse(out["counts_as_verified_positive"])

    def test_class_4_is_never_counted_as_non_toxic(self) -> None:
        for class_id in range(0, 10):
            out = p3.map_label(class_id)
            if class_id in p3.EXCLUDED_CLASSES or out["status"].startswith("unknown"):
                self.assertNotEqual(out["toxic"], 0,
                                    f"class {class_id} wrongly a verified negative")
                self.assertFalse(out["counts_as_verified_negative"])

    def test_approved_m1_and_m2_mappings(self) -> None:
        self.assertEqual(p3.map_label(0)["toxic"], 1)   # Abusive -> toxic
        self.assertEqual(p3.map_label(1)["toxic"], 0)   # Normal  -> non-toxic
        self.assertFalse(p3.map_label(1)["identity_hate"])
        for class_id in (2, 3):                          # M2
            out = p3.map_label(class_id)
            self.assertEqual(out["toxic"], 1)
            self.assertEqual(out["identity_hate"], 1)

    def test_unknown_class_is_unknown_not_a_negative(self) -> None:
        out = p3.map_label(99)
        self.assertEqual(out["status"], "unknown_class")
        self.assertIsNone(out["toxic"])
        self.assertFalse(out["counts_as_verified_negative"])

    def test_non_integer_labels_are_rejected(self) -> None:
        for bad in ("4", None, 4.0, True, [4]):
            with self.subTest(label=bad):
                with self.assertRaises(p3.P3Error):
                    p3.map_label(bad)

    def test_excluded_rows_never_inflate_verified_negatives(self) -> None:
        """4 excluded rows must not increase the verified-negative count."""
        classes = [1, 1, 4, 4, 4, 4]
        mapped = [p3.map_label(c) for c in classes]
        negatives = sum(1 for m in mapped if m["counts_as_verified_negative"])
        excluded = sum(1 for m in mapped
                       if m["status"] == "excluded_pending_adjudication")
        self.assertEqual(negatives, 2, "excluded rows leaked into negatives")
        self.assertEqual(excluded, 4)


class TestIsolation(unittest.TestCase):
    def test_module_imports_no_application_code(self) -> None:
        source = Path(p3.__file__).read_text(encoding="utf8")
        for forbidden in ("import backend", "import ml_service", "sqlite3",
                          "urllib", "requests"):
            self.assertNotIn(forbidden, source)

    def test_module_contains_no_dataset_or_retention_policy(self) -> None:
        """No data path, DB, split or retention value may appear in this module.

        ('ruhsold' is intentionally not on this list: the name is referenced in
        prose to document scope, while the checks below target *operable*
        references such as paths, tables and the retention value.)
        """
        source = Path(p3.__file__).read_text(encoding="utf8").lower()
        for forbidden in ("ur_test", "ur_val", "aura.db", "huggingface",
                          "parquet", "retention_end_date", "dataset_samples",
                          ".csv", "hf_cache"):
            self.assertNotIn(forbidden, source,
                             f"scope leak: {forbidden}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
