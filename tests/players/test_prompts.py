from gptnt.players.ai.prompts import NEEDY_MODULE_PAGE_NUMS, load_manual_as_prompt


def test_manual_loads_consistently_without_error() -> None:
    """Test that the manual loads from the function without error."""
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt
    manual_prompt = load_manual_as_prompt()
    assert manual_prompt


def test_needy_module_pages_are_skipped() -> None:
    """Test that the needy module pages are skipped."""
    manual_prompt = load_manual_as_prompt()
    mamual_prompt_texts = [page for page in manual_prompt if isinstance(page, str)]

    page_numbers = [
        *[f"{num}/23" for num in NEEDY_MODULE_PAGE_NUMS],
        *[f"Page {num} of 23" for num in NEEDY_MODULE_PAGE_NUMS],
    ]

    for page in mamual_prompt_texts:
        for page_number in page_numbers:
            assert page_number not in page
