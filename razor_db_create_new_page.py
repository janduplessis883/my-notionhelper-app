"""
Streamlit-compatible module for creating Notion pages or appending content.
"""
import re
from typing import Optional
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


# Valid Notion block types
VALID_BLOCK_TYPES = {
    'paragraph', 'heading_1', 'heading_2', 'heading_3', 'heading_4',
    'bulleted_list_item', 'numbered_list_item', 'to_do', 'toggle',
    'code', 'quote', 'callout', 'divider', 'table_of_contents',
    'breadcrumb', 'equation', 'embed', 'bookmark', 'image', 'video',
    'pdf', 'file', 'audio', 'link_to_page', 'table', 'table_row',
    'column_list', 'column', 'synced_block', 'template', 'ai_block'
}


def filter_valid_blocks(blocks: list) -> list:
    """
    Filter out invalid or malformed blocks from the Blockizer output.

    Args:
        blocks: List of Notion block dictionaries

    Returns:
        Filtered list with only valid blocks
    """
    valid_blocks = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        # Check if block has at least one valid block type key
        has_valid_type = any(key in VALID_BLOCK_TYPES for key in block.keys())
        if has_valid_type:
            valid_blocks.append(block)
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
