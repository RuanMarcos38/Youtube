from app.config import Settings, normalize_postgres_database_url


def test_prisma_supabase_query_parameters_are_removed_for_psycopg():
    source = (
        "postgresql://user:secret@db.example.com:6543/postgres"
        "?schema=public&pgbouncer=true&connection_limit=1&pool_timeout=10"
        "&sslmode=require&connect_timeout=5"
    )

    value = normalize_postgres_database_url(source)

    assert value.startswith("postgresql+psycopg://user:secret@db.example.com:6543/postgres?")
    assert "schema=" not in value
    assert "pgbouncer=" not in value
    assert "connection_limit=" not in value
    assert "pool_timeout=" not in value
    assert "sslmode=require" in value
    assert "connect_timeout=5" in value


def test_legacy_postgres_scheme_is_converted():
    assert normalize_postgres_database_url("postgres://u:p@host/db?sslmode=require") == (
        "postgresql+psycopg://u:p@host/db?sslmode=require"
    )


def test_settings_uses_sanitized_database_url():
    configured = Settings(
        _env_file=None,
        database_url="postgresql://u:p@host/db?schema=public&sslmode=require",
    )
    assert configured.sqlalchemy_database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_non_postgres_urls_are_not_rewritten():
    assert normalize_postgres_database_url("sqlite:///data/app.db") == "sqlite:///data/app.db"
