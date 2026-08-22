from app.config import Settings


def test_admin_bootstrap_has_no_repository_credential_default():
    settings = Settings(_env_file=None)
    assert settings.admin_bootstrap_email == ""
    assert settings.admin_bootstrap_password_hash == ""
