from PIL import Image

from gptnt.statics.preprocess import preprocess_expert_ocr_instance


def test_expert_ocr_preserves_the_loaded_image() -> None:
    processed = preprocess_expert_ocr_instance(
        {"image": Image.new("RGB", (1, 1)), "module": "Wires", "question": "Which wires?"}
    )

    assert processed["image"] is processed["model_input"][0]
