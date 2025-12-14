"""Parse unified diffs and map line positions for GitHub API."""

import re
from dataclasses import dataclass
from pathlib import PurePath


@dataclass
class DiffHunk:
    """A single hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]
    header: str


@dataclass
class FileDiff:
    """Parsed diff for a single file."""

    old_path: str
    new_path: str
    hunks: list[DiffHunk]
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False
    is_binary: bool = False


@dataclass
class LinePosition:
    """Maps a line number in the new file to its position in the diff."""

    file_path: str
    line_number: int  # Line in the actual file
    diff_position: int  # Position in the diff (for GitHub API)
    content: str
    is_addition: bool


def parse_diff(diff_text: str) -> list[FileDiff]:
    """Parse a unified diff into structured FileDiff objects."""
    files: list[FileDiff] = []
    current_file: FileDiff | None = None
    current_hunk: DiffHunk | None = None

    lines = diff_text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i]

        # New file header
        if line.startswith("diff --git"):
            if current_file:
                files.append(current_file)

            # Parse paths from "diff --git a/path b/path"
            match = re.match(r"diff --git a/(.+) b/(.+)", line)
            if match:
                current_file = FileDiff(
                    old_path=match.group(1),
                    new_path=match.group(2),
                    hunks=[],
                )
            current_hunk = None
            i += 1
            continue

        # Check for new/deleted file markers
        if current_file:
            if line.startswith("new file mode"):
                current_file.is_new = True
            elif line.startswith("deleted file mode"):
                current_file.is_deleted = True
            elif line.startswith("rename from"):
                current_file.is_renamed = True
            elif line.startswith("Binary files"):
                current_file.is_binary = True

        # Hunk header
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line)
            if match and current_file:
                current_hunk = DiffHunk(
                    old_start=int(match.group(1)),
                    old_count=int(match.group(2)) if match.group(2) else 1,
                    new_start=int(match.group(3)),
                    new_count=int(match.group(4)) if match.group(4) else 1,
                    lines=[],
                    header=match.group(5).strip(),
                )
                current_file.hunks.append(current_hunk)
            i += 1
            continue

        # Diff content lines
        if current_hunk is not None and (
            line.startswith("+")
            or line.startswith("-")
            or line.startswith(" ")
            or line == ""
        ):
            current_hunk.lines.append(line)

        i += 1

    if current_file:
        files.append(current_file)

    return files


def get_line_positions(file_diff: FileDiff) -> dict[int, LinePosition]:
    """
    Build a mapping from new file line numbers to diff positions.

    GitHub's review API requires the "position" in the diff, not the line number.
    Position is 1-indexed and counts all lines in the diff (including context and removals).
    """
    positions: dict[int, LinePosition] = {}

    if file_diff.is_deleted or file_diff.is_binary:
        return positions

    diff_position = 0  # Position in the diff (1-indexed when used)

    for hunk in file_diff.hunks:
        diff_position += 1  # Count the @@ header line
        new_line = hunk.new_start

        for line in hunk.lines:
            diff_position += 1

            if line.startswith("+"):
                # Addition - this line exists in new file
                positions[new_line] = LinePosition(
                    file_path=file_diff.new_path,
                    line_number=new_line,
                    diff_position=diff_position,
                    content=line[1:],  # Remove the + prefix
                    is_addition=True,
                )
                new_line += 1
            elif line.startswith("-"):
                # Deletion - skip, no line number in new file
                pass
            else:
                # Context line
                positions[new_line] = LinePosition(
                    file_path=file_diff.new_path,
                    line_number=new_line,
                    diff_position=diff_position,
                    content=line[1:] if line.startswith(" ") else line,
                    is_addition=False,
                )
                new_line += 1

    return positions


def build_position_index(files: list[FileDiff]) -> dict[str, dict[int, LinePosition]]:
    """Build a complete index: {file_path: {line_number: LinePosition}}."""
    index: dict[str, dict[int, LinePosition]] = {}
    for file_diff in files:
        if not file_diff.is_binary and not file_diff.is_deleted:
            index[file_diff.new_path] = get_line_positions(file_diff)
    return index


def filter_files_by_patterns(
    files: list[FileDiff],
    include_patterns: list[str],
    exclude_patterns: list[str],
) -> list[FileDiff]:
    """Filter files by glob patterns.

    Uses PurePath.match() which properly handles ** glob patterns.
    """

    def matches_any(path: str, patterns: list[str]) -> bool:
        pure_path = PurePath(path)
        return any(pure_path.match(p) for p in patterns)

    filtered: list[FileDiff] = []
    for f in files:
        path = f.new_path

        # Check include patterns (if specified)
        if include_patterns and not matches_any(path, include_patterns):
            continue

        # Check exclude patterns
        if exclude_patterns and matches_any(path, exclude_patterns):
            continue

        filtered.append(f)

    return filtered
