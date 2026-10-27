# Meeting Notes Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a FreeLLM-powered Meeting Notes page with optional explicit Notion append, and make Groq/FreeLLM selectable across the app's existing Groq-backed AI features.

**Architecture:** A shared OpenAI-compatible completion boundary will represent both providers with an immutable configuration object. Transcript conversion and meeting-note generation remain UI-independent and testable; a focused Streamlit page module owns upload, generation, preview, session-state, and download behavior. The existing selectbox router remains in place, with the chosen provider configuration injected into Tasks and Write to URL while Meeting Notes always receives a fixed FreeLLM configuration.

**Tech Stack:** Python, Streamlit, OpenAI Python client, pytest, LangChain packages supplied in `meeting_requirements.txt`

**Spec:** `docs/superpowers/specs/2026-10-27-meeting-notes-agent-design.md`

## Global Constraints

- FreeLLM base URL is exactly `https://freellmapi-4ace.srv1395197.hstgr.cloud/v1`.
- FreeLLM uses Streamlit secret `FREELLMAPI_API_KEY` and model `auto`.
- Groq uses Streamlit secret `GROQ_API_KEY`, its current model list, and its OpenAI-compatible endpoint.
- Meeting Notes always uses FreeLLM regardless of the global provider selection.
- `.vtt` conversion retains cue timestamps, voice/speaker labels, and all spoken content.
- Uploaded transcripts and generated Markdown stay in memory and are not persisted to disk; Notion append happens only after a separate explicit button click.
- The Notion Interview Database page's independent endpoint/model controls remain unchanged.
- Existing non-AI pages and workflows remain unchanged.

## Review Focus

- A FreeLLM or Groq response with no message text must raise a descriptive error rather than render `None`; pinned in Task 1 tests.
- A WebVTT cue with settings, a cue identifier, voice tags, and multiple content lines must retain timestamp, speaker, and every spoken word; pinned in Task 2 tests.
- Empty or non-UTF-8 uploads must produce a clear validation error without invoking the model; pinned in Task 2 tests.
- Model output wrapped in a fenced JSON block or surrounding prose must still parse, while malformed JSON must raise a useful error; pinned in Task 2 tests.
- Changing provider selection must route Tasks and Write to URL through the selected endpoint/model, while Meeting Notes remains on FreeLLM `auto`; pinned in Tasks 1 and 3 tests.
- An absent or invalid Notion URL must not affect generation or download, and explicit append must batch no more than 100 blocks per request; pinned in Task 3 tests.

---

### Task 1: Shared OpenAI-compatible provider client

**Files:**
- Create: `llm_client.py`
- Create: `tests/test_llm_client.py`

**Interfaces:**
- Consumes: API keys supplied by the Streamlit UI; no direct `st.secrets` dependency.
- Produces: `LLMConfig(provider: str, base_url: str, api_key: str, model: str)`, `build_llm_config(provider: str, api_key: str, model: str | None = None) -> LLMConfig`, and `complete_chat(config: LLMConfig, prompt: str, system_prompt: str | None = None, client: object | None = None) -> str`.

- [ ] **Step 1: Write failing provider-configuration tests**

Add tests named `test_builds_groq_config_with_selected_model`, `test_builds_freellm_config_with_auto_model`, and `test_rejects_unknown_provider`. Assert exact base URLs, models, provider labels, and error behavior using literal expected values.

- [ ] **Step 2: Run provider-configuration tests and verify RED**

Run: `pytest tests/test_llm_client.py -k "builds or rejects" -v`

Expected: FAIL because `llm_client` does not exist.

- [ ] **Step 3: Implement provider constants, `LLMConfig`, and `build_llm_config`**

Create `llm_client.py` with `GROQ`, `FREELLM`, `GROQ_BASE_URL`, `FREELLM_BASE_URL`, `GROQ_MODELS`, and the interfaces above. FreeLLM must ignore any supplied model and use `auto`; Groq must require the selected model.

- [ ] **Step 4: Run provider-configuration tests and verify GREEN**

Run: `pytest tests/test_llm_client.py -k "builds or rejects" -v`

