# Meeting Notes Agent and selectable LLM providers

## Intent

Add the supplied Meeting Notes Agent to the Streamlit application and let users choose Groq or FreeLLM for the app's existing Groq-backed features. Meeting-note generation must always use FreeLLM. The result should turn uploaded meeting transcripts into readable, downloadable Markdown without losing timestamps or speaker information from WebVTT files.

## Goals

- Add `Meeting Notes Agent` to the existing sidebar page selector.
- Accept `.txt` and `.vtt` uploads and process them only after the user clicks a generation button.
- Convert WebVTT input to plain text while retaining cue timestamps, voice/speaker labels, and spoken content.
- Run the supplied meeting-note prompt and formatting flow against `https://freellmapi-4ace.srv1395197.hstgr.cloud/v1`, using model `auto` and the `FREELLMAPI_API_KEY` Streamlit secret.
- Render generated notes with `st.markdown` and provide an in-memory `.md` download.
- Allow the user to optionally provide a Notion page URL and append generated Markdown to that page with a separate post-generation button.
- Add a global Groq/FreeLLM provider selector for the current Groq-backed Tasks and Write to URL flows. Groq keeps its existing model list; FreeLLM uses `auto`.
- Merge the unique packages from `meeting_requirements.txt` into `requirements.txt` without duplicating packages already present.
- Add automated tests for provider routing, response extraction, VTT conversion, JSON parsing, and Markdown formatting.

## Non-goals

- Do not automatically send meeting notes to Notion or persist uploads/results on the server.
- Do not change the Notion Interview Database page's independent custom endpoint/model controls; this request only replaces places currently coupled to Groq.
- Do not expose the FreeLLM API key or let users edit the fixed Meeting Notes endpoint/model.
- Do not add audio/video transcription.

## Constraints and failure behavior

- Credentials come only from `st.secrets`; the app must show a useful error if the selected provider's key is missing.
- Uploaded content stays in memory. UTF-8 is preferred, with a clear error for undecodable input.
- Empty files, unsupported extensions, malformed model JSON, network errors, and empty model responses must be surfaced in the UI without crashing the app.
- A missing or invalid optional Notion URL must block only the append action, not meeting-note generation or download.
- Existing Notion, PDF, weather, and script-runner behavior must remain unchanged.
- The generated Markdown is retained in session state so it survives Streamlit reruns long enough to preview and download.

## Approaches considered

1. **Central OpenAI-compatible client — selected.** Introduce one provider configuration and chat-completion boundary used by both Groq and FreeLLM. This removes duplicated Groq calls, centralizes error handling, and makes the sidebar selection reusable.
2. **Separate provider implementations.** Keep the Groq SDK paths and add FreeLLM branches in each caller. This has a smaller first diff but duplicates request logic and makes later provider changes harder.

The selected design will use the installed OpenAI client against both OpenAI-compatible endpoints. Groq remains a selectable provider, but existing direct Groq client construction is removed from the affected flows.

## Design

### Shared LLM boundary

A small module will define provider names, base URLs, default models, Groq model options, and a chat-completion function accepting provider, API key, model, user prompt, and optional system prompt. It will return response text or raise a descriptive exception. Streamlit-specific secret lookup and error display remain in the UI layer.

The sidebar will show:

- `AI provider`: `Groq` or `FreeLLM`.
- `Model`: the current Groq model list when Groq is selected; `auto` when FreeLLM is selected.

The selection will be passed into Tasks and Write to URL. The Meeting Notes page bypasses the global choice and always constructs the FreeLLM configuration.

### Meeting transcript conversion

Plain-text uploads are decoded and passed through unchanged. WebVTT conversion will remove the `WEBVTT` header, cue identifiers, metadata/settings, and markup that are not part of the transcript, while emitting each cue in readable text form such as:

```text
[00:00:01.000 --> 00:00:05.000] Sarah: Welcome everyone.
```

WebVTT voice tags such as `<v Sarah>Welcome everyone</v>` will become `Sarah: Welcome everyone`. Existing speaker text such as `Sarah: ...` remains intact. Multi-line cue content is joined without dropping words. This preserves the information required by the agent while producing a `.txt`-style transcript in memory.

### Meeting Notes page

The page will contain a file uploader restricted to `.txt` and `.vtt`, an optional transcript preview, and a `Generate meeting notes` button. On click it will validate and convert the upload, call the adapted agent with the fixed FreeLLM configuration, parse its structured JSON, format it using the supplied Markdown formatter, and store the result in session state.

The output will be rendered as Markdown inside a bordered container or expander, followed by a `Download Markdown` button whose payload is the generated string and whose filename is derived safely from the inferred meeting title (falling back to `meeting_notes.md`).

After generation, the page will also show an optional Notion page URL field and a separate `Append to Notion page` button. The button will normalize/extract the page ID, convert the generated Markdown to Notion blocks, append in batches of no more than 100 blocks, and report success or a useful error. Generation never triggers this action automatically, preventing accidental duplicate content when notes are regenerated.

### Supplied agent and dependencies

`meeting_notes_agent.py` will be refactored so endpoint, API key, and model are injected rather than hard-coded. Its JSON parser and Markdown formatter remain reusable and testable. The CLI may remain functional using environment variables, but the Streamlit path will not write an output file.

`requirements.txt` will incorporate `langchain`, `langchain-core`, `langchain-openai`, and `python-dotenv` from `meeting_requirements.txt`, resolving duplicates with the app's existing `openai` dependency. Versions will be kept compatible with the supplied agent's declared set.

## Verification

- Unit tests first for representative `.txt` and `.vtt` inputs, including voice tags, cue identifiers, multiline cues, and malformed/empty input.
- Unit tests for Groq versus FreeLLM endpoint/model routing and meeting-agent JSON/Markdown behavior, with only the external network boundary replaced.
- Unit tests for optional Notion URL validation and explicit append behavior, including block batching.
- Run the focused tests, then the complete test suite.
- Compile/import-check changed Python files and verify the Streamlit app can start without an immediate exception using configured secrets.

## Builder decisions

- Keep the current selectbox-based navigation rather than migrating the whole app to `st.navigation`, limiting risk to this feature.
- Use in-memory conversion/download rather than temporary files.
- Treat only existing Groq-backed functionality as part of the global provider migration.
