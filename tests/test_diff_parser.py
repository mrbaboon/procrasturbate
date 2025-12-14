"""Tests for the diff parser."""

import pytest
from procrasturbate.services.diff_parser import (
    parse_diff,
    get_line_positions,
    build_position_index,
    filter_files_by_patterns,
)


SAMPLE_DIFF = """diff --git a/src/main.py b/src/main.py
index 1234567..abcdefg 100644
--- a/src/main.py
+++ b/src/main.py
@@ -10,6 +10,8 @@ def main():
     print("Hello")
     print("World")

+    # New comment
+    print("New line")
     return 0


diff --git a/src/utils.py b/src/utils.py
new file mode 100644
--- /dev/null
+++ b/src/utils.py
@@ -0,0 +1,5 @@
+def helper():
+    pass
+
+def another():
+    return True
"""


def test_parse_diff_basic():
    """Test basic diff parsing."""
    files = parse_diff(SAMPLE_DIFF)

    assert len(files) == 2
    assert files[0].new_path == "src/main.py"
    assert files[1].new_path == "src/utils.py"
    assert files[1].is_new == True


def test_parse_diff_hunks():
    """Test hunk parsing."""
    files = parse_diff(SAMPLE_DIFF)

    main_py = files[0]
    assert len(main_py.hunks) == 1
    assert main_py.hunks[0].new_start == 10
    assert main_py.hunks[0].new_count == 8


def test_get_line_positions():
    """Test line position mapping."""
    files = parse_diff(SAMPLE_DIFF)
    positions = get_line_positions(files[0])

    # Line 13 should be the "+ # New comment" line
    assert 13 in positions
    assert positions[13].is_addition == True
    assert "New comment" in positions[13].content


def test_build_position_index():
    """Test full position index building."""
    files = parse_diff(SAMPLE_DIFF)
    index = build_position_index(files)

    assert "src/main.py" in index
    assert "src/utils.py" in index

    # New file should have all lines mapped (including trailing newline)
    utils_positions = index["src/utils.py"]
    assert len(utils_positions) == 6


def test_filter_files_by_patterns():
    """Test file filtering by glob patterns."""
    files = parse_diff(SAMPLE_DIFF)

    # Include only main.py
    filtered = filter_files_by_patterns(files, ["**/main.py"], [])
    assert len(filtered) == 1
    assert filtered[0].new_path == "src/main.py"

    # Exclude utils.py
    filtered = filter_files_by_patterns(files, ["**/*"], ["**/utils.py"])
    assert len(filtered) == 1
    assert filtered[0].new_path == "src/main.py"


def test_empty_diff():
    """Test parsing empty diff."""
    files = parse_diff("")
    assert len(files) == 0


def test_binary_file_diff():
    """Test handling binary file diffs."""
    binary_diff = """diff --git a/image.png b/image.png
new file mode 100644
Binary files /dev/null and b/image.png differ
"""
    files = parse_diff(binary_diff)
    assert len(files) == 1
    assert files[0].is_binary == True
