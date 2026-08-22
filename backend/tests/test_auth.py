from app.auth import hash_password, verify_password


def test_password_hash_is_salted_and_verifiable():
    first = hash_password("SenhaForte123")
    second = hash_password("SenhaForte123")

    assert first != second
    assert verify_password("SenhaForte123", first) is True
    assert verify_password("senha-errada", first) is False


def test_password_hash_rejects_short_password():
    try:
        hash_password("123")
    except ValueError as exc:
        assert "8" in str(exc)
    else:
        raise AssertionError("short password should be rejected")
