"""Interactive documentation browser for zebra_day CLI."""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

man_app = typer.Typer(help="Interactive documentation browser")
console = Console()

# ---------------------------------------------------------------------------
# Topic registry
# ---------------------------------------------------------------------------

@dataclass
class TopicSource:
    """A documentation source: file path + optional heading to extract."""

    file_path: str  # relative to package or repo root
    heading: str | None = None  # None = whole file; str = heading text to match


@dataclass
class Topic:
    """A documentation topic with one or more content sources."""

    name: str
    description: str
    sources: list[TopicSource] = field(default_factory=list)
    subtopics: dict[str, "Topic"] = field(default_factory=dict)


# Map of topic slug -> Topic
TOPICS: dict[str, Topic] = {
    "overview": Topic(
        name="Overview",
        description="What zebra_day is and what it does",
        sources=[TopicSource("README.md", "zebra_day")],
    ),
    "quickstart": Topic(
        name="Quickstart",
        description="Get up and running in minutes",
        sources=[
            TopicSource("README.md", "For The Impatient"),
            TopicSource("README.md", "QUICKSTART"),
        ],
    ),
    "install": Topic(
        name="Installation & Setup",
        description="Requirements, pip install, source install, XDG paths",
        sources=[
            TopicSource("README.md", "Getting Started"),
        ],
    ),
    "cli": Topic(
        name="CLI Reference",
        description="All zday subcommands and options",
        sources=[TopicSource("README.md", "CLI Reference")],
    ),
    "gui": Topic(
        name="GUI Usage",
        description="Web UI pages, features, and navigation",
        sources=[TopicSource("zebra_day/docs/zebra_day_ui_guide.md")],
    ),
    "api": Topic(
        name="API Endpoints",
        description="HTTP print API and simplified Python API",
        sources=[
            TopicSource("README.md", "Simplified API"),
            TopicSource("README.md", "Print Request HTTP API"),
        ],
    ),
    "programmatic": Topic(
        name="Programmatic API",
        description="Using zebra_day as a Python library",
        sources=[TopicSource("zebra_day/docs/programatic_guide.md")],
    ),
    "dynamo": Topic(
        name="DynamoDB Shared Config",
        description="Multi-client shared configuration via AWS DynamoDB",
        sources=[TopicSource("AWS_DYNAMO_CONFIG_PLAN.md")],
    ),
    "https": Topic(
        name="HTTPS / TLS Setup",
        description="Local HTTPS with mkcert, certificate management",
        sources=[TopicSource("README.md", "Local HTTPS Setup")],
    ),
    "auth": Topic(
        name="Authentication (Cognito)",
        description="AWS Cognito authentication for the web UI",
        sources=[TopicSource("README.md", "Authentication")],
    ),
    "hardware": Topic(
        name="Hardware Configuration",
        description="Zebra printer models, network setup, calibration",
        sources=[TopicSource("zebra_day/docs/hardware_config_guide.md")],
    ),
    "troubleshooting": Topic(
        name="Troubleshooting",
        description="Common issues and fixes",
        sources=[TopicSource("README.md", "Troubleshooting")],
    ),
}

# Ordered list for menu display
TOPIC_ORDER: list[str] = [
    "overview",
    "quickstart",
    "install",
    "cli",
    "gui",
    "api",
    "programmatic",
    "dynamo",
    "https",
    "auth",
    "hardware",
    "troubleshooting",
]

# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

_doc_cache: dict[str, str] = {}


def _package_dir() -> Path:
    """Return the zebra_day package directory."""
    return Path(__file__).resolve().parent.parent


def _repo_root() -> Path:
    """Return the repository root (parent of package dir)."""
    return _package_dir().parent


def _find_doc_file(relative_path: str) -> Path | None:
    """Locate a doc file. Checks package dir first, then repo root."""
    # Direct relative to package dir
    candidate = _package_dir() / relative_path
    if candidate.is_file():
        return candidate
    # Relative to repo root
    candidate = _repo_root() / relative_path
    if candidate.is_file():
        return candidate
    return None


