import asyncio
import uuid
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.dialogue_space.server import DialogueSpaceServer


@pytest_asyncio.fixture
async def dialogue_space_server(host: str, port: int) -> AsyncGenerator[DialogueSpaceServer, None]:
    server = DialogueSpaceServer.from_host_and_port(host, port)
    async with server:
        yield server


def test_adding_message_to_dialogue_space_works(
    dialogue_space_server: DialogueSpaceServer,
) -> None:
    num_messages = 10
    sender_uuid = uuid.uuid4()

    for message_count in range(num_messages):
        _ = dialogue_space_server.add_message(
            sender_uuid, message=f"This is message {message_count}"
        )

    # Check message store length
    assert len(dialogue_space_server.messages) == num_messages

    # Check the uuid is correct for each message
    for message in dialogue_space_server.messages.values():
        assert message.sender_uuid == sender_uuid

    # Make sure each message ID is correct and sequential
    for idx, (message_id, message) in enumerate(dialogue_space_server.messages.items()):
        assert message.message_id == idx
        assert message_id == idx


@pytest.mark.asyncio
async def test_clients_can_connect_and_disconnect(
    dialogue_space_server: DialogueSpaceServer, host: str, port: int
) -> None:
    num_clients = 3

    for client_idx in range(num_clients):
        client = DialogueSpaceClient.from_host_and_port(host, port)

        assert client.is_connected is False
        await client.connect()
        assert client.is_connected is True

        # Make sure each client is added to the server
        assert len(dialogue_space_server.agents) == client_idx + 1

    # Make sure the server has the correct number of clients
    assert len(dialogue_space_server.agents) == num_clients

    # Close the server
    await dialogue_space_server.close()
    # Make sure the server has no clients after exiting the context manager
    assert len(dialogue_space_server.agents) == 0


@pytest.mark.asyncio
async def test_sent_messages_are_received_by_the_server(
    dialogue_space_server: DialogueSpaceServer, host: str, port: int
) -> None:
    num_clients = 3

    clients = {
        idx: DialogueSpaceClient.from_host_and_port(host, port) for idx in range(num_clients)
    }
    # Connect all the clients
    _ = await asyncio.gather(*[client.connect() for client in clients.values()])

    # Send a message from each client
    for client_idx, client in clients.items():
        await client.send_message(f"Test message: {client_idx}")

        # Check the server has received the messages
        most_recent_message = dialogue_space_server.messages[
            dialogue_space_server.next_message_id - 1
        ]
        assert most_recent_message.message_content == f"Test message: {client_idx}"


@pytest.mark.asyncio
async def test_clients_pull_unread_messages_from_others(
    dialogue_space_server: DialogueSpaceServer, host: str
) -> None:
    num_clients = 3

    clients = {
        idx: DialogueSpaceClient.from_host_and_port(host, dialogue_space_server.server.port)
        for idx in range(num_clients)
    }
    _ = await asyncio.gather(*[client.connect() for client in clients.values()])

    # 1. Make the first client send a message
    await clients[0].send_message("Test message: 0")

    # 1a. make sure the latest message id is 0
    assert dialogue_space_server.next_message_id - 1 == 0

    # 2. Make all clients pull messages
    for client_idx, client in clients.items():
        pulled_messages = await client.pull_messages()

        # If the first client is pulling, it should not be pulling anything
        if client_idx == 0:
            assert len(pulled_messages) == 0
        # Otherwise, all other clients should have the message
        else:
            assert len(pulled_messages) == 1
            assert pulled_messages[0] == "Test message: 0"

    # 3. Check the last read message ID for each agent, should all be identical
    for agent in dialogue_space_server.agents.values():
        assert agent.last_read_message_id == 0

    # 4. Add another message from the first client
    await clients[0].send_message("Test message: 1")

    # 5. Make all clients pull messages again
    for client_idx, client in clients.items():
        pulled_messages = await client.pull_messages()

        # If the first client is pulling, it should not be pulling anything
        if client_idx == 0:
            assert len(pulled_messages) == 0
        # Otherwise, all other clients should have the message
        else:
            assert len(pulled_messages) == 1
            assert pulled_messages[0] == "Test message: 1"

    # 6. Check the last read message ID for each agent, should all be identical
    for agent in dialogue_space_server.agents.values():
        assert agent.last_read_message_id == 1


@pytest.mark.asyncio
async def test_pull_no_messages(dialogue_space_server: DialogueSpaceServer) -> None:
    num_clients = 3
    clients = {
        idx: DialogueSpaceClient.from_host_and_port(
            dialogue_space_server.server.host, dialogue_space_server.server.port
        )
        for idx in range(num_clients)
    }
    _ = await asyncio.gather(*[client.connect() for client in clients.values()])

    for client in clients.values():
        assert len(await client.pull_messages()) == 0
