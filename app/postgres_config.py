"""Non-secret identity of this project's private PostgreSQL deployment."""
from urllib.parse import quote, urlsplit

PG_SERVICE = "psych_quiz_postgres"
PG_DATABASE = "psychology_atlas"
PG_ROLE = "psychology_app"
PG_IMAGE = "postgres:18.6-bookworm@sha256:3725f4e2499eef5134592b3b4ab79a543ed7f8e533b05b5b637af926630f6650"


def private_target(password: str, *, database: str = PG_DATABASE) -> str:
    if database not in {PG_DATABASE, "postgres"}:
        raise ValueError("Unexpected PostgreSQL target")
    return f"postgresql://{PG_ROLE}:{quote(password, safe='')}@{PG_SERVICE}:5432/{database}"


def validate_delivery_target(target: str) -> None:
    parsed = urlsplit(target)
    if (parsed.scheme != "postgresql" or parsed.hostname != PG_SERVICE or parsed.port != 5432
            or parsed.username != PG_ROLE or parsed.path != "/" + PG_DATABASE
            or not parsed.password or parsed.query or parsed.fragment):
        raise ValueError("PostgreSQL delivery requires the private project database and role")
