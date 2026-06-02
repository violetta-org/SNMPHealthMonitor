"""
File management utility functions.
Ported from legacy Flask app.py helper functions.

Security measures:
- Path traversal protection via _is_safe_path()
- Unicode-safe filename sanitization via secure_filename_unicode()
- Null byte injection prevention
- Windows reserved name protection
"""
import os
import re
import unicodedata

from django.conf import settings


# ---------------------------------------------------------------------------
# Path security helpers
# ---------------------------------------------------------------------------

def is_safe_path(base_dir: str, target_path: str) -> bool:
    """
    Prevent Path Traversal attacks.
    Ensures target_path resolves to a location within base_dir.
    """
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    return target_abs.startswith(base_abs)


def relpath_within_home(abs_path: str) -> str:
    """Return a forward-slash relative path from HOME_DIRECTORY."""
    try:
        rel = os.path.relpath(abs_path, settings.HOME_DIRECTORY)
        return rel.replace('\\', '/')
    except Exception:
        return abs_path


def normalize_rel_target(rel_path: str):
    """Normalize a relative path: strip leading ./ and backslashes."""
    if not rel_path:
        return None
    target = rel_path.replace('\\', '/').lstrip('./')
    return target or None


# ---------------------------------------------------------------------------
# Filename sanitization
# ---------------------------------------------------------------------------

# Windows reserved filenames
_RESERVED_NAMES = frozenset({
    'CON', 'PRN', 'AUX', 'NUL',
    *(f'COM{i}' for i in range(1, 10)),
    *(f'LPT{i}' for i in range(1, 10)),
})


def secure_filename_unicode(filename: str) -> str:
    """
    Sanitize a filename while preserving Unicode characters (Vietnamese, etc.).

    Security measures:
    - Removes path separators (/ \\) to prevent directory traversal
    - Removes parent directory references (..)
    - Removes null bytes and control characters
    - Removes characters invalid on Windows (< > : " | ? *)
    - Normalizes Unicode to NFC form
    - Limits length to 255 characters
    - Rejects Windows reserved names
    """
    if not filename:
        return 'unnamed_file'

    # Normalize Unicode to NFC
    filename = unicodedata.normalize('NFC', filename)

    # Remove null bytes
    filename = filename.replace('\x00', '')

    # Remove dangerous characters
    for ch in ('/', '\\', '<', '>', ':', '"', '|', '?', '*'):
        filename = filename.replace(ch, '')

    # Remove control characters (ASCII 0-31)
    filename = ''.join(c for c in filename if ord(c) >= 32)

    # Strip leading/trailing dots and spaces
    filename = filename.strip('. ')

    # Collapse consecutive dots (prevents ".." traversal)
    while '..' in filename:
        filename = filename.replace('..', '.')

    # Limit length, preserve extension
    max_length = 255
    if len(filename) > max_length:
        parts = filename.rsplit('.', 1)
        if len(parts) == 2 and len(parts[1]) <= 10:
            name = parts[0][:max_length - len(parts[1]) - 1]
            filename = f"{name}.{parts[1]}"
        else:
            filename = filename[:max_length]

    # Final safety checks
    if not filename or filename in ('.', '..'):
        return 'unnamed_file'

    # Windows reserved names
    name_without_ext = filename.rsplit('.', 1)[0].upper()
    if name_without_ext in _RESERVED_NAMES:
        filename = f"file_{filename}"

    return filename


# ---------------------------------------------------------------------------
# File type helpers
# ---------------------------------------------------------------------------

def is_archive(filename: str) -> bool:
    """Check if filename has an archive extension."""
    lower = filename.lower()
    return any(lower.endswith(ext) for ext in settings.ARCHIVE_EXTENSIONS)


def is_editable(filepath: str) -> bool:
    """
    Check if a file is editable (text file under MAX_EDIT_SIZE).
    Uses a heuristic: reads first 1024 bytes and checks for NUL byte.
    """
    try:
        size = os.path.getsize(filepath)
        if size > settings.MAX_EDIT_SIZE:
            return False
        with open(filepath, 'rb') as f:
            chunk = f.read(1024)
            return b'\x00' not in chunk
    except Exception:
        return False


def detect_language(filepath: str) -> str:
    """Map file extension to CodeMirror/editor language name."""
    lang_map = {
        'py': 'python', 'js': 'javascript', 'json': 'json',
        'md': 'markdown', 'yaml': 'yaml', 'yml': 'yaml',
        'html': 'html', 'css': 'css', 'c': 'c', 'h': 'c',
        'cpp': 'cpp', 'sh': 'shell', 'sql': 'sql',
        'xml': 'xml', 'txt': 'plaintext', 'conf': 'plaintext',
        'ini': 'plaintext', 'log': 'plaintext',
    }
    ext = os.path.splitext(filepath)[1].lower().lstrip('.')
    return lang_map.get(ext, 'plaintext')
