import stock_service


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_call_gemini_once_uses_120s_timeout(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "ok"}]},
                        "finishReason": "STOP",
                    }
                ]
            }
        )

    monkeypatch.setattr(stock_service.requests, "post", fake_post)

    stock_service._call_gemini_once("prompt", "k", "gemini-test")

    assert captured["timeout"] == 120


def test_call_gemini_once_skips_google_search_tool_when_disabled(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["payload"] = json
        return _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {"parts": [{"text": "ok"}]},
                        "finishReason": "STOP",
                    }
                ]
            }
        )

    monkeypatch.setattr(stock_service.requests, "post", fake_post)

    stock_service._call_gemini_once("prompt", "k", "gemini-test", enable_model_search=False)

    assert "tools" not in captured["payload"]


def test_call_claude_once_uses_120s_timeout(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse({"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"})

    monkeypatch.setattr(stock_service.requests, "post", fake_post)

    stock_service._call_claude_once("prompt", "k", "claude-test")

    assert captured["timeout"] == 120


def test_call_openai_compatible_once_uses_120s_timeout(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["timeout"] = timeout
        return _FakeResponse({"choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    monkeypatch.setattr(stock_service.requests, "post", fake_post)

    stock_service._call_openai_compatible_once("prompt", "k", "openai-test", "https://api.openai.com/v1")

    assert captured["timeout"] == 120
