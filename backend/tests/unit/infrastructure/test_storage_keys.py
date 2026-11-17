"""
Unit tests for the object-key builder.

`build_key` and `validate_key` exist to make three real classes of incident
impossible: keys built from a user's file name (collisions and traversal), keys
assembled with f-strings that drift from the layout lifecycle/IAM rules depend
on, and leading slashes that break prefix queries. These tests pin each of those
refusals, plus the normal happy-path shape.
"""

import re

import pytest

from src.infrastructure.external.storage.storage_keys import (
    MAX_KEY_BYTES,
    InvalidStorageKeyError,
    build_key,
    safe_file_name,
    validate_key,
)


class TestBuildKey:
    def test_layout_is_prefix_segments_then_uuid_with_extension(self) -> None:
        key = build_key("documents", "42", file_name="Q3 Report.pdf", prefix="arch/prod")

        assert re.fullmatch(r"arch/prod/documents/42/[0-9a-f]{32}\.pdf", key)

    def test_uuid_makes_two_calls_for_the_same_inputs_distinct(self) -> None:
        """Two users uploading report.pdf to the same entity must not collide."""
        first = build_key("documents", "42", file_name="report.pdf")
        second = build_key("documents", "42", file_name="report.pdf")

        assert first != second

    def test_only_the_extension_of_the_file_name_is_used(self) -> None:
        key = build_key("documents", "42", file_name="../../etc/passwd.pdf")

        # The name contributes '.pdf' and nothing else — no path, no traversal.
        assert "passwd" not in key
        assert ".." not in key
        assert key.endswith(".pdf")

    def test_no_file_name_yields_a_key_without_extension(self) -> None:
        key = build_key("avatars", "7")

        assert re.fullmatch(r"avatars/7/[0-9a-f]{32}", key)

    def test_a_slash_in_a_segment_is_rejected(self) -> None:
        with pytest.raises(InvalidStorageKeyError):
            build_key("documents/42", file_name="x.pdf")

    def test_a_traversal_segment_is_rejected(self) -> None:
        with pytest.raises(InvalidStorageKeyError):
            build_key("documents", "..", file_name="x.pdf")

    def test_no_segments_is_rejected(self) -> None:
        with pytest.raises(InvalidStorageKeyError):
            build_key(file_name="x.pdf")


class TestValidateKey:
    def test_a_well_formed_key_is_returned_unchanged(self) -> None:
        key = "documents/42/abc123.pdf"

        assert validate_key(key) == key

    @pytest.mark.parametrize(
        "bad_key",
        [
            "",
            "   ",
            "/leading-slash.pdf",
            "documents/../secret.pdf",
            "documents//x.pdf",
            "documents/./x.pdf",
        ],
    )
    def test_malformed_keys_are_rejected(self, bad_key: str) -> None:
        with pytest.raises(InvalidStorageKeyError):
            validate_key(bad_key)

    def test_a_key_over_the_byte_limit_is_rejected(self) -> None:
        too_long = "a/" + "b" * MAX_KEY_BYTES

        with pytest.raises(InvalidStorageKeyError):
            validate_key(too_long)


class TestSafeFileName:
    def test_accents_are_folded_not_stripped(self) -> None:
        assert safe_file_name("résumé.pdf") == "resume.pdf"

    def test_a_full_windows_path_is_reduced_to_the_leaf(self) -> None:
        assert safe_file_name(r"C:\Users\me\Q3 Report.pdf") == "Q3-Report.pdf"

    def test_unsafe_characters_become_hyphens(self) -> None:
        assert safe_file_name("in voice #7!.pdf") == "in-voice-7.pdf"

    def test_empty_or_none_falls_back(self) -> None:
        assert safe_file_name(None) == "file"
        assert safe_file_name("") == "file"
