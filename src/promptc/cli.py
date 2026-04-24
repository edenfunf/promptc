from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from promptc import __version__
from promptc.dedup import DedupResult, DuplicateGroup, find_duplicates
from promptc.models import FileRole, ScanResult
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
    scan_result = scan(path)
    dedup_result = find_duplicates(scan_result.files)

    if output_format.lower() == "json":
        _print_json(scan_result, dedup_result)
        return

    console = Console()
    _print_terminal(console, scan_result, dedup_result, verbose=verbose)

    if not no_html and verbose:
        console.print("[dim](HTML report generation lands in Week 2.)[/dim]")
    if open_report and verbose:
        console.print("[dim](--open is a no-op until the HTML report ships.)[/dim]")


def _print_terminal(
    console: Console,
    scan_result: ScanResult,
    dedup_result: DedupResult,
    *,
    verbose: bool,
) -> None:
    if not scan_result.files:
        console.print(
            f"[yellow]No markdown files found under[/yellow] [bold]{scan_result.root}[/bold]."
        )
        _print_warnings(console, scan_result)
        return

    total_tokens = scan_result.total_tokens
    wasted = dedup_result.total_wasted_tokens
    ratio = (wasted / total_tokens) if total_tokens else 0.0

    console.print(
        f"[bold]Scanned:[/bold] {scan_result.root}  "
        f"[dim]({scan_result.total_files} files, {total_tokens:,} tokens)[/dim]"
    )
    if dedup_result.total_groups:
        console.print(
            f"[bold]Duplicate chunks:[/bold] {dedup_result.total_groups} groups  "
            f"[red]{wasted:,} tokens wasted ({ratio:.1%})[/red]"
        )
    else:
        console.print("[bold]Duplicate chunks:[/bold] [green]none found[/green]")
    console.print()

    _print_file_table(console, scan_result, dedup_result)
    console.print()
    _print_role_summary(console, scan_result)

    if dedup_result.total_groups:
        console.print()
        _print_duplicate_groups(console, dedup_result, limit=5, verbose=verbose)

    _print_warnings(console, scan_result)

    console.print()
    console.print(f"[dim]{TOKENIZER_DISCLAIMER}[/dim]")


def _print_file_table(
    console: Console,
    scan_result: ScanResult,
    dedup_result: DedupResult,
) -> None:
    table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
    table.add_column("File", overflow="fold")
    table.add_column("Role", style="cyan")
    table.add_column("Total", justify="right")
    table.add_column("Body", justify="right")
    table.add_column("Desc", justify="right")
    table.add_column("Dup", justify="right")
    table.add_column("Dup%", justify="right")

    for f in scan_result.files:
        desc = "-" if f.description_tokens is None else f"{f.description_tokens:,}"
        dup_tokens = dedup_result.per_file_wasted.get(f.relative_path, 0)
        dup_ratio = (dup_tokens / f.body_tokens) if f.body_tokens else 0.0
        dup_cell = f"{dup_tokens:,}" if dup_tokens else "-"
        dup_pct_cell = f"{dup_ratio:.0%}" if dup_tokens else "-"
        if dup_ratio >= 0.4:
            dup_pct_cell = f"[red]{dup_pct_cell}[/red]"
        elif dup_ratio >= 0.15:
            dup_pct_cell = f"[yellow]{dup_pct_cell}[/yellow]"

        table.add_row(
            f.relative_path,
            f.role.value,
            f"{f.total_tokens:,}",
            f"{f.body_tokens:,}",
            desc,
            dup_cell,
            dup_pct_cell,
        )

    console.print(table)


def _print_role_summary(console: Console, scan_result: ScanResult) -> None:
    roles: dict[FileRole, tuple[int, int]] = {}
    for f in scan_result.files:
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


def _print_duplicate_groups(
    console: Console,
    dedup_result: DedupResult,
    *,
    limit: int,
    verbose: bool,
) -> None:
    console.print("[bold]Top duplicate groups:[/bold]")
    for idx, group in enumerate(dedup_result.groups[:limit], start=1):
        kind = "exact" if group.is_exact else "near"
        files = ", ".join(group.files_involved)
        console.print(
            f"  [bold]{idx}.[/bold] [red]{group.wasted_tokens:,}[/red] tokens wasted "
            f"({group.size} chunks, {kind}) in: {files}"
        )
        preview = _preview(group.canonical.raw, 100)
        console.print(f"      [dim]canonical:[/dim] {preview}")
        if verbose:
            for chunk in group.chunks:
                if chunk is group.canonical:
                    continue
                chunk_preview = _preview(chunk.raw, 100)
                console.print(
                    f"      [dim]dup:[/dim] [cyan]{chunk.file_path}[/cyan]"
                    f"#chunk{chunk.chunk_index}: {chunk_preview}"
                )
    remaining = dedup_result.total_groups - limit
    if remaining > 0:
        console.print(
            f"  [dim]... {remaining} more group(s) hidden. Use --verbose to expand.[/dim]"
        )


def _preview(text: str, max_chars: int) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _print_warnings(console: Console, scan_result: ScanResult) -> None:
    if not scan_result.warnings:
        return
    console.print()
    console.print("[yellow]Warnings:[/yellow]")
    for warning in scan_result.warnings:
        console.print(f"  [yellow]-[/yellow] {warning}")


def _group_to_dict(group: DuplicateGroup) -> dict:
    return {
        "size": group.size,
        "kind": "exact" if group.is_exact else "near",
        "wasted_tokens": group.wasted_tokens,
        "canonical": {
            "file": group.canonical.file_path,
            "chunk_index": group.canonical.chunk_index,
            "tokens": group.canonical.tokens,
            "preview": _preview(group.canonical.raw, 200),
        },
        "chunks": [
            {
                "file": c.file_path,
                "chunk_index": c.chunk_index,
                "tokens": c.tokens,
                "is_canonical": c is group.canonical,
            }
            for c in group.chunks
        ],
    }


def _print_json(scan_result: ScanResult, dedup_result: DedupResult) -> None:
    payload = {
        "root": str(scan_result.root),
        "total_files": scan_result.total_files,
        "total_tokens": scan_result.total_tokens,
        "tokenizer_disclaimer": TOKENIZER_DISCLAIMER,
        "duplicates": {
            "total_groups": dedup_result.total_groups,
            "total_wasted_tokens": dedup_result.total_wasted_tokens,
            "per_file_wasted": dedup_result.per_file_wasted,
            "groups": [_group_to_dict(g) for g in dedup_result.groups],
        },
        "files": [
            {
                "path": f.relative_path,
                "role": f.role.value,
                "total_tokens": f.total_tokens,
                "frontmatter_tokens": f.frontmatter_tokens,
                "body_tokens": f.body_tokens,
                "description_tokens": f.description_tokens,
                "duplicate_tokens": dedup_result.per_file_wasted.get(f.relative_path, 0),
                "frontmatter_valid": f.frontmatter_valid,
                "frontmatter_error": f.frontmatter_error,
                "name": f.name,
            }
            for f in scan_result.files
        ],
        "warnings": scan_result.warnings,
    }
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
