import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from gradio import ChatMessage
from pytest_cases import parametrize_with_cases

from gptnt.app.controller import Controller
from gptnt.app.views.defuser import DefuserPlayerView
from gptnt.app.views.expert import ExpertPlayerView
from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.dialogue_space.server import DialogueSpaceServer


@pytest_asyncio.fixture
async def ds_server(host: str, port: int) -> AsyncGenerator[DialogueSpaceServer, None]:
    server = DialogueSpaceServer.from_host_and_port(host, port)
    async with server:
        yield server


@pytest.fixture
def ds_client(ds_server: DialogueSpaceServer) -> DialogueSpaceClient:
    return DialogueSpaceClient.from_host_and_port(ds_server.server.host, ds_server.server.port)


class PlayerControllerCases:
    def case_expert(self, ds_client: DialogueSpaceClient) -> Controller:
        expert_view = ExpertPlayerView(
            pdf_endpoint="https://www.bombmanual.com/print/KeepTalkingAndNobodyExplodes-BombDefusalManual-v1.pdf"
        )
        return Controller(view=expert_view, dialogue_space_client=ds_client)

    def case_defuser(self, ds_client: DialogueSpaceClient) -> Controller:
        defuser_view = DefuserPlayerView(stream_endpoint="http://localhost:5000/video_feed")
        return Controller(view=defuser_view, dialogue_space_client=ds_client)


@pytest.mark.asyncio
@parametrize_with_cases("controller", cases=PlayerControllerCases)
async def test_send_button_updates_history(
    controller: Controller, ds_server: DialogueSpaceServer
) -> None:
    num_messages = 5

    # Connect to dialogue space.
    await controller.ds_client.connect()

    # Create 'empty' chat history
    history: list[ChatMessage] = []

    for message_idx in range(num_messages):
        message = f"TEST MESSAGE {message_idx}"
        history, text_box_content = await controller.handle_user_message(message)
        # Text box should be cleared
        assert text_box_content == ""
        # Chat history should be updated
        assert history[-1] == ChatMessage(content=message, role="user")
        # Dialogue space should have received message
        assert ds_server.messages[message_idx].message_content == message


@pytest.mark.asyncio
@parametrize_with_cases("controller", cases=PlayerControllerCases)
async def test_pulling(controller: Controller, ds_server: DialogueSpaceServer) -> None:
    num_messages = 5
    poll_interval = 0.5
    other_client = DialogueSpaceClient.from_host_and_port(
        ds_server.server.host, ds_server.server.port
    )

    await other_client.connect()
    await controller.ds_client.connect()

    # No messages in history yet
    chat_history = []

    for message_idx in range(num_messages):
        message_content = f"TEST MESSAGE {message_idx}"
        await other_client.send_message(message_content)

        try:
            # Time out after waiting for poll_interval * 5
            new_chat_history = await asyncio.wait_for(
                anext(controller.poll_and_add_new_messages()), timeout=poll_interval * 5
            )
            # Only one new message
            assert len(new_chat_history) - len(chat_history) == 1
            # New message has right body
            assert new_chat_history[-1].content == message_content
            chat_history = new_chat_history.copy()
        except TimeoutError:
            pytest.fail(f"Timed out waiting for message {message_idx}")
