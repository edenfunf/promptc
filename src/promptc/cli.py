from __future__ import annotations

from pathlib import Path

import click

from promptc import __version__


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="promptc")
@click.pass_context
def main(ctx: click.Context) -> None:
    """promptc — measure worst-case context exposure in your Claude / Cursor setup."""
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

    PATH defaults to the current working directory. If PATH does not already
    contain a .claude/ subdirectory, promptc will still scan PATH itself.
    """
    target = path / ".claude" if (path / ".claude").is_dir() else path
    click.echo(f"promptc v{__version__} — analyze is not wired up yet.")
    click.echo(f"Would analyze: {target}")
    click.echo(f"Format: {output_format} | HTML: {not no_html} | verbose: {verbose}")
    if open_report:
        click.echo("(--open flag received)")


if __name__ == "__main__":
    main()
