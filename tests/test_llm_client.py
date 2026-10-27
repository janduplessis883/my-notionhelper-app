from types import SimpleNamespace

import pytest

from llm_client import build_llm_config, complete_chat


class FakeCompletions:
    def __init__(self, content):
        self.content = content
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def fake_client(content):
    completions = FakeCompletions(content)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def test_builds_groq_config_with_selected_model():
    config = build_llm_config("Groq", "groq-secret", "openai/gpt-oss-120b")

    assert config.provider == "Groq"
    assert config.base_url == "https://api.groq.com/openai/v1"
    assert config.api_key == "groq-secret"
    assert config.model == "openai/gpt-oss-120b"


def test_builds_freellm_config_with_auto_model():
    config = build_llm_config("FreeLLM", "free-secret", "ignored-model")

    assert config.provider == "FreeLLM"
    assert config.base_url == "https://freellmapi-4ace.srv1395197.hstgr.cloud/v1"
    assert config.api_key == "free-secret"
    assert config.model == "auto"


def test_rejects_unknown_provider():
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        build_llm_config("Unknown", "secret", "model")


def test_complete_chat_sends_system_and_user_messages():
    config = build_llm_config("FreeLLM", "secret")
    client, completions = fake_client("  Answer text  ")

    result = complete_chat(config, "User prompt", "System prompt", client=client)

    assert result == "Answer text"
    assert completions.requests == [
        {
            "model": "auto",
            "messages": [
                {"role": "system", "content": "System prompt"},
                {"role": "user", "content": "User prompt"},
            ],
        }
    ]


def test_complete_chat_omits_absent_system_message():
    config = build_llm_config("Groq", "secret", "qwen/qwen3-32b")
    client, completions = fake_client("Answer")

    complete_chat(config, "Only user", client=client)

    assert completions.requests[0]["messages"] == [
        {"role": "user", "content": "Only user"}
    ]


@pytest.mark.parametrize("content", [None, "", "   "])
def test_complete_chat_rejects_empty_response(content):
    config = build_llm_config("FreeLLM", "secret")
    client, _ = fake_client(content)

    with pytest.raises(RuntimeError, match="empty response"):
        complete_chat(config, "Prompt", client=client)
