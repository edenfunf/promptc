from __future__ import annotations

import webbrowser
from pathlib import Path

import click

from promptc import __version__
from promptc.dedup import find_duplicates
from promptc.exposure import analyze_exposure
from promptc.grade import compute_grade
from promptc.report import DEFAULT_REPORT_FILENAME, render_html, write_report
from promptc.scanner import scan
from promptc.views import make_console, print_json, print_terminal


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="promptc")
@click.pass_context
def main(ctx: click.Context) -> None:
    """promptc - measure worst-case skill-context exposure in your Claude Code setup."""
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
@click.option(
    "--output",
    "output_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Where to write the HTML report. Defaults to ./promptc-report.html.",
)
@click.option("--open", "open_report", is_flag=True, help="Open the HTML report after analysis.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress.")
@click.option(
    "--threshold",
    type=click.FloatRange(0.0, 1.0),
    default=0.85,
    show_default=True,
    help=(
        "Jaccard word-set similarity above which chunks are treated as "
        "duplicates. 1.0 = only verbatim matches, 0.0 = anything matches."
    ),
)
@click.option(
    "--min-words",
    type=click.IntRange(1, None),
    default=5,
    show_default=True,
    help=(
        "Skip paragraph chunks with fewer unique words after normalization. "
        "Higher = fewer false positives from short list items / headings."
    ),
)
@click.option(
    "--exclude",
    "excludes",
    metavar="PATTERN",
    multiple=True,
    help="Glob pattern (matched against relative path or basename) to skip. Repeatable.",
)
def analyze(
    path: Path,
    output_format: str,
    no_html: bool,
    output_path: Path | None,
    open_report: bool,
    verbose: bool,
    threshold: float,
    min_words: int,
    excludes: tuple[str, ...],
) -> None:
    """Analyze a .claude/ directory and report context debt.

    PATH defaults to the current working directory. If PATH contains a
    `.claude/` subdirectory, that subdirectory is scanned; otherwise PATH
    itself is scanned.
    """
    scan_result = scan(path, excludes=excludes)
    dedup_result = find_duplicates(
        scan_result.files, threshold=threshold, min_words=min_words
    )
    exposure_result = analyze_exposure(scan_result.files)
    total_tokens = scan_result.total_tokens
    bloat_ratio = (
        dedup_result.total_wasted_tokens / total_tokens if total_tokens else 0.0
    )
    grade = compute_grade(bloat_ratio)

    if output_format.lower() == "json":
        print_json(scan_result, dedup_result, exposure_result, grade)
        return

    console = make_console()
    print_terminal(
        console,
        scan_result,
        dedup_result,
        exposure_result,
        grade,
        verbose=verbose,
        html_will_be_written=not no_html,
    )

    if no_html:
        if open_report:
            console.print(
                "[yellow]--open has no effect when --no-html is set.[/yellow]"
            )
        if output_path is not None:
            console.print(
                "[yellow]--output has no effect when --no-html is set.[/yellow]"
            )
        return

    report_path = output_path if output_path is not None else Path.cwd() / DEFAULT_REPORT_FILENAME
    html = render_html(scan_result, dedup_result, exposure_result, grade)
    try:
        written = write_report(report_path, html)
    except OSError as exc:
        console.print(f"[red]Could not write HTML report:[/red] {exc}")
        return

    console.print()
    console.print(f"[bold]Full report:[/bold] [cyan]{written}[/cyan]")

    if open_report:
        webbrowser.open(written.as_uri())


if __name__ == "__main__":
    main()
