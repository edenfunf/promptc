"""Progressive disclosure exposure analysis.

Background (cited, not asserted):
    Claude Code's Skills documentation describes "progressive disclosure":
    at session start only the frontmatter metadata (name + description)
    loads into the context window; the full SKILL.md body is fetched on
    demand when the skill is actually invoked.

        https://docs.anthropic.com/en/docs/claude-code/skills

    Community reports describe configurations where the full body loads
    at session start anyway:

        https://github.com/anthropics/claude-code/issues/14882

This module computes the gap between those two scenarios *without*
claiming which one applies to any given user. We measure the ceiling.

Definitions used below:
    - promised load    = tokens for the frontmatter `name` and `description`
                         values (what the docs say is loaded at startup).
    - worst-case load  = tokens for the entire file (what the community
                         reports describe when progressive disclosure
                         does not kick in).
    - exposure multiplier = worst-case / promised, per file and aggregate.

Only SKILL files are subject to progressive disclosure. INSTRUCTIONS
(CLAUDE.md / AGENTS.md), PROMPTS (slash commands), and AGENTS are loaded
in full regardless, so they are excluded from this analysis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from promptc.models import FileRole, ParsedFile
from promptc.tokens import count_tokens

ANTHROPIC_DOCS_URL = "https://docs.anthropic.com/en/docs/claude-code/skills"
COMMUNITY_ISSUE_URL = "https://github.com/anthropics/claude-code/issues/14882"

EXPOSURE_NARRATIVE = (
    "Claude Code's Skills documentation describes progressive disclosure: "
    "at session start only frontmatter metadata (name + description) loads "
    "into the context window; the full SKILL.md body is fetched on demand "
    "when the skill is invoked."
    f"\n  Docs:  {ANTHROPIC_DOCS_URL}"
    "\n"
    "\nCommunity reports describe setups where the full body loads anyway."
    f"\n  Issue: {COMMUNITY_ISSUE_URL}"
    "\n"
    "\nThe multiplier above is the ceiling of your exposure if progressive "
    "disclosure does not kick in. This tool makes no claim about whether "
    "that happens in your setup; it measures the upper bound."
)


@dataclass
class FileExposure:
    file_path: str
    name: str | None
    promised_tokens: int
    worst_case_tokens: int

    @property
    def has_promise(self) -> bool:
        return self.promised_tokens > 0

    @property
    def multiplier(self) -> float | None:
        """worst-case / promised. Returns None when promised is 0 (undefined)."""
        if self.promised_tokens == 0:
            return None
        return self.worst_case_tokens / self.promised_tokens


@dataclass
class ExposureReport:
    files: list[FileExposure] = field(default_factory=list)
    skills_without_description: list[str] = field(default_factory=list)

    @property
    def total_promised(self) -> int:
        return sum(f.promised_tokens for f in self.files)

    @property
    def total_worst_case(self) -> int:
        return sum(f.worst_case_tokens for f in self.files)

    @property
    def multiplier(self) -> float | None:
        if self.total_promised == 0:
            return None
        return self.total_worst_case / self.total_promised

    @property
    def skill_count(self) -> int:
        return len(self.files)

    def top_by_worst_case(self, n: int) -> list[FileExposure]:
        return sorted(self.files, key=lambda f: f.worst_case_tokens, reverse=True)[:n]


def _promised_tokens(parsed: ParsedFile) -> int:
    """Tokens for frontmatter name + description combined.

    Prefers the cached ``description_tokens`` on the parsed file. Recomputes
    when either field is missing from the cache but present in frontmatter.
    """
    name_tokens = count_tokens(parsed.name) if parsed.name else 0
    if parsed.description_tokens is not None:
        description_tokens = parsed.description_tokens
    elif parsed.description is not None:
        description_tokens = count_tokens(parsed.description)
    else:
        description_tokens = 0
    return name_tokens + description_tokens


def analyze_exposure(files: list[ParsedFile]) -> ExposureReport:
    """Build an :class:`ExposureReport` over the SKILL files in ``files``.

    Non-skill files (instructions, prompts, agents, other) are not subject
    to progressive disclosure and are excluded.
    """
    report = ExposureReport()

    for parsed in files:
        if parsed.role is not FileRole.SKILL:
            continue

        promised = _promised_tokens(parsed)
        exposure = FileExposure(
            file_path=parsed.relative_path,
            name=parsed.name,
            promised_tokens=promised,
            worst_case_tokens=parsed.total_tokens,
        )
        report.files.append(exposure)

        if parsed.description is None:
            report.skills_without_description.append(parsed.relative_path)

    report.files.sort(key=lambda f: f.worst_case_tokens, reverse=True)
    return report
