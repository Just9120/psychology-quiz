"""Conservative locator checks shared by private review and publication."""

import re


_WHOLE_EXTRACTED_TEXT_RANGE = re.compile(
    r"extracted text, Unicode characters \(zero-based, end exclusive\): 0:\d+"
)


def locator_precision_review_required(locator: str) -> bool:
    """Flag a 0:end reference for review; its actual scope needs source text."""
    return bool(_WHOLE_EXTRACTED_TEXT_RANGE.fullmatch(locator.strip()))
