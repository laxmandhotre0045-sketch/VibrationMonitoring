"""Generate a sample HR document PDF for local testing."""

from pathlib import Path

import fitz

CONTENT = """
CHAPTER 3
LEAVE

SECTION 3.1 CASUAL LEAVE
Employees are entitled to 12 days of casual leave per calendar year.
Casual leave must be applied at least one day in advance through the HR portal.
Unused casual leave does not carry forward to the next year.

SECTION 3.2 SICK LEAVE
Employees receive 10 days of sick leave annually.
A medical certificate is required for sick leave exceeding 2 consecutive days.

SECTION 3.3 ANNUAL LEAVE
Full-time employees accrue 21 days of annual leave per year.
Annual leave requests require manager approval at least 7 days in advance.
"""


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "sample_document.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), CONTENT.strip(), fontsize=11, fontname="helv")
    doc.save(out)
    doc.close()
    print(f"Created {out}")


if __name__ == "__main__":
    main()
