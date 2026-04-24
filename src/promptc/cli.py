from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from promptc import __version__
from promptc.models import FileRole
from promptc.scanner import scan
from promptc.tokens import TOKENIZER_DISCLAIMER


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="promptc")
@click.pass_context
def main(ctx: click.Context) -> None:
    """promptc - measure worst-case context exposure in your Claude / Cursor setup."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@main.command()
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path.cwd(),
    required=False,
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["terminal", "json"], case_sensitive=False),
    default="terminal",
    help="Output format.",
)
@click.option("--no-html", is_flag=True, help="Skip HTML report generation.")
@click.option("--open", "open_report", is_flag=True, help="Open the HTML report after analysis.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress.")
def analyze(
    path: Path,
    output_format: str,
    no_html: bool,
    open_report: bool,
    verbose: bool,
) -> None:
    """Analyze a .claude/ directory and report context debt.

    PATH defaults to the current working directory. If PATH contains a
    `.claude/` subdirectory, that subdirectory is scanned; otherwise PATH
    itself is scanned.
    """
    result = scan(path)

    if output_format.lower() == "json":
        _print_json(result)
        return

    console = Console()
    _print_terminal(console, result, verbose=verbose)

    # HTML / --open wiring lands in Week 2 (Day 8+).
    if not no_html and verbose:
        console.print("[dim](HTML report generation lands in Week 2.)[/dim]")
    if open_report and verbose:
        console.print("[dim](--open is a no-op until the HTML report ships.)[/dim]")


def _print_terminal(console: Console, result, *, verbose: bool) -> None:
    if not result.files:
        console.print(
            f"[yellow]No markdown files found under[/yellow] [bold]{result.root}[/bold]."
        )
        _print_warnings(console, result)
        return

    header = (
        f"[bold]Scanned:[/bold] {result.root}  "
        f"[dim]({result.total_files} files, {result.total_tokens:,} tokens)[/dim]"
    )
    console.print(header)
    console.print()

    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Role", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Frontmatter", justify="right")
    table.add_column("Body", justify="right")
    table.add_column("Description", justify="right")

    for f in result.files:
        desc_tokens = "-" if f.description_tokens is None else f"{f.description_tokens:,}"
        table.add_row(
            f.relative_path,
            f.role.value,
            f"{f.total_tokens:,}",
            f"{f.frontmatter_tokens:,}",
            f"{f.body_tokens:,}",
            desc_tokens,
        )

    console.print(table)
    console.print()

    _print_role_summary(console, result)
    _print_warnings(console, result)

    console.print()
    console.print(f"[dim]{TOKENIZER_DISCLAIMER}[/dim]")


def _print_role_summary(console: Console, result) -> None:
    roles: dict[FileRole, tuple[int, int]] = {}
    for f in result.files:
        count, tokens = roles.get(f.role, (0, 0))
        roles[f.role] = (count + 1, tokens + f.total_tokens)

    if not roles:
        return

    summary = Table(title="By role", show_header=True, header_style="bold", box=None)
    summary.add_column("Role", style="cyan")
    summary.add_column("Files", justify="right")
    summary.add_column("Tokens", justify="right")
    for role in FileRole:
        if role not in roles:
            continue
        count, tokens = roles[role]
        summary.add_row(role.value, f"{count:,}", f"{tokens:,}")
    console.print(summary)


def _print_warnings(console: Console, result) -> None:
    if not result.warnings:
        return
    console.print()
    console.print("[yellow]Warnings:[/yellow]")
    for warning in result.warnings:
        console.print(f"  [yellow]-[/yellow] {warning}")


def _print_json(result) -> None:
    payload = {
        "root": str(result.root),
        "total_files": result.total_files,
        "total_tokens": result.total_tokens,
        "tokenizer_disclaimer": TOKENIZER_DISCLAIMER,
        "files": [
            {
                "path": f.relative_path,
                "role": f.role.value,
                "total_tokens": f.total_tokens,
                "frontmatter_tokens": f.frontmatter_tokens,
                "body_tokens": f.body_tokens,
                "description_tokens": f.description_tokens,
                "frontmatter_valid": f.frontmatter_valid,
                "frontmatter_error": f.frontmatter_error,
                "name": f.name,
            }
            for f in result.files
        ],
        "warnings": result.warnings,
    }
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
