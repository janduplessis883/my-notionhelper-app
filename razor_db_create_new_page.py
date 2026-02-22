"""
Streamlit-compatible module for creating Notion pages or appending content.
"""
import re
from typing import Optional, Any
import streamlit as st
from notionhelper import NotionHelper
from notion_blockify import Blockizer
from groq import Groq
# Authentication from Streamlit secrets
notion_token = st.secrets["NOTION_TOKEN"]
razor_db_id = st.secrets["RAZOR_DB_ID"]
groq_api_key = st.secrets["GROQ_API_KEY"]

# Initialize NotionHelper
nh = NotionHelper(notion_token)
client = Groq(api_key=st.secrets["GROQ_API_KEY"])

# Simple function to get a response from Groq
def ask_groq(prompt: str, model: str = "openai/gpt-oss-120b"):
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        model=model,
    )
    try:
        return chat_completion.choices[0].message.content
    except Exception as e:
        st.error(f"Error getting response from Groq: {e}")
        return "Error: Could not get a response from Groq."

def extract_page_id_from_url(notion_url: str) -> Optional[str]:
    """
    Extract the Notion page ID from a Notion URL.

    Args:
        notion_url: A Notion page URL

    Returns:
        The extracted page ID or None if not found
    """
    # Notion URLs can be in formats like:
    # https://www.notion.so/Page-Title-abc123def456...
    # https://www.notion.so/workspace/abc123def456...
    # https://notion.so/abc123def456...
    
    # Extract the 32-character hex ID (with or without hyphens)
    # Notion IDs are 32 hex characters, sometimes formatted as UUID with hyphens
    
    # Pattern for UUID format with hyphens
    uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
    
    # Pattern for 32 hex characters without hyphens (at end of URL)
    hex_pattern = r'[a-f0-9]{32}'
    
    # Try UUID pattern first
    match = re.search(uuid_pattern, notion_url, re.IGNORECASE)
    if match:
        return match.group()
    
    # Try hex pattern (usually at the end of URL after last hyphen)
    match = re.search(hex_pattern, notion_url, re.IGNORECASE)
    if match:
        # Convert to UUID format
        hex_id = match.group()
        return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"
    
    return None


VALID_BLOCK_TYPES = {
    'paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item',
    'numbered_list_item', 'to_do', 'toggle', 'code', 'quote', 'callout',
    'divider', 'table_of_contents', 'breadcrumb', 'equation', 'embed',
    'bookmark', 'image', 'video', 'pdf', 'file', 'audio', 'link_to_page',
    'table', 'table_row', 'column_list', 'column', 'synced_block', 'template'
}


TEXT_BLOCK_TYPES = {
    'paragraph', 'heading_1', 'heading_2', 'heading_3', 'bulleted_list_item',
    'numbered_list_item', 'quote', 'callout', 'toggle'
}

MAX_RICH_TEXT_CONTENT_LENGTH = 2000


def _utf16_units(value: str) -> int:
    """Return UTF-16 code units count (how Notion validates text length)."""
    return len(value.encode("utf-16-le")) // 2


def _chunk_text(value: str, chunk_size: int = MAX_RICH_TEXT_CONTENT_LENGTH) -> list[str]:
    """Split text into Notion-safe rich_text chunks by UTF-16 code units."""
    if not value:
        return [""]

    chunks: list[str] = []
    current_chars: list[str] = []
    current_units = 0

    for ch in value:
        ch_units = _utf16_units(ch)
        if current_chars and current_units + ch_units > chunk_size:
            chunks.append("".join(current_chars))
            current_chars = [ch]
            current_units = ch_units
        else:
            current_chars.append(ch)
            current_units += ch_units

    if current_chars:
        chunks.append("".join(current_chars))

    return chunks


def _normalize_rich_text(items: Any) -> list[dict]:
    """Normalize rich_text items to Notion's request schema."""
    if not isinstance(items, list):
        return []

    normalized = []
    for item in items:
        if not isinstance(item, dict):
            continue

        text = item.get("text")
        if not isinstance(text, dict):
            text = {}

        content = text.get("content")
        if content is None:
            content = item.get("plain_text")
        if content is None:
            continue

        content_str = str(content)
        link_url = None
        link = text.get("link")
        if isinstance(link, dict):
            link_url = link.get("url")
        if not link_url:
            link_url = item.get("href")

        annotations = item.get("annotations")
        clean_annotations = None
        if isinstance(annotations, dict):
            clean_annotations = {
                "bold": bool(annotations.get("bold", False)),
                "italic": bool(annotations.get("italic", False)),
                "strikethrough": bool(annotations.get("strikethrough", False)),
                "underline": bool(annotations.get("underline", False)),
                "code": bool(annotations.get("code", False)),
                "color": str(annotations.get("color", "default")),
            }

        for chunk in _chunk_text(content_str):
            clean_text = {"content": chunk}
            if link_url:
                clean_text["link"] = {"url": link_url}

            clean_item = {
                "type": "text",
                "text": clean_text,
            }
            if clean_annotations:
                clean_item["annotations"] = clean_annotations

            normalized.append(clean_item)

    return normalized


