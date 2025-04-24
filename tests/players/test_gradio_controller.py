"""Import asyncio from collections.abc import AsyncGenerator from pathlib import Path.

import pytest
import pytest_asyncio
from httpx import AsyncClient
from pydantic import TypeAdapter
from pytest_cases import parametrize_with_cases

from gptnt.dialogue_space.client import DialogueSpaceClient
from gptnt.dialogue_space.server import DialogueSpaceServer
from gptnt.ktane.client import KtaneClient
from gptnt.players.human.controller import Controller
from gptnt.players.human.views.base_view import ChatMessage
from gptnt.players.human.views.defuser import DefuserPlayerView
from gptnt.players.human.views.expert import ExpertPlayerView


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
        httpx_client = AsyncClient(base_url="http://localhost:1235")
        ktane_client = KtaneClient(client=httpx_client)
        defuser_view = DefuserPlayerView(
            stream_endpoint="http://localhost:5000/video_feed", ktane_client=ktane_client
        )
        return Controller(view=defuser_view, dialogue_space_client=ds_client)


@pytest.fixture(scope="session")
def saved_chats_temp_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("gradio_chats")


@pytest.mark.asyncio
@parametrize_with_cases("controller", cases=PlayerControllerCases)
async def test_send_button_updates_history(
    controller: Controller, ds_server: DialogueSpaceServer
) -> None:
    num_messages = 5

    # Connect to dialogue space.
    await controller.dialogue_space_client.connect()

    # Create 'empty' chat history
    history: list[ChatMessage] = []

    for message_idx in range(num_messages):
        message = f"TEST MESSAGE {message_idx}"
        history, text_box_content = await controller.handle_user_message(message)
        # Text box should be cleared
        assert text_box_content == ""
        # Chat history should be updated
        assert history[-1].content == message
        assert history[-1].role == "user"
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
    await controller.dialogue_space_client.connect()

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


@pytest.mark.asyncio
@parametrize_with_cases("controller", cases=PlayerControllerCases)
async def test_save_messages(controller: Controller, saved_chats_temp_dir: Path) -> None:
    num_messages = 5
    await controller.dialogue_space_client.connect()

    for message_idx in range(num_messages):
        controller_msg = f"CONTROLLER TEST MESSAGE {message_idx}"

        _ = await controller.handle_user_message(controller_msg)

    log_path = controller.handle_save_history(saved_chats_temp_dir)
    log_json = log_path.read_text()
    chat_messages: list[ChatMessage] = TypeAdapter(list[ChatMessage]).validate_json(log_json)

    assert len(chat_messages) == num_messages
    for idx, msg in enumerate(chat_messages):
        assert msg.content == f"CONTROLLER TEST MESSAGE {idx}"
"""
