"""Command line access to the ISO limits agent.

    python -m iso_agent "zone B/C boundary for a 55 kW pump, separate driver, rigid"
    python -m iso_agent "is 4.9 mm/s acceptable on a 75 kW pump?"

No API key, no model, no document index -- the answer is a table lookup, so
this runs instantly and costs nothing.

Output is forced to ASCII: a Windows console is cp1252 and cannot encode the
punctuation the tables carry.
"""

from __future__ import annotations

import argparse
import sys
import unicodedata

from iso_agent.agent import ASKS_LIMIT_RE, answer

_TRANSLIT = {"—": "-", "–": "-", "→": "->", "·": "-"}


def _ascii(text: str) -> str:
    out = "".join(_TRANSLIT.get(ch, ch) for ch in text or "")
    return unicodedata.normalize("NFKD", out).encode("ascii", "ignore").decode("ascii")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m iso_agent",
        description="ISO 10816-3 velocity severity limits, looked up rather than generated.",
    )
    parser.add_argument("question", nargs="+", help="The limits question, in plain English")
    parser.add_argument("--json", action="store_true", help="Print the raw lookup instead")
    args = parser.parse_args(argv)

    question = " ".join(args.question)
    result = answer(question)

    if not result.ok:
        print(f"Could not answer: {result.reason}", file=sys.stderr)
        if not ASKS_LIMIT_RE.search(question):
            print(
                "This agent answers severity-limit questions only. For anything "
                "explanatory, ask the knowledge-base agent instead.",
                file=sys.stderr,
            )
        return 1

    if args.json:
        import json

        print(json.dumps(result.payload, indent=2))
    else:
        print(_ascii(result.text))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
