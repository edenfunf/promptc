"""String-level duplicate detection via Jaccard similarity on word sets.

Algorithm (v0.1):
    1. Split each file body into paragraph chunks (blank-line delimited).
    2. Normalize each chunk (strip markdown, lowercase, collapse whitespace).
    3. Tokenize into a word set.
    4. Skip chunks with fewer than `min_words` unique words (noise guard).
    5. Compare every chunk pair with Jaccard similarity.
    6. Cluster chunks whose similarity is >= threshold using Union-Find.
    7. In each cluster, the longest chunk (by original token count) is
       the canonical; the rest count as waste.

This is O(N^2) in chunk count; fine for v0.1 scale (dozens of skills).
MinHash LSH is the obvious upgrade path when N grows.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from promptc.models import ParsedFile
from promptc.normalizer import chunk_paragraphs, normalize
from promptc.tokens import count_tokens


@dataclass(frozen=True)
class Chunk:
    file_path: str
    chunk_index: int
    raw: str
    normalized: str
    tokens: int
    words: frozenset[str]


@dataclass
class DuplicateGroup:
    chunks: list[Chunk]

    @property
    def canonical(self) -> Chunk:
        return max(self.chunks, key=lambda c: (c.tokens, -c.chunk_index, c.file_path))

    @property
    def wasted_tokens(self) -> int:
        return sum(c.tokens for c in self.chunks) - self.canonical.tokens

    @property
    def files_involved(self) -> list[str]:
        return sorted({c.file_path for c in self.chunks})

    @property
    def size(self) -> int:
        return len(self.chunks)

    @property
    def is_exact(self) -> bool:
        """True when all chunks in the group normalize to the same string."""
        return len({c.normalized for c in self.chunks}) == 1


@dataclass
class DedupResult:
    groups: list[DuplicateGroup] = field(default_factory=list)
    per_file_wasted: dict[str, int] = field(default_factory=dict)

    @property
    def total_wasted_tokens(self) -> int:
        return sum(g.wasted_tokens for g in self.groups)

    @property
    def total_groups(self) -> int:
        return len(self.groups)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity between two sets; empty vs empty is defined as 1.0."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    if intersection == 0:
        return 0.0
    return intersection / len(a | b)


class _UnionFind:
    def __init__(self, n: int) -> None:
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1


def _extract_chunks(files: list[ParsedFile], min_words: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for f in files:
        for i, paragraph in enumerate(chunk_paragraphs(f.body)):
            normalized = normalize(paragraph)
            words = frozenset(normalized.split())
            if len(words) < min_words:
                continue
            chunks.append(
                Chunk(
                    file_path=f.relative_path,
                    chunk_index=i,
                    raw=paragraph,
                    normalized=normalized,
                    tokens=count_tokens(paragraph),
                    words=words,
                )
            )
    return chunks


def find_duplicates(
    files: list[ParsedFile],
    *,
    threshold: float = 0.85,
    min_words: int = 5,
) -> DedupResult:
    """Detect near-duplicate paragraph chunks across `files`.

    - threshold: Jaccard similarity >= this counts as a duplicate pair.
    - min_words: chunks with fewer unique words after normalization are skipped.
    """
    chunks = _extract_chunks(files, min_words=min_words)
    n = len(chunks)
    if n < 2:
        return DedupResult()

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            if jaccard(chunks[i].words, chunks[j].words) >= threshold:
                uf.union(i, j)

    clusters: dict[int, list[Chunk]] = {}
    for i, chunk in enumerate(chunks):
        clusters.setdefault(uf.find(i), []).append(chunk)

    groups = [DuplicateGroup(chunks=members) for members in clusters.values() if len(members) > 1]
    groups.sort(key=lambda g: g.wasted_tokens, reverse=True)

    per_file: dict[str, int] = {}
    for group in groups:
        canonical = group.canonical
        for chunk in group.chunks:
            if chunk is canonical:
                continue
            per_file[chunk.file_path] = per_file.get(chunk.file_path, 0) + chunk.tokens

    return DedupResult(groups=groups, per_file_wasted=per_file)
