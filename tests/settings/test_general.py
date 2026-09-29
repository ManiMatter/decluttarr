from src.settings._general import General


def test_request_timeout_defaults_to_15_seconds():
    general = General({})

    assert general.request_timeout == 15.0


def test_request_timeout_accepts_numeric_strings():
    general = General({"general": {"request_timeout": "42"}})

    assert general.request_timeout == 42.0


def test_remove_from_queue_is_a_valid_tracker_handling_value():
    """remove_from_queue clears the arr queue while leaving the torrent in the client."""
    general = General({"general": {"private_tracker_handling": "remove_from_queue"}})

    assert general.private_tracker_handling == "remove_from_queue"
