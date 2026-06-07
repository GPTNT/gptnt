from pytest_cases import parametrize

from gptnt.core.common.image_ops import ImageDimensions
from gptnt.core.ktane.manual import (
    APPENDIX_PAGES,
    EXPLAINER_PAGES_TO_REMOVE,
    NEEDY_MODULE_PAGE_NUMS,
)
from gptnt.core.prompts.manual import load_manual_as_prompt


@parametrize(("width", "height"), [(800, 600), (640, 480), (480, 640), (100, 100)])
def test_manual_loads_consistently_without_error(width: int, height: int) -> None:
    """Test that the manual loads from the function without error."""
    desired_image_dimensions = ImageDimensions(width=width, height=height)
    manual_prompt = load_manual_as_prompt(image_dimensions=desired_image_dimensions)
    assert manual_prompt
    manual_prompt = load_manual_as_prompt(image_dimensions=desired_image_dimensions)
    assert manual_prompt
    manual_prompt = load_manual_as_prompt(image_dimensions=desired_image_dimensions)
    assert manual_prompt


@parametrize("should_skip", [True, False], ids=["skip_needy_modules", "don't_skip_needy_modules"])
def test_needy_module_pages_are_controlled(should_skip: bool) -> None:
    """Test that the needy module pages are skipped."""
    manual_prompt = load_manual_as_prompt(skip_needy_modules=should_skip)
    manual_prompt_texts = [page for page in manual_prompt if isinstance(page, str)]
    all_text = " ".join(manual_prompt_texts)

    page_numbers = [f"Page {num} of 23" for num in NEEDY_MODULE_PAGE_NUMS]

    for page_number in page_numbers:
        if should_skip:
            assert page_number not in all_text
        else:
            assert page_number in all_text


@parametrize(
    "should_skip", [True, False], ids=["skip_explainer_pages", "don't_skip_explainer_pages"]
)
def test_explainer_pages_are_controlled(should_skip: bool) -> None:
    """Test that the explainer pages are skipped."""
    manual_prompt = load_manual_as_prompt(skip_explainer_pages=should_skip)
    manual_prompt_texts = [page for page in manual_prompt if isinstance(page, str)]
    all_text = " ".join(manual_prompt_texts)

    page_numbers = [f"Page {num} of 23" for num in EXPLAINER_PAGES_TO_REMOVE if num != 1]
    # Page 1 is a special case because it contains the identifier string, so we check for a string
    page_numbers.append("Verification Code: 241")
    for page_number in page_numbers:
        if should_skip:
            assert page_number not in all_text
        else:
            assert page_number in all_text


@parametrize(
    "should_skip", [True, False], ids=["skip_appendix_pages", "don't_skip_appendix_pages"]
)
def test_appendix_pages_are_controlled(should_skip: bool) -> None:
    """Test that the appendix pages are skipped."""
    manual_prompt = load_manual_as_prompt(skip_appendix_pages=should_skip)
    manual_prompt_texts = [page for page in manual_prompt if isinstance(page, str)]
    all_text = " ".join(manual_prompt_texts)

    page_numbers = [f"Page {num} of 23" for num in APPENDIX_PAGES]

    for page_number in page_numbers:
        if should_skip:
            assert page_number not in all_text
        else:
            assert page_number in all_text