def _sanitize_notion_block(block: dict) -> Optional[dict]:
    """Convert a block to a Notion-compatible request payload."""
    if not isinstance(block, dict):
        return None

    block_type = block.get("type")
    if not isinstance(block_type, str):
        return None
    original_block_type = block_type

    # Notion only supports heading_1..heading_3.
    if block_type.startswith("heading_"):
        try:
            level = int(block_type.split("_", maxsplit=1)[1])
            if level > 3:
                block_type = "heading_3"
        except (ValueError, IndexError):
            return None

    if block_type not in VALID_BLOCK_TYPES:
        return None

    payload = block.get(original_block_type)
    if not isinstance(payload, dict):
        payload = {}

    clean_payload: dict[str, Any] = {}

    if block_type in TEXT_BLOCK_TYPES:
        clean_payload["rich_text"] = _normalize_rich_text(payload.get("rich_text", []))

    if block_type == "to_do":
        clean_payload["rich_text"] = _normalize_rich_text(payload.get("rich_text", []))
        clean_payload["checked"] = bool(payload.get("checked", False))

    if block_type == "code":
        clean_payload["language"] = str(payload.get("language", "plain text"))
        clean_payload["rich_text"] = _normalize_rich_text(payload.get("rich_text", []))

    if block_type == "equation":
        expression = payload.get("expression")
        if expression is None:
            return None
        clean_payload["expression"] = str(expression)

    if block_type in {"embed", "bookmark", "video", "pdf", "audio"}:
        url = payload.get("url")
        if not url:
            return None
        clean_payload["url"] = str(url)

    if block_type == "image":
        image_external = payload.get("external")
        if isinstance(image_external, dict) and image_external.get("url"):
            clean_payload["external"] = {"url": str(image_external["url"])}
        elif payload.get("url"):
            clean_payload["external"] = {"url": str(payload["url"])}
        else:
            return None

    if block_type == "table":
        clean_payload["table_width"] = int(payload.get("table_width", 1))
        clean_payload["has_column_header"] = bool(payload.get("has_column_header", False))
        clean_payload["has_row_header"] = bool(payload.get("has_row_header", False))
        children = payload.get("children", [])
        clean_children = filter_valid_blocks(children)
        if clean_children:
            clean_payload["children"] = clean_children

    if block_type == "table_row":
        cells = payload.get("cells")
        if not isinstance(cells, list):
            return None
        clean_cells = []
        for cell in cells:
            clean_cells.append(_normalize_rich_text(cell))
        clean_payload["cells"] = clean_cells

    children = payload.get("children")
    if isinstance(children, list) and block_type not in {"table", "table_row"}:
        clean_children = filter_valid_blocks(children)
        if clean_children:
            clean_payload["children"] = clean_children

    # Block types with empty payload are valid if explicitly allowed by Notion.
    if block_type in {"divider", "table_of_contents", "breadcrumb"} and not clean_payload:
        clean_payload = {}

    if block_type not in {"divider", "table_of_contents", "breadcrumb"} and not clean_payload:
        return None

    return {
        "object": "block",
        "type": block_type,
        block_type: clean_payload,
    }


def filter_valid_blocks(blocks: list) -> list:
    """
    Normalize and filter malformed blocks from the Blockizer output.

    Args:
        blocks: List of Notion block dictionaries

    Returns:
        List of sanitized block dictionaries accepted by Notion
    """
    valid_blocks = []
    for block in blocks:
        clean_block = _sanitize_notion_block(block)
        if clean_block:
            valid_blocks.append(clean_block)
    return valid_blocks


def batch_blocks(blocks: list, batch_size: int = 100) -> list[list]:
    """
    Split blocks into batches to comply with Notion API limits.

    Args:
        blocks: List of Notion block dictionaries
        batch_size: Maximum number of blocks per batch (Notion limit is 100)

    Returns:
        List of batches, where each batch is a list of blocks
    """
    return [blocks[i:i + batch_size] for i in range(0, len(blocks), batch_size)]


