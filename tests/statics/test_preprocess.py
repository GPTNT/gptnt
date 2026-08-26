from PIL import Image

from gptnt.ktane.manuals.artifacts import ManualArtifact
from gptnt.statics.preprocess import preprocess_expert_ocr_instance, preprocess_expert_vqa_instance


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


def test_expert_vqa_metadata_preserves_large_integers() -> None:
    large_integer = 10**100

    processed = preprocess_expert_vqa_instance(
        {
            "page_number": [1],
            "images": [Image.new("RGB", (1, 1))],
            "manual_texts": ["Cut the wire."],
            "model_input": "Which wire?",
            "metadata": f'{{"seed": {large_integer}}}',
        }
    )

    assert processed["metadata"]["seed"] == large_integer
