from typing import override

import gradio as gr

from gptnt.app.views.base_player import BasePlayerView


class ExpertPlayerView(BasePlayerView):
    """View for Expert player."""

    role = "expert"

    def __init__(self, *, pdf_endpoint: str) -> None:
        super().__init__()
        self.endpoint = pdf_endpoint

    @override
    def render_viewing_window(self) -> None:
        """Create pdf-viewer for expert."""
        with gr.Column(scale=2):
            viewer_html = f"""
            <object data="{self.endpoint}" type="application/pdf" width="900px" height="750px">
                <embed src="{self.endpoint}" type="application/pdf">
                    <p>This browser does not support PDFs. Please download the PDF to view it: <a href="{self.endpoint}">Download PDF</a>.</p>
                </embed>
            </object>
            """
            self._pdf_viewer = gr.HTML(viewer_html)

    @override
    def load_custom_js(self) -> str:
        """No embedded js needed for this view."""
        return ""
