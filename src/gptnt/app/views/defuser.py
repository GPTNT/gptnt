from typing import override

import gradio as gr

from gptnt.app.views.base_player import BasePlayerView


class DefuserPlayerView(BasePlayerView):
    """View for defuser player."""

    def __init__(self, *, stream_endpoint: str) -> None:
        self.endpoint = stream_endpoint

    @override
    def render_viewing_window(self) -> None:
        """Create video feed for defuser."""
        with gr.Column(scale=2):
            image_html = f"""
            <img src="{self.endpoint}" width="100%" height="750" style="object-fit: cover;">
            """
            self._game_window = gr.HTML(image_html, elem_id="video_feed")

    @override
    def load_custom_js(self) -> str:
        script = """
                function setupClick() {
                    console.log("BEFORE");
                    const video = document.getElementById("video_feed");
                    const boundingBox = video.getBoundingClientRect();
                    video.addEventListener("click", function handleClick(event){
                        console.log("Got click: ", event);
                        const relativeX = event.clientX - boundingBox.left;
                        const relativeY = event.clientY - boundingBox.top;

                        console.log(`Clicked at: X=${relativeX}, Y=${relativeY}`)
                    }, false);

                    console.log("AFTER");

                    return 'Animation created';
                }
            """
        return script