def _load_file(path: Path) -> str:
    """Load and cache a file's content."""
    key = str(path)
    if key not in _doc_cache:
        _doc_cache[key] = path.read_text(encoding="utf-8")
    return _doc_cache[key]


# ---------------------------------------------------------------------------
# Section extraction
# ---------------------------------------------------------------------------


def _extract_section(content: str, heading_text: str) -> str:
    """Extract a markdown section by heading text.

    Returns everything from the matched heading (inclusive) through the next
    heading of equal or higher level, or end-of-file.
    """
    lines = content.split("\n")
    start_idx: int | None = None
    start_level: int = 0

    for i, line in enumerate(lines):
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            if start_idx is None:
                # Look for the heading
                if heading_text.lower() in text.lower():
                    start_idx = i
                    start_level = level
            else:
                # We've started — stop at same or higher level heading
                if level <= start_level:
                    return "\n".join(lines[start_idx:i]).rstrip()

    if start_idx is not None:
        return "\n".join(lines[start_idx:]).rstrip()
    return ""


# ---------------------------------------------------------------------------
# Content assembly
# ---------------------------------------------------------------------------


def _get_topic_content(topic: Topic) -> str:
    """Assemble the full text content for a topic from its sources."""
    parts: list[str] = []
    for src in topic.sources:
        path = _find_doc_file(src.file_path)
        if path is None:
            parts.append(f"> *File not found: `{src.file_path}`*\n")
            continue
        raw = _load_file(path)
        if src.heading:
            section = _extract_section(raw, src.heading)
            if section:
                parts.append(section)
            else:
                parts.append(
                    f"> *Section '{src.heading}' not found in `{src.file_path}`*\n"
                )
        else:
            parts.append(raw)
    return "\n\n---\n\n".join(parts) if parts else "*No content available.*"


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def _is_interactive() -> bool:
    """Return True if stdin is a TTY (interactive session)."""
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _render_content(content: str) -> None:
    """Render markdown content to the console."""
    try:
        md = Markdown(content)
        console.print(md)
    except Exception:
        # Fallback: plain text
        console.print(content)


