from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest_asyncio

from gptnt.api.room_manager import were_last_n_messages_empty
from gptnt.dialogue_space.server import DialogueSpaceServer
from gptnt.dialogue_space.structures import DialogueSpaceMessage
from gptnt.players.structures import NO_NEW_MESSAGES_SENTINEL


@pytest_asyncio.fixture
async def server(host: str, port: int) -> AsyncGenerator[DialogueSpaceServer, None]:
    server = DialogueSpaceServer.from_host_and_port(host, port)
    for idx in range(10):
        server.messages[idx] = DialogueSpaceMessage(
            sender_uuid=uuid4(), message_id=idx, message_content=f"This is message {idx}"
        )
    async with server:
        yield server


def test_truncation_works_when_expected(server: DialogueSpaceServer) -> None:
    # Fill in messages with 5 do nothing
    for idx in range(5):
        server.messages[len(server.messages) + idx + 1] = DialogueSpaceMessage(
            sender_uuid=uuid4(), message_id=idx, message_content=NO_NEW_MESSAGES_SENTINEL
        )

    # verify that we return true for the truncation

    should_stop = were_last_n_messages_empty(ds_server=server, num_to_check=5)

    assert should_stop is True


def test_truncation_doesnt_work_when_expected(server: DialogueSpaceServer) -> None:
    # Fill in messages with 5 do nothing
    for idx in range(3):
        server.messages[len(server.messages) + idx + 1] = DialogueSpaceMessage(
            sender_uuid=uuid4(), message_id=idx, message_content=NO_NEW_MESSAGES_SENTINEL
        )

    # verify that we return true for the truncation

    should_stop = were_last_n_messages_empty(ds_server=server, num_to_check=5)

    assert should_stop is False