def append_blocks_in_batches(page_id: str, blocks: list) -> dict:
    """
    Append blocks to a Notion page in batches to handle API limits.

    Args:
        page_id: The Notion page ID
        blocks: List of Notion block dictionaries

    Returns:
        API response from the last batch
    """
    batches = batch_blocks(blocks, batch_size=100)
    result = None
    
    for batch in batches:
        result = nh.append_page_body(page_id, blocks=batch)
    
    return result


def create_new_page(
    title: str,
    desc: str,
    category: str,
    url: str,
    markdown_body: Optional[str] = None,
    database_id: str = ""
) -> dict:
    """
    Create a new Notion page with the specified properties.

    Args:
        title: Title of the page
        desc: Description content
        category: Category select option
        url: URL to be stored
        markdown_body: Optional markdown content for page body
        database_id: The ID of the Notion database (defaults to RAZOR_DB_ID)

    Returns:
        API response dictionary
    """
    if not database_id:
        database_id = razor_db_id
    
    properties = {
        'Title': {'title': [{'text': {'content': title}}]},
        'Description': {'rich_text': [{'text': {'content': desc}}]},
        'Category': {'select': {'name': category}},
        'URL': {'url': url if url else None}
    }
    
    result = nh.new_page_to_data_source(database_id, page_properties=properties)
    
    if markdown_body:
        blocks = Blockizer().convert(markdown_body)
        # Filter out any invalid/malformed blocks
        blocks = filter_valid_blocks(blocks)
        if blocks:
            # Use batching to handle large content (Notion limit is 100 blocks)
            output = append_blocks_in_batches(result['id'], blocks)
        else:
            output = result
    else:
        output = result
    
    return output


def append_to_existing_page(page_id: str, markdown_body: str) -> dict:
    """
    Append markdown content to an existing Notion page.

    Args:
        page_id: The Notion page ID
        markdown_body: Markdown content to append

    Returns:
        API response dictionary
    """
    blocks = Blockizer().convert(markdown_body)
    # Filter out any invalid/malformed blocks
    blocks = filter_valid_blocks(blocks)
    if not blocks:
        raise ValueError("No valid blocks generated from markdown content")
    # Use batching to handle large content (Notion limit is 100 blocks)
    return append_blocks_in_batches(page_id, blocks)


def query_llm(prompt: str, system_prompt: Optional[str] = None) -> str:
    """
    Query an LLM (Groq) to generate markdown content.

    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt

    Returns:
        Generated markdown content
    """
    import requests
    import json
    
    if system_prompt is None:
        system_prompt = "You are a helpful assistant. Generate well-formatted markdown content based on the user's request."
    
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {groq_api_key}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4096
    }
    
    response = requests.post(url, headers=headers, json=data)
    response.raise_for_status()
    
    result = response.json()
    return result["choices"][0]["message"]["content"]


def render_notion_page_creator(model: str = "openai/gpt-oss-120b") -> None:
    """
    Render the Streamlit UI for creating/appending Notion pages.

    Args:
        model: The LLM model to use for content generation
    """
    st.subheader(":material/note_add: Notion Page Creator")
    
    # Mode selection
    mode = st.radio(
        "Select mode:",
        options=["Create New Page", "Append to Existing Page"],
        horizontal=True,
        key="notion_page_mode"
    )
    
    st.divider()
    
    if mode == "Create New Page":
        _render_create_new_page_form(model=model)
    else:
        _render_append_to_page_form(model=model)