def _show_topic_menu() -> None:
    """Display the numbered topic menu."""
    table = Table(
        title="zebra_day Documentation",
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("#", style="bold", width=4, justify="right")
    table.add_column("Topic", style="cyan", min_width=25)
    table.add_column("Description")

    for idx, slug in enumerate(TOPIC_ORDER, 1):
        topic = TOPICS[slug]
        table.add_row(str(idx), topic.name, topic.description)

    console.print()
    console.print(table)
    console.print()
    console.print("[dim]Enter a number, topic name, or:[/dim]")
    console.print("[dim]  /term  — search docs    q — quit[/dim]")
    console.print()


def _show_topic(slug: str) -> None:
    """Display a single topic with a header panel."""
    topic = TOPICS.get(slug)
    if not topic:
        console.print(f"[red]Unknown topic:[/red] {slug}")
        return
    content = _get_topic_content(topic)
    console.print()
    console.print(
        Panel(
            f"[bold]{topic.name}[/bold]\n[dim]{topic.description}[/dim]",
            border_style="cyan",
        )
    )
    _render_content(content)
    console.print()


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _search_docs(term: str) -> None:
    """Search all doc sources for a term and display matching lines."""
    pattern = re.compile(re.escape(term), re.IGNORECASE)
    results: list[tuple[str, str, int, str]] = []  # (file, topic, line_no, line)

    seen_files: set[str] = set()
    for slug in TOPIC_ORDER:
        topic = TOPICS[slug]
        for src in topic.sources:
            file_key = src.file_path
            if file_key in seen_files:
                continue
            seen_files.add(file_key)
            path = _find_doc_file(file_key)
            if not path:
                continue
            content = _load_file(path)
            for line_no, line in enumerate(content.split("\n"), 1):
                if pattern.search(line):
                    results.append((file_key, topic.name, line_no, line.rstrip()))

    if not results:
        console.print(f"[yellow]No results for:[/yellow] {term}")
        return

    console.print(
        Panel(f"[bold]Search results for:[/bold] {term}  ({len(results)} matches)", border_style="cyan")
    )
    for file_path, topic_name, line_no, line in results[:50]:
        highlighted = pattern.sub(lambda m: f"[bold red]{m.group()}[/bold red]", line)
        console.print(
            f"  [dim]{file_path}:{line_no}[/dim] [cyan]({topic_name})[/cyan]"
        )
        console.print(f"    {highlighted}")
    if len(results) > 50:
        console.print(f"\n  [dim]...and {len(results) - 50} more matches[/dim]")


# ---------------------------------------------------------------------------
# Slug resolution (fuzzy matching)
# ---------------------------------------------------------------------------


def _resolve_slug(text: str) -> str | None:
    """Resolve user input to a topic slug.

    Accepts: exact slug, partial prefix, or a number (1-based index).
    """
    text = text.strip().lower()
    if not text:
        return None

    # Exact match
    if text in TOPICS:
        return text

    # Number
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(TOPIC_ORDER):
            return TOPIC_ORDER[idx]
        return None

    # Prefix match
    matches = [s for s in TOPIC_ORDER if s.startswith(text)]
    if len(matches) == 1:
        return matches[0]

    # Substring match on topic name
    for slug in TOPIC_ORDER:
        if text in TOPICS[slug].name.lower():
            return slug

    return None


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------


def _interactive_loop() -> None:
    """Run the interactive documentation browser."""
    _show_topic_menu()
    while True:
        try:
            raw = console.input("[bold cyan]man>[/bold cyan] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        if not raw:
            continue
        if raw.lower() in ("q", "quit", "exit"):
            break
        if raw.startswith("/"):
            term = raw[1:].strip()
            if term:
                _search_docs(term)
            continue
        if raw.lower() in ("m", "menu", "h", "help"):
            _show_topic_menu()
            continue
        if raw.lower() == "b":
            _show_topic_menu()
            continue

        slug = _resolve_slug(raw)
        if slug:
            _show_topic(slug)
            console.print("[dim]  b — back to menu    q — quit    /term — search[/dim]")
        else:
            console.print(f"[yellow]Unknown topic:[/yellow] {raw}")
            console.print("[dim]Enter a number, topic name, or 'menu' for the list[/dim]")


# ---------------------------------------------------------------------------
# Typer command
# ---------------------------------------------------------------------------


@man_app.callback(invoke_without_command=True)
def man_main(
    ctx: typer.Context,
    topic: str | None = typer.Argument(None, help="Topic to display (e.g. quickstart, cli, dynamo)"),
    search: str | None = typer.Option(None, "--search", "-s", help="Search all docs for a term"),
    list_topics: bool = typer.Option(False, "--list", "-l", help="List available topics"),
):
    """Interactive documentation browser for zebra_day.

    Run without arguments for an interactive menu, or specify a topic directly.

    \b
    Examples:
        zday man                    Interactive menu
        zday man quickstart         Show quickstart docs
        zday man cli                Show CLI reference
        zday man --search "HTTPS"   Search all docs
        zday man --list             List topics
    """
    if ctx.invoked_subcommand is not None:
        return

    # --list: just show topic table and exit
    if list_topics:
        _show_topic_menu()
        return

    # --search: search and exit
    if search:
        _search_docs(search)
        return

    # Direct topic
    if topic:
        # Support "dynamo bootstrap" style (two-word topics via remainder)
        slug = _resolve_slug(topic)
        if slug:
            _show_topic(slug)
        else:
            console.print(f"[red]Unknown topic:[/red] {topic}")
            console.print("[dim]Available topics:[/dim]")
            for s in TOPIC_ORDER:
                console.print(f"  [cyan]{s}[/cyan] — {TOPICS[s].description}")
            raise typer.Exit(1)
        return

    # No arguments: interactive if TTY, else show menu and exit
    if _is_interactive():
        _interactive_loop()
    else:
        _show_topic_menu()

