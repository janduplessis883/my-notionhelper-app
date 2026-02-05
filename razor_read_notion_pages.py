"""
CLI tool for reading Notion pages with a modern interface.
"""
from typing import Optional, Union, Dict, Any
import argparse
import re
import os
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich.syntax import Syntax
from notionhelper import NotionHelper  # type: ignore

# Initialize Rich console for beautiful output
console = Console()

# Authentication - prefer environment variable for security



def extract_page_id(input_string: str) -> str:
    """
    Extracts a 32-character Notion ID from a URL or returns the string
    if it's already a clean ID.
    
    Args:
        input_string: Either a Notion URL or a page ID
        
    Returns:
        The extracted 32-character page ID
        
    Examples:

    """
    # Regex looks for a sequence of 32 alphanumeric characters (hex)
    # This handles both URLs and clean IDs
    match = re.search(r'([a-f0-9]{32})', input_string.lower())
    if match:
        return match.group(1)
    return input_string


def format_page_id(page_id: str) -> str:
    """
    Format a page ID with hyphens for better readability.
    
    Args:
        page_id: 32-character page ID
        
    Returns:
        Formatted page ID with hyphens (8-4-4-4-12 format)
    """
    if len(page_id) == 32:
        return f"{page_id[:8]}-{page_id[8:12]}-{page_id[12:16]}-{page_id[16:20]}-{page_id[20:]}"
    return page_id


def read_page(raw_input: str, render_markdown: bool = True, show_raw: bool = False) -> None:
    """
    Read and display a Notion page.
    
    Args:
        raw_input: Page ID or URL
        render_markdown: Whether to render markdown in terminal
        show_raw: Whether to show raw markdown instead of rendered
    """
    page_id = extract_page_id(raw_input)
    formatted_id = format_page_id(page_id)
    
    # Display header
    console.print(
        Panel.fit(
            "[bold cyan]Notion Page Reader[/bold cyan]\n"
            f"[dim]Fetching Page: {formatted_id}[/dim]",
            border_style="cyan"
        )
    )
    console.print()
    
    try:
        nh = NotionHelper(NOTION_TOKEN)
        
        # Fetch page with progress indicator
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task(description="Fetching page content...", total=None)
            body = nh.get_page(page_id, return_markdown=True)
            progress.update(task, completed=True)
        
        # Success message
        console.print(
            Panel(
                "[bold green]✓[/bold green] Page retrieved successfully!",
                border_style="green",
                title="Success"
            )
        )
        console.print()
        
        # Display content - body can be str or dict
        body_str = str(body) if body else ""
        
        if body_str:
            console.print(
                Panel(
                    "[bold magenta]Page Content[/bold magenta]",
                    border_style="magenta"
                )
            )
            console.print()
            
            if show_raw:
                # Show raw markdown
                console.print("[dim]Raw Markdown:[/dim]")
                console.print(body_str)
            elif render_markdown and body_str.strip():
                # Render markdown beautifully in black color with no background
                try:
                    md = Markdown(body_str, code_theme="monokai", inline_code_theme="monokai")
                    # Create a new console with black style for markdown (no background)
                    from rich.theme import Theme
                    black_theme = Theme({
                        "markdown.text": "black",
                        "markdown.paragraph": "black",
                        "markdown.h1": "bold black",
                        "markdown.h2": "bold black",
                        "markdown.h3": "bold black",
                        "markdown.h4": "bold black",
                        "markdown.h5": "bold black",
                        "markdown.h6": "bold black",
                        "markdown.code": "black",
                        "markdown.code_block": "black",
                    })
                    black_console = Console(theme=black_theme)
                    black_console.print(md)
                except Exception:
                    # Fallback to plain text with black color
                    console.print(f"[black]{body_str}[/black]")
            else:
                console.print(f"[black]{body_str}[/black]")
        else:
            console.print(
                Panel(
                    "[yellow]⚠[/yellow] Page is empty or has no content",
                    border_style="yellow",
                    title="Warning"
                )
            )
            
    except Exception as e:
        console.print(
            Panel(
                f"[bold red]✗[/bold red] Error retrieving page:\n{str(e)}",
                border_style="red",
                title="Error"
            )
        )
        raise SystemExit(1)


def main() -> None:
    """Main CLI function with Rich formatting."""
    parser = argparse.ArgumentParser(
        description="📖 Read and display Notion pages with beautiful formatting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Using page ID
  python razor_read_notion_pages.py --page_
  
  # Using full URL
  python razor_read_notion_pages.py --page_id
  
  # Show raw markdown
  python razor_read_notion_pages.py --page_id <id> --raw
  
  # Interactive mode
  python razor_read_notion_pages.py
        """
    )
    
    parser.add_argument(
        '--page_id',
        type=str,
        required=False,
        help='The Notion page ID or the full Notion URL'
    )
    
    parser.add_argument(
        '--no-render',
        action='store_true',
        help='Display plain text instead of rendered markdown'
    )
    
    parser.add_argument(
        '--raw',
        action='store_true',
        help='Show raw markdown without rendering'
    )
    
    args = parser.parse_args()
    
    # Get page ID (interactive if not provided)
    page_input = args.page_id
    if not page_input:
        console.print(
            Panel.fit(
                "[bold cyan]Notion Page Reader[/bold cyan]\n"
                "[dim]Interactive Mode[/dim]",
                border_style="cyan"
            )
        )
        console.print()
        page_input = console.input("[cyan]Enter Notion page ID or URL:[/cyan] ")
    
    read_page(
        page_input,
        render_markdown=not args.no_render,
        show_raw=args.raw
    )


if __name__ == '__main__':
    main()