Expected: PASS.

- [ ] **Step 5: Write failing completion tests**

Add `test_complete_chat_sends_system_and_user_messages`, `test_complete_chat_omits_absent_system_message`, and `test_complete_chat_rejects_empty_response`. Use a small fake client that implements the external completion boundary; assert the real function's returned text/error and the literal request payload captured by the fake.

- [ ] **Step 6: Run completion tests and verify RED**

Run: `pytest tests/test_llm_client.py -k "complete_chat" -v`

Expected: FAIL because `complete_chat` is missing.

- [ ] **Step 7: Implement `complete_chat`**

Use `OpenAI(api_key=config.api_key, base_url=config.base_url)` only when no client is injected. Call `client.chat.completions.create(model=config.model, messages=...)`, return stripped content, and raise `RuntimeError` for missing/blank content.

- [ ] **Step 8: Run Task 1 tests**

Run: `pytest tests/test_llm_client.py -v`

Expected: PASS.

- [ ] **Step 9: Commit Task 1**

```bash
git add llm_client.py tests/test_llm_client.py
git commit -m "feat: add selectable llm provider client"
```

### Task 2: Transcript conversion and adapted meeting-note agent

**Files:**
- Modify: `meeting_notes_agent.py`
- Create: `meeting_transcript.py`
- Create: `tests/test_meeting_transcript.py`
- Create: `tests/test_meeting_notes_agent.py`

**Interfaces:**
- Consumes: `LLMConfig` and `complete_chat` from Task 1.
- Produces: `decode_transcript_upload(filename: str, payload: bytes) -> str`, `convert_vtt_to_text(vtt_text: str) -> str`, `generate_meeting_notes(transcript: str, config: LLMConfig, completion_fn: Callable[..., str] = complete_chat) -> dict`, existing `parse_json_response(text: str) -> dict`, and existing `format_notes(notes: dict) -> str`.

- [ ] **Step 1: Write failing transcript decoding tests**

Add tests for unchanged UTF-8 `.txt`, case-insensitive extensions, unsupported extensions, empty payloads, and invalid UTF-8. Assert `ValueError` messages identify the failing condition.

- [ ] **Step 2: Run decoding tests and verify RED**

Run: `pytest tests/test_meeting_transcript.py -k "decode" -v`

Expected: FAIL because `meeting_transcript` does not exist.

- [ ] **Step 3: Implement `decode_transcript_upload`**

Decode UTF-8 bytes, reject empty/whitespace-only content, pass `.txt` through, dispatch `.vtt` to `convert_vtt_to_text`, and reject all other extensions.

- [ ] **Step 4: Run decoding tests and verify GREEN**

Run: `pytest tests/test_meeting_transcript.py -k "decode" -v`

Expected: PASS.

- [ ] **Step 5: Write failing WebVTT conversion tests**

Add `test_vtt_retains_timestamps_speakers_and_multiline_text`, `test_vtt_preserves_existing_speaker_prefix`, and `test_vtt_rejects_content_without_cues`. Use a fixture containing `WEBVTT`, cue metadata, a cue identifier, timestamp settings, `<v Sarah>` markup, HTML entities, and multiple text lines. Assert exact readable transcript lines such as `[00:00:01.000 --> 00:00:05.000] Sarah: Welcome everyone.`

- [ ] **Step 6: Run WebVTT tests and verify RED**

Run: `pytest tests/test_meeting_transcript.py -k "vtt" -v`

Expected: FAIL because `convert_vtt_to_text` is missing.

- [ ] **Step 7: Implement `convert_vtt_to_text`**

Parse cue blocks without a new dependency: ignore the `WEBVTT` header, notes, style/region blocks, and cue identifiers; normalize the timestamp to start/end values without cue settings; translate `<v Speaker>` into `Speaker:`; remove remaining VTT tags; HTML-unescape content; join multiline cue text without dropping words.

- [ ] **Step 8: Run transcript tests**

Run: `pytest tests/test_meeting_transcript.py -v`

Expected: PASS.

