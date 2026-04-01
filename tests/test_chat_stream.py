import json

from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def _collect_data_lines(response) -> list[str]:
    data_lines: list[str] = []
    for line in response.iter_lines():
        if line.startswith("data: "):
            data_lines.append(line[6:])
    return data_lines


def test_chat_stream_message_flow() -> None:
    with client.stream("POST", "/chat/stream", json={"message": "xin chao"}) as response:
        assert response.status_code == 200
        data_lines = _collect_data_lines(response)

    assert any(json.loads(item).get("type") == "message" for item in data_lines if item != "[DONE]")
    assert any(json.loads(item).get("type") == "done" for item in data_lines if item != "[DONE]")
    assert data_lines[-1] == "[DONE]"


def test_chat_stream_hidden_event_flow() -> None:
    payload = {
        "message": "",
        "hidden_events": {
            "action": "open_product_modal",
            "payload": {"id": 123},
        },
    }

    with client.stream("POST", "/chat/stream", json=payload) as response:
        assert response.status_code == 200
        data_lines = _collect_data_lines(response)

    parsed = [json.loads(item) for item in data_lines if item != "[DONE]"]
    assert any(chunk.get("type") == "a2ui" for chunk in parsed)
    assert data_lines[-1] == "[DONE]"

