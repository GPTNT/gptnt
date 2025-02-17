import uuid

import pytest
import structlog
from hypothesis import given, strategies as st

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.dialogue_space.server import DialogueSpaceServer
from gptnt.websocket_api.client import WebsocketClient
from gptnt.websocket_api.server import WebsocketServer

log = structlog.get_logger()

HOST = "localhost"
PORT = 8000


@st.composite
def dialogue_space(draw: st.DrawFn) -> DialogueSpaceServer:  # noqa: ARG001
    """Hypothesis strategy for generating a DialogueSpace object.

    We can't just use a fixture since Hypothesis doesn't play nice with function-scoped fixtures.
    """
    return DialogueSpaceServer(WebsocketServer(host=HOST, port=PORT))


@pytest.mark.asyncio
@given(
    num_messages=st.integers(min_value=1, max_value=10),
    uuid=st.uuids(),
    dialogue_space=dialogue_space(),
)
async def test_adding_message_to_dialogue_space_works(
    dialogue_space: DialogueSpaceServer, num_messages: int, uuid: uuid.UUID
) -> None:
    for message_count in range(num_messages):
        _ = dialogue_space.add_message(uuid, f"This is message {message_count}")

    # Check message store length
    assert len(dialogue_space.messages) == num_messages

    # Check the uuid is correct for each message
    for message in dialogue_space.messages:
        assert message.sender_uuid == uuid

    # Make sure each message ID is correct and sequential
    for idx, message in enumerate(dialogue_space.messages):
        assert message.message_id == idx


@pytest.mark.asyncio
@given(num_clients=st.integers(min_value=1, max_value=3), dialogue_space=dialogue_space())
async def test_clients_can_connect_and_disconnect(
    num_clients: int, dialogue_space: DialogueSpaceServer
) -> None:
    async with dialogue_space as server:
        for client_idx in range(num_clients):
            client = DialogueSpaceClient(WebsocketClient(host=HOST, port=PORT))
            await client.connect()

            # Make sure each client is added to the server
            assert len(server.agents) == client_idx + 1

        # Make sure the server has the correct number of clients
        assert len(server.agents) == num_clients

    # Make sure the server has no clients after exiting the context manager
    assert len(server.agents) == 0


@pytest.mark.asyncio
@given(num_clients=st.integers(min_value=1, max_value=3), dialogue_space=dialogue_space())
async def test_message_received(num_clients: int, dialogue_space: DialogueSpaceServer) -> None:
    async with dialogue_space as server:
        for client_idx in range(num_clients):
            client = DialogueSpaceClient(WebsocketClient(host=HOST, port=PORT))
            await client.connect()
            await client.send_message(f"Test message: {client_idx}")

            most_recent_message = server.messages[-1]
            assert most_recent_message.message_content == f"Test message: {client_idx}"


@pytest.mark.asyncio
@given(num_clients=st.integers(min_value=2, max_value=3), dialogue_space=dialogue_space())
async def test_pull_messages(num_clients: int, dialogue_space: DialogueSpaceServer) -> None:
    async with dialogue_space as _:
        message_count = -1
        # Connect clients
        connected_clients = await connect_clients(num_clients)

        # Connect clients and send message
        for client in connected_clients:
            message_count += 1
            await client.send_message(f"Test message: {message_count}")

        # Check each client pulls all messages
        for client in connected_clients:
            # One message for each client upon joining
            pulled_messages = await client.pull_messages()
            assert len(pulled_messages) == num_clients
            # Check pulled messages are in order
            for message_idx, message in enumerate(pulled_messages):
                assert message == f"Test message: {message_idx}"

        # Now each client has pulled, send additional messages and ensure only new ones are pulled
        for client in connected_clients:
            message_count += 1
            await client.send_message(f"Test message: {message_count}")

        # After each client has sent, pull messages
        for client in connected_clients:
            pulled_messages = await client.pull_messages()
            assert len(pulled_messages) == num_clients
            for message_idx, message in enumerate(pulled_messages):
                log.debug(f"Second pulled messages: {pulled_messages}")
                assert message == f"Test message: {message_idx + num_clients}"

        # No additional messages
        for client in connected_clients:
            pulled_messages = await client.pull_messages()
            assert len(pulled_messages) == 0


@pytest.mark.asyncio
@given(num_clients=st.integers(min_value=2, max_value=4), dialogue_space=dialogue_space())
async def test_pull_no_messages(num_clients: int, dialogue_space: DialogueSpaceServer) -> None:
    async with dialogue_space as _:
        connected_clients = await connect_clients(num_clients)

        for client in connected_clients:
            assert len(await client.pull_messages()) == 0


async def connect_clients(num_clients: int) -> list[DialogueSpaceClient]:
    clients = []
    for _ in range(num_clients):
        client = DialogueSpaceClient(WebsocketClient(HOST, PORT))
        await client.connect()
        clients.append(client)
    return clients
