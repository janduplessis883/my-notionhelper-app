"""Shared configuration for OpenAI-compatible LLM providers."""

from dataclasses import dataclass


GROQ = "Groq"
FREELLM = "FreeLLM"

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
FREELLM_BASE_URL = "https://freellmapi-4ace.srv1395197.hstgr.cloud/v1"

GROQ_MODELS = [
    "moonshotai/kimi-k2-instruct-0905",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "groq/compound-mini",
    "groq/compound",
]


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    model: str


def build_llm_config(provider: str, api_key: str, model: str | None = None) -> LLMConfig:
    """Build a validated provider configuration."""
    if provider == FREELLM:
        return LLMConfig(FREELLM, FREELLM_BASE_URL, api_key, "auto")
    if provider == GROQ:
        if not model:
            raise ValueError("A model is required for Groq.")
        return LLMConfig(GROQ, GROQ_BASE_URL, api_key, model)
    raise ValueError(f"Unsupported AI provider: {provider}")


def complete_chat(
    config: LLMConfig,
    prompt: str,
    system_prompt: str | None = None,
    client: object | None = None,
) -> str:
    """Return text from an OpenAI-compatible chat completion."""
    if client is None:
        from openai import OpenAI

        client = OpenAI(api_key=config.api_key, base_url=config.base_url)

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    response = client.chat.completions.create(model=config.model, messages=messages)
    content = response.choices[0].message.content
    if not content or not content.strip():
        raise RuntimeError(f"{config.provider} returned an empty response.")
    return content.strip()