- [ ] **Step 9: Write failing meeting-agent tests**

Add tests that verify fenced/surrounded JSON parsing, malformed JSON errors, a meeting generation call using the supplied transcript/config/system prompt, and Markdown containing title, participants, summary, decisions, action items, blockers, discussion topics, next meeting, and follow-up questions. The completion fake returns a literal JSON response and tests the returned notes rather than the fake itself.

- [ ] **Step 10: Run meeting-agent tests and verify RED**

Run: `pytest tests/test_meeting_notes_agent.py -v`

Expected: FAIL because the agent still hard-codes a local model and its Markdown omits required sections.

- [ ] **Step 11: Refactor `meeting_notes_agent.py`**

Inject `LLMConfig` and a completion callable into `generate_meeting_notes`; remove hard-coded endpoint/key/model; keep the structured prompt; validate non-empty transcripts; expand `format_notes` to render all structured fields consistently. Keep the CLI functional by reading `FREELLMAPI_API_KEY`, building a FreeLLM config, and preserving its existing output-file behavior.

- [ ] **Step 12: Run Task 2 tests**

Run: `pytest tests/test_meeting_transcript.py tests/test_meeting_notes_agent.py -v`

Expected: PASS.

- [ ] **Step 13: Commit Task 2**

```bash
git add meeting_notes_agent.py meeting_transcript.py tests/test_meeting_transcript.py tests/test_meeting_notes_agent.py
git commit -m "feat: adapt meeting notes agent for uploaded transcripts"
```

### Task 3: Streamlit page and provider integration

**Files:**
- Create: `meeting_notes_page.py`
- Create: `tests/test_streamlit_integration.py`
- Modify: `streamlit_app.py:1-320`
- Modify: `razor_db_create_new_page.py:1-30,491-720`

**Interfaces:**
- Consumes: Task 1 provider APIs and Task 2 transcript/agent APIs.
- Produces: `render_meeting_notes_page(api_key: str, append_to_notion: Callable[[str, str], str]) -> None`; `append_meeting_notes_to_notion(notion_url: str, markdown: str, notion_helper: NotionHelper) -> str`; `render_notion_page_creator(llm_config: LLMConfig) -> None`; sidebar provider/model state passed to every currently Groq-backed flow.

- [ ] **Step 1: Write failing integration tests for provider routing**

Add tests that import the changed modules without constructing provider clients at import time, verify Tasks calls `complete_chat` with the selected `LLMConfig`, verify both Notion page generation branches accept and use the injected config, and verify Meeting Notes builds FreeLLM `auto` regardless of the global selection. Isolate only external Streamlit/network boundaries.

- [ ] **Step 2: Run provider-routing tests and verify RED**

Run: `pytest tests/test_streamlit_integration.py -k "provider or routing" -v`

Expected: FAIL because the app still constructs global Groq clients and the page APIs do not accept `LLMConfig`.

- [ ] **Step 3: Replace direct Groq use in `razor_db_create_new_page.py`**

Remove module-level Groq credentials/client and unused `query_llm`; change `render_notion_page_creator`, `_render_create_new_page_form`, and `_render_append_to_page_form` to accept `LLMConfig` and call `complete_chat` for generation.

- [ ] **Step 4: Add sidebar provider/model configuration in `streamlit_app.py`**

Add `Meeting Notes Agent` to `PAGE_SELECTION`. Add `AI provider` selection with Groq and FreeLLM. Show the current Groq model options only for Groq; display/use `auto` for FreeLLM. Build the chosen config from the corresponding secret without constructing a network client at import time.

- [ ] **Step 5: Route existing AI features through the selected config**

Replace `ask_groq` usage in Tasks with `complete_chat(selected_llm_config, prompt)` and pass the config to `render_notion_page_creator`. Preserve current Notion-save behavior and existing Groq model choices.

- [ ] **Step 6: Run provider-routing tests and verify GREEN**

Run: `pytest tests/test_streamlit_integration.py -k "provider or routing" -v`

Expected: PASS.

- [ ] **Step 7: Write failing Meeting Notes page-state tests**