def _render_create_new_page_form(model: str = "openai/gpt-oss-120b") -> None:
    """Render the form for creating a new page."""
    col1, col2 = st.columns(2)
    
    with col1:
        title = st.text_input(
            "Title",
            placeholder="Enter page title",
            key="new_page_title"
        )
        category = st.text_input(
            "Category",
            placeholder="Enter category",
            key="new_page_category"
        )
    
    with col2:
        desc = st.text_input(
            "Description",
            placeholder="Enter description",
            key="new_page_desc"
        )
        url = st.text_input(
            "URL",
            placeholder="https://example.com",
            key="new_page_url"
        )
    
    st.divider()
    
    # Content source toggle
    use_llm = st.toggle(
        "Generate content with LLM",
        value=False,
        key="use_llm_toggle"
    )
    
    markdown_body = ""
    
    if use_llm:
        llm_prompt = st.text_area(
            "LLM Prompt",
            placeholder="Describe what content you want the LLM to generate...",
            height=100,
            key="llm_prompt_input"
        )
        
        if st.button("Generate Content", key="generate_llm_content", icon=":material/robot_2:"):
            if llm_prompt:
                with st.spinner("Generating content with LLM...", show_time=True):
                    try:
                        markdown_body = ask_groq(llm_prompt, model=model)
                        st.session_state["generated_markdown"] = markdown_body
                        st.success(":material/check_circle: Content generated!")
                    except Exception as e:
                        st.error(f":material/error: Failed to generate content: {e}")
        
        # Show generated content if available
        if "generated_markdown" in st.session_state:
            st.text_area(
                "Generated Markdown (editable)",
                value=st.session_state["generated_markdown"],
                height=200,
                key="generated_markdown_display"
            )
            markdown_body = st.session_state.get("generated_markdown_display", st.session_state["generated_markdown"])
    else:
        markdown_body = st.text_area(
            "Markdown Body",
            placeholder="Paste or type your markdown content here...",
            height=200,
            key="paste_markdown_input"
        )
    
    st.divider()
    
    # Submit button
    if st.button("Create Page", key="create_page_btn", icon=":material/add:", type="primary"):
        if not title:
            st.error(":material/error: Title is required")
            return
        
        with st.spinner("Creating Notion page...", show_time=True):
            try:
                result = create_new_page(
                    title=title,
                    desc=desc or "",
                    category=category or "General",
                    url=url,
                    markdown_body=markdown_body if markdown_body else None
                )
                # Clear the generated markdown from session state
                if "generated_markdown" in st.session_state:
                    del st.session_state["generated_markdown"]
                st.success(f":material/check_circle: Page created successfully!  \n\nPage ID: `{result.get('id', 'N/A')}`")
                st.rerun()
            except Exception as e:
                st.error(f":material/error: Failed to create page: {e}")


def _render_append_to_page_form(model: str = "openai/gpt-oss-120b") -> None:
    """Render the form for appending to an existing page."""
    notion_url = st.text_input(
        "Notion Page URL",
        placeholder="Paste the Notion page URL here...",
        key="append_notion_url"
    )
    
    # Extract and display page ID
    page_id = None
    if notion_url:
        page_id = extract_page_id_from_url(notion_url)
        if page_id:
            st.info(f":material/info: Extracted Page ID: `{page_id}`")
        else:
            st.warning(":material/warning: Could not extract page ID from URL")
    
    st.divider()
    
    # Content source toggle
    use_llm = st.toggle(
        "Generate content with LLM",
        value=False,
        key="append_use_llm_toggle"
    )
    
    markdown_body = ""
    
    if use_llm:
        llm_prompt = st.text_area(
            "LLM Prompt",
            placeholder="Describe what content you want the LLM to generate...",
            height=100,
            key="append_llm_prompt_input"
        )
        
        if st.button("Generate Content", key="append_generate_llm_content", icon=":material/robot_2:"):
            if llm_prompt:
                with st.spinner("Generating content with LLM...", show_time=True):
                    try:
                        markdown_body = ask_groq(llm_prompt, model=model)
                        st.session_state["append_generated_markdown"] = markdown_body
                        st.success(":material/check_circle: Content generated!")
                    except Exception as e:
                        st.error(f":material/error: Failed to generate content: {e}")
        
        # Show generated content if available
        if "append_generated_markdown" in st.session_state:
            st.text_area(
                "Generated Markdown (editable)",
                value=st.session_state["append_generated_markdown"],
                height=200,
                key="append_generated_markdown_display"
            )
            markdown_body = st.session_state.get("append_generated_markdown_display", st.session_state["append_generated_markdown"])
    else:
        markdown_body = st.text_area(
            "Markdown Body",
            placeholder="Paste or type your markdown content here...",
            height=200,
            key="append_paste_markdown_input"
        )
    
    st.divider()
    
    # Submit button
    if st.button("Append to Page", key="append_page_btn", icon=":material/add:", type="primary"):
        if not page_id:
            st.error(":material/error: Valid Notion URL is required")
            return
        
        if not markdown_body:
            st.error(":material/error: Markdown content is required")
            return
        
        with st.spinner("Appending content to Notion page...", show_time=True):
            try:
                result = append_to_existing_page(page_id, markdown_body)
                # Clear the generated markdown from session state
                if "append_generated_markdown" in st.session_state:
                    del st.session_state["append_generated_markdown"]
                st.success(f":material/check_circle: Content appended successfully!  \n\nPage ID: `{page_id}`")
                st.rerun()
            except Exception as e:
                st.error(f":material/error: Failed to append content: {e}")
