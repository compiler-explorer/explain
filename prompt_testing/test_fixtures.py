"""Guards for the curated test-case fixtures."""

from pathlib import Path

import pytest

from prompt_testing.ce_api.models import derive_label_definitions
from prompt_testing.file_utils import load_all_test_cases

CASES = load_all_test_cases(str(Path(__file__).parent / "test_cases"))


def test_case_ids_are_unique():
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case_has_real_assembly(case):
    assert case["input"]["asm"], "empty asm: the compile produced no code (e.g. a Rust leaf fn inlined away)"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_label_definitions_are_compiler_explorers_map(case):
    """`labelDefinitions` must be label -> 1-based line of its definition in the filtered asm, as CE sends it.

    An earlier enrich client derived it from label *references* (0-based, first use), which fed the model
    line numbers that contradicted the listing.
    """
    texts = [a["text"] for a in case["input"]["asm"]]
    assert dict(case["input"].get("labelDefinitions") or {}) == derive_label_definitions(texts)
