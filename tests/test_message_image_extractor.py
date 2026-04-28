import json

from app.services.message_image_extractor import extract_image_keys_from_message_content


def test_extract_image_key_from_image_message() -> None:
    content = json.dumps({"image_key": "img_123"})

    assert extract_image_keys_from_message_content("image", content) == ["img_123"]


def test_extract_image_key_from_post_message() -> None:
    content = json.dumps(
        {
            "title": "",
            "content": [
                [
                    {"tag": "at", "user_name": "OCR机器人"},
                    {"tag": "text", "text": " "},
                ],
                [
                    {
                        "tag": "img",
                        "image_key": "example_image_key",
                        "width": 812,
                        "height": 1356,
                    }
                ],
            ],
        }
    )

    assert extract_image_keys_from_message_content("post", content) == ["example_image_key"]


def test_extract_multiple_image_keys_from_post_message() -> None:
    content = json.dumps(
        {
            "title": "",
            "content": [
                [
                    {"tag": "img", "image_key": "img_1"},
                    {"tag": "img", "image_key": "img_2"},
                ],
                [
                    {"tag": "text", "text": "done"},
                    {"tag": "img", "image_key": "img_3"},
                ],
            ],
        }
    )

    assert extract_image_keys_from_message_content("post", content) == ["img_1", "img_2", "img_3"]


def test_extract_image_key_returns_empty_for_text_message() -> None:
    content = json.dumps({"text": "hello"})

    assert extract_image_keys_from_message_content("text", content) == []
