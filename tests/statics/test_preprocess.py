from PIL import Image

from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.statics.preprocess import preprocess_expert_ocr_instance


def test_expert_ocr_preserves_the_loaded_image() -> None:
    processed = preprocess_expert_ocr_instance(
        {"image": Image.new("RGB", (1, 1)), "module": "Wires", "question": "Which wires?"}
    )

    assert processed["image"] is processed["model_input"][0]


def test_expert_ocr_uses_text_from_an_explicit_artifact(
    prepared_manual_artifact: ManualArtifact,
) -> None:
    processed = preprocess_expert_ocr_instance(
        {"image": Image.new("RGB", (1, 1)), "module": "Wires", "question": "Which wires?"},
        manual_artifact=prepared_manual_artifact,
    )

    assert "SHARED PREPARED MANUAL" in processed["model_input"][0]
    assert processed["image"] is processed["model_input"][1]
