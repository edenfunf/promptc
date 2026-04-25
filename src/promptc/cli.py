from __future__ import annotations

import json
import sys
import webbrowser
from pathlib import Path

import click
from rich.align import Align
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from promptc import __version__
from promptc.dedup import DedupResult, DuplicateGroup, find_duplicates
from promptc.exposure import EXPOSURE_NARRATIVE, ExposureReport, analyze_exposure
from promptc.grade import Grade, compute_grade
from promptc.models import FileRole, ScanResult
from promptc.report import DEFAULT_REPORT_FILENAME, render_html, write_report
from promptc.scanner import scan
from promptc.tokens import TOKENIZER_DISCLAIMER


def _make_console() -> Console:
    """Return a Console that won't crash on emoji / CJK in legacy Windows consoles.

    Rich's default Windows renderer calls the Win32 Console API directly,
    which respects the active code page (cp950 / cp1252 etc.) and raises
    UnicodeEncodeError on non-representable characters that appear in
    user-scanned files. Reconfigure stdout in place so unrepresentable
    glyphs are written as '?' instead of crashing; legacy_windows=False
    forces rich to emit ANSI instead of calling the Win32 API.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    return Console(legacy_windows=False)


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
@click.option("--open", "open_report", is_flag=True, help="Open the HTML report after analysis.")
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress.")
@click.option(
    "--threshold",
    type=click.FloatRange(0.0, 1.0),
    default=0.85,
    show_default=True,
    help="Jaccard similarity at or above which chunks are treated as duplicates.",
)
@click.option(
    "--min-words",
    type=click.IntRange(1, None),
    default=5,
    show_default=True,
    help="Skip paragraph chunks with fewer unique words after normalization.",
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
        _print_json(scan_result, dedup_result, exposure_result, grade)
        return

    console = _make_console()
    _print_terminal(
        console,
        scan_result,
        dedup_result,
        exposure_result,
        grade,
        verbose=verbose,
    )

    if no_html:
        if open_report:
            console.print(
                "[yellow]--open has no effect when --no-html is set.[/yellow]"
            )
        return

    report_path = Path.cwd() / DEFAULT_REPORT_FILENAME
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


def _print_terminal(
    console: Console,
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
    *,
    verbose: bool,
) -> None:
    if not scan_result.files:
        _print_cursor_sibling_warning(console, scan_result)
        console.print(
            f"[yellow]No markdown files found under[/yellow] [bold]{scan_result.root}[/bold]."
        )
        _print_warnings(console, scan_result)
        return

    total_tokens = scan_result.total_tokens
    wasted = dedup_result.total_wasted_tokens

    _print_cursor_sibling_warning(console, scan_result)
    _print_hero(
        console,
        scan_result=scan_result,
        dedup_result=dedup_result,
        exposure_result=exposure_result,
        grade=grade,
    )
    console.print()

    console.print(
        f"[bold]Scanned:[/bold] {scan_result.root}  "
        f"[dim]({scan_result.total_files} files, {total_tokens:,} tokens)[/dim]"
    )
    console.print()

    _print_file_table(console, scan_result, dedup_result)
    console.print()
    _print_role_summary(console, scan_result)

    if dedup_result.total_groups:
        console.print()
        _print_duplicate_groups(console, dedup_result, limit=5, verbose=verbose)

    if exposure_result.skill_count and not scan_result.is_insufficient:
        console.print()
        _print_exposure(console, exposure_result, limit=5)

    if wasted:
        console.print()
        _print_savings(console, wasted=wasted, total=total_tokens)

    _print_warnings(console, scan_result)

    console.print()
    console.print(f"[dim]{TOKENIZER_DISCLAIMER}[/dim]")


def _print_cursor_sibling_warning(console: Console, scan_result: ScanResult) -> None:
    """Surface .cursor/rules/ presence so Cursor users know they weren't audited.

    Prints to stderr-style yellow line above the hero. promptc v0.1 doesn't
    walk .cursor/ — Cursor support is tracked for v0.2.
    """
    n = scan_result.cursor_sibling_files
    if n == 0:
        return
    console.print(
        f"[yellow]Detected .cursor/rules/ ({n} file{'s' if n != 1 else ''}) — "
        "not yet scanned. Cursor support is tracked for v0.2.[/yellow]"
    )
    console.print()


def _print_hero(
    console: Console,
    *,
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> None:
    """Dispatch hero rendering across the 3 framing states.

    Per `framing_locked.md`:
      - Insufficient (data threshold): no grade shown, neutral copy.
      - Debt (D / F): red, multiplier appears IN hero as supporting evidence.
      - Clean / Moderate (A / B / C): grade shown, multiplier moves down-page.
    """
    if scan_result.is_insufficient:
        _print_hero_insufficient(console, scan_result)
    elif grade.letter in ("D", "F"):
        _print_hero_debt(
            console,
            scan_result=scan_result,
            dedup_result=dedup_result,
            exposure_result=exposure_result,
            grade=grade,
        )
    else:
        _print_hero_clean(
            console,
            scan_result=scan_result,
            dedup_result=dedup_result,
            exposure_result=exposure_result,
            grade=grade,
        )


def _print_hero_insufficient(console: Console, scan_result: ScanResult) -> None:
    skill_count = sum(1 for f in scan_result.files if f.role is FileRole.SKILL)
    body_tokens = scan_result.skill_body_tokens

    title = Text("NOT ENOUGH TO AUDIT YET", style="bold")
    line1 = Text(
        f"Your .claude/ has {skill_count} skill file{'s' if skill_count != 1 else ''}"
        f" ({body_tokens:,} body tokens).",
        justify="center",
    )
    line2 = Text(
        "promptc currently audits .claude/ only -- if your prompts live in "
        ".cursor/rules/, support is tracked for v0.2.",
        style="dim",
        justify="center",
    )
    line3 = Text(
        "promptc needs at least 3 skills and 1,000 body tokens to find "
        "patterns. Add more skills, or point promptc at a larger directory.",
        style="dim",
        justify="center",
    )

    body = Group(line1, Text(""), line2, Text(""), line3)
    panel = Panel(body, title=title, border_style="cyan", padding=(1, 4))
    console.print(panel)


def _print_hero_clean(
    console: Console,
    *,
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> None:
    """A / B / C states. No multiplier in hero (moves to its own section)."""
    skill_count = exposure_result.skill_count
    skills_with_desc = skill_count - len(exposure_result.skills_without_description)

    title = Text(grade.display, style=f"bold {grade.color}")

    if grade.letter == "A":
        if dedup_result.total_groups == 0:
            headline = Text("Your .claude/ is clean.", justify="center")
            subtitle_text = (
                f"No duplicate content found. {skills_with_desc} of "
                f"{skill_count} skills have descriptions."
            )
        else:
            headline = Text(
                f"Mostly clean - {dedup_result.total_groups} small "
                f"duplicate group{'s' if dedup_result.total_groups != 1 else ''} flagged below.",
                justify="center",
            )
            subtitle_text = (
                f"{skills_with_desc} of {skill_count} skills have descriptions."
            )
    else:  # B or C
        headline = Text(
            f"{dedup_result.total_groups} duplicate "
            f"group{'s' if dedup_result.total_groups != 1 else ''} found "
            f"({dedup_result.total_wasted_tokens:,} tokens, "
            f"{grade.bloat_ratio:.0%} of body).",
            justify="center",
        )
        subtitle_text = (
            f"{skill_count} skill file{'s' if skill_count != 1 else ''} scanned. "
            "Details in the sections below."
        )

    pointer = Text(
        "See \"Skill Context Exposure\" below for worst-case load detail.",
        style="dim",
        justify="center",
    )

    subtitle = Text(subtitle_text, style="dim", justify="center")
    body = Group(
        Align.center(title),
        Text(""),
        headline,
        Text(""),
        subtitle,
        Text(""),
        pointer,
    )
    panel = Panel(body, border_style=grade.color, padding=(1, 4))
    console.print(panel)


def _print_hero_debt(
    console: Console,
    *,
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> None:
    """D / F states. Multiplier IN hero, framed as amplifying the verdict."""
    body_total = sum(f.body_tokens for f in scan_result.files)
    wasted = dedup_result.total_wasted_tokens
    files_affected = len(dedup_result.per_file_wasted)

    title = Text(grade.display, style=f"bold {grade.color}")

    headline = Text(justify="center")
    headline.append(f"{wasted:,}", style=f"bold {grade.color}")
    headline.append(
        f" tokens of duplicate content across {files_affected} "
        f"file{'s' if files_affected != 1 else ''}",
        style="bold",
    )

    ratio_line = Text(
        f"({grade.bloat_ratio:.0%} of {body_total:,} body tokens)",
        style="dim",
        justify="center",
    )

    mult = exposure_result.multiplier
    if mult and mult > 1:
        amplifier = Text(justify="center")
        amplifier.append("Plus ", style="dim")
        amplifier.append(f"{mult:.1f}x", style=f"bold {grade.color}")
        amplifier.append(" worst-case context exposure on top.", style="dim")
    else:
        amplifier = None

    pointer = Text("Top offenders below.", style="dim", justify="center")

    parts: list = [Align.center(title), Text(""), headline, ratio_line]
    if amplifier is not None:
        parts.extend([Text(""), amplifier])
    parts.extend([Text(""), pointer])
    body = Group(*parts)

    panel = Panel(body, border_style=grade.color, padding=(1, 4))
    console.print(panel)


def _print_savings(console: Console, *, wasted: int, total: int) -> None:
    post_total = max(total - wasted, 0)
    post_ratio = 0.0
    post_grade = compute_grade(post_ratio)

    console.print("[bold]Estimated Savings[/bold]")
    table = Table(show_header=False, box=None, pad_edge=False)
    table.add_column(style="dim")
    table.add_column(justify="right")
    table.add_column(justify="right", style="dim")
    table.add_row(
        "If duplicates removed",
        f"[green]-{wasted:,} tokens[/green]",
        f"({wasted / total:.1%})" if total else "",
    )
    table.add_row(
        "Post-dedup context",
        f"{post_total:,} tokens",
        "",
    )
    table.add_row(
        "Post-dedup grade (ceiling)",
        f"[{post_grade.color}]{post_grade.display}[/{post_grade.color}]",
        "",
    )
    console.print(table)
    console.print(
        "[dim]Ceiling assumes every duplicate promptc flagged is removed. "
        "Real-world savings depend on which ones you choose to keep.[/dim]"
    )


def _print_exposure(console: Console, report: ExposureReport, *, limit: int) -> None:
    console.print("[bold]Skill Context Exposure[/bold] [dim](worst-case load)[/dim]")

    promised = report.total_promised
    worst = report.total_worst_case
    mult = report.multiplier
    mult_display = f"{mult:.1f}x" if mult is not None else "n/a"

    summary = Table(show_header=False, box=None, pad_edge=False)
    summary.add_column(style="dim")
    summary.add_column(justify="right")
    summary.add_row("Promised load (description only)", f"{promised:,} tokens")
    summary.add_row("Worst-case load (SKILL.md body)", f"{worst:,} tokens")
    summary.add_row("Exposure multiplier", f"[red]{mult_display}[/red]")
    console.print(summary)

    top = [f for f in report.top_by_worst_case(limit) if f.worst_case_tokens]
    if top:
        console.print()
        console.print("[bold]Top skills by worst-case load:[/bold]")
        for f in top:
            if f.multiplier is None:
                mult_str = "[yellow]no description[/yellow]"
            else:
                mult_str = f"[red]{f.multiplier:.1f}x[/red]"
            console.print(
                f"  {f.file_path}  "
                f"[dim]{f.worst_case_tokens:,} worst / {f.promised_tokens:,} promised[/dim]  "
                f"{mult_str}"
            )

    if report.skills_without_description:
        count = len(report.skills_without_description)
        console.print()
        console.print(
            f"[yellow]{count} skill(s) have no description field[/yellow] -- "
            "promised load is 0, so there is no startup metadata to match "
            "against; the full body is the only way to know what they do."
        )

    console.print()
    console.print(f"[dim]{EXPOSURE_NARRATIVE}[/dim]")


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


def _print_json(
    scan_result: ScanResult,
    dedup_result: DedupResult,
    exposure_result: ExposureReport,
    grade: Grade,
) -> None:
    payload = {
        "root": str(scan_result.root),
        "total_files": scan_result.total_files,
        "total_tokens": scan_result.total_tokens,
        "tokenizer_disclaimer": TOKENIZER_DISCLAIMER,
        "grade": {
            "letter": grade.letter,
            "modifier": grade.modifier,
            "display": grade.display,
            "bloat_ratio": grade.bloat_ratio,
        },
        "duplicates": {
            "total_groups": dedup_result.total_groups,
            "total_wasted_tokens": dedup_result.total_wasted_tokens,
            "per_file_wasted": dedup_result.per_file_wasted,
            "groups": [_group_to_dict(g) for g in dedup_result.groups],
        },
        "progressive_disclosure": {
            "skill_count": exposure_result.skill_count,
            "total_promised_tokens": exposure_result.total_promised,
            "total_worst_case_tokens": exposure_result.total_worst_case,
            "exposure_multiplier": exposure_result.multiplier,
            "skills_without_description": exposure_result.skills_without_description,
            "narrative": EXPOSURE_NARRATIVE,
            "files": [
                {
                    "path": f.file_path,
                    "name": f.name,
                    "promised_tokens": f.promised_tokens,
                    "worst_case_tokens": f.worst_case_tokens,
                    "multiplier": f.multiplier,
                }
                for f in exposure_result.files
            ],
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
    # Write UTF-8 bytes directly to stdout so emoji / CJK in parsed skills
    # don't trip the Windows cp950 / cp1252 default console encoding.
    encoded = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
