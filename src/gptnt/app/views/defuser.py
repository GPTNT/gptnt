from pathlib import Path
from typing import override

import gradio as gr
from structlog import getLogger

from gptnt.app.views.base_player import BasePlayerView
from gptnt.ktane.actions import GameActionType, KtaneAction, RelativeCoordinate
from gptnt.ktane.client import KtaneClient

logger = getLogger()


class DefuserPlayerView(BasePlayerView):
    """View for defuser player."""

    role = "defuser"
    previous_event = ""

    def __init__(self, *, stream_endpoint: str, ktane_client: KtaneClient) -> None:
        super().__init__()
        self.endpoint = stream_endpoint
        self.ktane_client = ktane_client

    @override
    def render_viewing_window(self) -> None:
        """Create video feed for defuser."""
        with gr.Column(scale=2):
            image_html = f"""
            <img src="{self.endpoint}" width="100%" height="750" style="object-fit: cover;">
            """
            self._game_window = gr.HTML(image_html, elem_id="video_feed")
            output = gr.Textbox(label="Response from Python", elem_id="real_box", visible=False)
            _ = output.input(fn=self._handle_textbox_change, inputs=[output], outputs=None)

    @override
    def load_custom_js(self) -> str:
        return Path(__file__).parent.joinpath("defuser_script.js").read_text()

    def _handle_textbox_change(self, text: str) -> None:
        # Parse JS mouse events and send to KTANE client
        logger.info(text)
        match text.split(sep=" "):
            case ["Mousedown", _, "X:", event_x, "Y:", event_y, _, _]:
                # Hold
                action = KtaneAction(
                    action=GameActionType.hold,
                    location=RelativeCoordinate(x_pos=float(event_x), y_pos=float(event_y)),
                )
                _ = self.ktane_client.send_action(action)
                self.previous_event = "Mousedown"

            case ["Mouseup", _, "X:", event_x, "Y:", event_y, _, _]:
                if self.previous_event == "Mousedown":
                    # Release
                    action = KtaneAction(action=GameActionType.release)
                else:
                    # Click
                    action = KtaneAction(
                        action=GameActionType.click,
                        location=RelativeCoordinate(x_pos=float(event_x), y_pos=float(event_y)),
                    )

                _ = self.ktane_client.send_action(action)
                self.previous_event = "Mouseup"

            # Incorrect event (throw error?)
            case err:
                logger.error(f"Invalid  mouse-event format recieved from JS: {err}")
