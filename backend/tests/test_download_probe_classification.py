from app.services.download_probe import _network_unreachable, _public_result


def test_network_unreachable_detection():
    assert _network_unreachable("Failed to establish a new connection: [Errno 101] Network is unreachable")
    assert not _network_unreachable("Sign in to confirm you're not a bot")


def test_bot_block_wins_over_incidental_network_error():
    result = _public_result(
        {
            "ok": False,
            "mode": "cookies",
            "attempts": 12,
            "bot_blocked": True,
            "error": "HTTPSConnection(host='www.youtube.com', port=443): Network is unreachable",
        }
    )
    assert result["failure_kind"] == "youtube_ip_challenge"
    assert result["bot_blocked"] is True
    assert result["network_unreachable"] is True
    assert "anti-bot" in result["error"]


def test_pure_network_failure_stays_network_failure():
    result = _public_result(
        {
            "ok": False,
            "mode": "guest",
            "attempts": 1,
            "bot_blocked": False,
            "error": "No route to host",
        }
    )
    assert result["failure_kind"] == "network_unreachable"
    assert result["bot_blocked"] is False