Add tests for no-file validation, generation only after button submission, decode errors preventing model invocation, successful Markdown rendering, persistence in session state, download payload/filename, optional Notion URL validation, and a separate append action that cannot run before notes exist. Use Streamlit's app-testing support where feasible; otherwise extract only the smallest pure page-state helper needed to make these behaviors observable.

- [ ] **Step 8: Run Meeting Notes page tests and verify RED**

Run: `pytest tests/test_streamlit_integration.py -k "meeting_notes_page" -v`

Expected: FAIL because `meeting_notes_page.py` does not exist.

- [ ] **Step 9: Implement `render_meeting_notes_page`**

Use `st.file_uploader(type=["txt", "vtt"])`, a transcript preview, an explicit primary `Generate meeting notes` button, spinner/error handling, `st.session_state` for generated Markdown and safe download filename, `st.markdown` inside a bordered container, and `st.download_button(mime="text/markdown")`. After output exists, show an optional Notion page URL and a separate `Append to Notion page` button. Build an internal FreeLLM config with model `auto` from the supplied API key.

- [ ] **Step 10: Implement explicit Notion append**

Add `append_meeting_notes_to_notion`: normalize/extract the page ID with the existing Notion URL utilities, convert Markdown with `Blockizer`, reject empty or invalid content, and append blocks in batches of at most 100. Return the page ID for success feedback. Wire it to the page through an injected callback so generation and append remain independent and testable.

- [ ] **Step 11: Wire the Meeting Notes route**

In `streamlit_app.py`, call `render_meeting_notes_page` only for the new page, supplying `st.secrets.get("FREELLMAPI_API_KEY", "")` and a Notion append callback bound to the existing `NotionHelper`. Show a clear missing-secret error without attempting generation.

- [ ] **Step 12: Run Task 3 tests**

Run: `pytest tests/test_streamlit_integration.py -v`

Expected: PASS.

- [ ] **Step 13: Commit Task 3**

```bash
git add meeting_notes_page.py streamlit_app.py razor_db_create_new_page.py tests/test_streamlit_integration.py
git commit -m "feat: add meeting notes page and provider selection"
```

### Task 4: Dependency merge and full verification

**Files:**
- Modify: `requirements.txt`
- Reference only: `meeting_requirements.txt`

**Interfaces:**
- Consumes: all modules and tests from Tasks 1-3.
- Produces: a complete install manifest and verified Streamlit application.

- [ ] **Step 1: Merge meeting-agent dependencies**

Add the unique declarations from `meeting_requirements.txt` to `requirements.txt`: `langchain==0.3.0`, `langchain-core==0.3.0`, `langchain-openai==0.2.0`, and `python-dotenv==1.0.1`. Keep only one `openai` declaration and preserve existing app dependencies.

- [ ] **Step 2: Run the complete test suite**

Run: `pytest -v`

Expected: all tests PASS with no warnings introduced by changed code. Report any unrelated pre-existing failures by name.

- [ ] **Step 3: Compile changed Python files**

Run: `python -m py_compile llm_client.py meeting_transcript.py meeting_notes_agent.py meeting_notes_page.py streamlit_app.py razor_db_create_new_page.py`

Expected: exit code 0.

- [ ] **Step 4: Verify dependency consistency**

Run: `python -m pip check`

Expected: exit code 0, or report exact pre-existing environment conflicts without changing unrelated packages.

- [ ] **Step 5: Check for an already-running Streamlit app**

Run: `lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | rg -i 'python.*:85' || true`

Expected: report whether the app is already running; do not start it without user approval.

- [ ] **Step 6: Inspect the final diff and secret hygiene**

Run: `git diff --check && git diff --stat && rg -n "12345|FREELLMAPI_API_KEY|freellmapi-4ace" -g '*.py' -g '*.toml' .`

Expected: no whitespace errors, no hard-coded API key, and the FreeLLM key name appears only as a secret/environment lookup.

- [ ] **Step 7: Commit dependency and verification changes**

```bash
git add requirements.txt
git commit -m "build: add meeting agent dependencies"
```
