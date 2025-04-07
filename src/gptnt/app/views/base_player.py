from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any, ClassVar

import gradio as gr


class BasePlayerView(ABC):
    """ABC for all the views, bringing common functionality across them."""

    role: ClassVar[str]

    def __init__(self) -> None:
        self.message_history: list[gr.ChatMessage] = []

    @abstractmethod
    def render_viewing_window(self) -> None:
        """Create a viewing window for video feeds/pdf reader/etc."""
        raise NotImplementedError

    @abstractmethod
    def load_custom_js(self) -> str:
        """Javascript to be embedded into gradio interface."""
        raise NotImplementedError

    def build_layout(
        self, handle_send: Callable[..., Any], handle_pull: Callable[..., Any]
    ) -> gr.Blocks:
        """Generate layout of interface with controller callbacks."""
        with gr.Blocks(js=self.load_custom_js()) as demo:
            # Put tailored component in same row as chatbox
            with gr.Row(equal_height=True):
                self.render_viewing_window()
                self._create_chatbox()
            # Have all dialogue components below on different columns
            self._create_message_input_ui()
            self._setup_chat_interactions(handle_send)

            # Run message polling function on gradio app load
            _ = demo.load(fn=handle_pull, outputs=[self._chatbox])

            return demo

    def add_external_message(self, message: str) -> list[gr.ChatMessage]:
        """Add message from external player to history box.

        For example, from an AI assistant or other human player.
        """
        self.message_history.append(gr.ChatMessage(content=message, role="assistant"))
        return self.message_history

    def add_user_message(self, message: str) -> None:
        """Add message from user player to history box."""
        self.message_history.append(gr.ChatMessage(content=message, role="user"))

    def _create_chatbox(self) -> None:
        """Create chatbox interface."""
        with gr.Column(scale=2):
            self._chatbox = gr.Chatbot(
                [],
                label="agent chat",
                elem_id="chatbox",
                height="750px",
                show_label=False,
                type="messages",
            )

    def _create_message_input_ui(self) -> None:
        """Create user message input and send button."""
        with gr.Row():
            with gr.Column(scale=4):
                self._user_msg = gr.Textbox(
                    show_label=False, placeholder="Type your message here...", container=False
                )
            with gr.Column(scale=1):
                self._user_send = gr.Button("Send")

    def _setup_chat_interactions(self, handle_send: Callable[..., Any]) -> None:
        """Set up interactions with controller callbacks."""
        _ = self._user_send.click(
            handle_send, inputs=[self._user_msg], outputs=[self._chatbox, self._user_msg]
        )
        _ = self._user_msg.submit(
            handle_send, inputs=[self._user_msg], outputs=[self._chatbox, self._user_msg]
        )
