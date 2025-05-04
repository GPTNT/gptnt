from gptnt.api.experiment import were_last_n_messages_empty
from gptnt.players.structures import NO_NEW_MESSAGES_SENTINEL


def test_truncation_works_when_expected() -> None:
    # Fill in messages with 5 do nothing
    messages = [f"this is message {idx}" for idx in range(5)]
    messages = [*messages, *[NO_NEW_MESSAGES_SENTINEL for _ in range(5)]]
    should_stop = were_last_n_messages_empty(raw_ds_messages=messages, num_to_check=5)

    assert should_stop is True


def test_truncation_doesnt_work_when_expected() -> None:
    # Fill in messages with 5 do nothing
    messages = [f"this is message {idx}" for idx in range(5)]
    messages = [*messages, *[NO_NEW_MESSAGES_SENTINEL for _ in range(3)]]
    should_stop = were_last_n_messages_empty(raw_ds_messages=messages, num_to_check=5)

    assert should_stop is False
