from functools import partial
from pathlib import Path
from typing import override

import gradio as gr
from structlog import getLogger

from gptnt.ktane.actions import GameActionType, KtaneAction, RelativeCoordinate
from gptnt.ktane.client import KtaneClient
from gptnt.players.human.views.base_view import BaseView

logger = getLogger()


class DefuserPlayerView(BaseView):
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
            # Build the game viewing window
            image_html = (
                '<img id="img_tag" src="" width="100%" height="750" style="object-fit: cover;">'
            )
            self._game_window = gr.HTML(image_html, elem_id="video_feed")
            output = gr.Textbox(label="Response from Python", elem_id="real_box", visible=False)
            _ = output.input(fn=self._handle_textbox_change, inputs=[output], outputs=None)

            # Discrete Action Buttons
            with gr.Column(scale=3):
                with gr.Row():
                    self._button_left = gr.Button("Turn Left")
                    self._button_right = gr.Button("Turn Right")
                    self._button_around = gr.Button("Turn Around")

                with gr.Row():
                    self._button_roll_up = gr.Button("Roll Up")
                    self._button_roll_down = gr.Button("Roll Down")
                    self._button_zoom_out = gr.Button("Zoom Out")

        # Registering the actions
        _ = self._button_left.click(
            fn=partial(self._handle_discrete_action, GameActionType.rotate_left)
        )
        _ = self._button_right.click(
            fn=partial(self._handle_discrete_action, GameActionType.rotate_right)
        )
        _ = self._button_around.click(
            fn=partial(self._handle_discrete_action, GameActionType.flip)
        )
        _ = self._button_roll_up.click(
            fn=partial(self._handle_discrete_action, GameActionType.roll_up)
        )
        _ = self._button_roll_down.click(
            fn=partial(self._handle_discrete_action, GameActionType.roll_down)
        )
        _ = self._button_zoom_out.click(
            fn=partial(self._handle_discrete_action, GameActionType.zoom_out)
        )

    @override
    def load_custom_js(self) -> str:
        base_url = self.ktane_client.client.base_url
        script = Path(__file__).parent.joinpath("defuser_script.js").read_text()
        script = script.replace("`{observation_endpoint}`", f'"{base_url}/screenshot"')
        return script

    async def _handle_textbox_change(self, text: str) -> None:
        # Parse JS mouse events and send to KTANE client
        logger.info(text)
        match text.split(sep=" "):
            case ["Mousedown", _, "X:", event_x, "Y:", event_y, _, _]:
                # Hold
                action = KtaneAction(
                    action=GameActionType.hold,
                    location=RelativeCoordinate(x_pos=float(event_x), y_pos=float(event_y)),
                )
                _ = await self.ktane_client.send_action(action)
                self.previous_event = "Mousedown"

            case ["Mouseup", _, "X:", event_x, "Y:", event_y, _, _]:
                if self.previous_event == "Mousedown":
                    # Release
                    action = KtaneAction(action=GameActionType.release)
                else:
                    # Click
                    action = KtaneAction(
                        action=GameActionType.click_release,
                        location=RelativeCoordinate(x_pos=float(event_x), y_pos=float(event_y)),
                    )

                _ = await self.ktane_client.send_action(action)
                self.previous_event = "Mouseup"

            # Incorrect event (throw error?)
            case err:
                logger.error(f"Invalid  mouse-event format received from JS: {err}")

    async def _handle_discrete_action(self, action_type: GameActionType) -> None:
        """Send the discrete action to the KTANE Client."""
        logger.debug(action_type)
        action = KtaneAction(action=action_type)
        _ = await self.ktane_client.send_action(action)
