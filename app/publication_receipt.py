"""Source-free repository review receipt; Git review is its trust boundary.

A receipt binds an exact public revision to a privately validated dossier.
It is not cryptographic proof or independent evidence of a source's truth.
"""
from datetime import date
import re

HEX64 = re.compile(r"[0-9a-f]{64}")


def required_checks(kind):
    return ({"meaning", "definition", "examples", "ambiguity", "duplicates", "sources"}
            if kind == "glossary" else
            {"meaning", "answer", "explanation", "ambiguity", "duplicates", "sources"}
            if kind == "questions" else {"sources"})


def receipt_error(kind, receipt, *, item_sha256):
    fields = {"schema_version", "item_sha256", "review_sha256", "decision", "purpose",
              "reviewer", "reviewed_at", "checks", "source_support"}
    if isinstance(receipt, dict) and "topic_id" in receipt:
        fields.add("topic_id")
    if (kind not in {"questions", "glossary", "literature"}
            or not isinstance(receipt, dict) or set(receipt) != fields
            or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or receipt["item_sha256"] != item_sha256
            or any(not isinstance(receipt[field], str) or HEX64.fullmatch(receipt[field]) is None
                   for field in ("item_sha256", "review_sha256"))
            or receipt["decision"] != "approved" or receipt["source_support"] != "supported"
            or receipt["purpose"] != ("bibliographic_metadata" if kind == "literature" else "learning_content")
            or not isinstance(receipt["reviewer"], str)
            or re.fullmatch(r"[\w.-]{1,64}", receipt["reviewer"]) is None
            or not isinstance(receipt["checks"], list)
            or any(not isinstance(check, str) for check in receipt["checks"])
            or len(receipt["checks"]) != len(required_checks(kind))
            or set(receipt["checks"]) != required_checks(kind)):
        return "invalid_publication_receipt"
    if "topic_id" in receipt and (kind != "questions" or not isinstance(receipt["topic_id"], str)
                                  or re.fullmatch(r"t_[a-f0-9]{12}", receipt["topic_id"]) is None):
        return "invalid_publication_receipt"
    try:
        if not isinstance(receipt["reviewed_at"], str) or date.fromisoformat(receipt["reviewed_at"]).isoformat() != receipt["reviewed_at"]:
            return "invalid_publication_receipt"
    except ValueError:
        return "invalid_publication_receipt"
    return None
