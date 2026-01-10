import os
import unicodedata

# ==========================================
# 2. HELPER FUNCTIONS (Các hàm hỗ trợ logic)
# ==========================================

def secure_filename_unicode(filename):
    r"""
    Secure filename sanitization that preserves Unicode characters (Vietnamese, Chinese, etc.)
    while removing dangerous characters that could cause Path Traversal attacks.
    
    Args:
        filename: Original filename from user upload
    
    Returns:
        Sanitized filename safe for file system operations
    
    Security measures:
    - Removes path separators: / \ (prevents directory traversal)
    - Removes parent directory references: .. (prevents traversal)
    - Removes null bytes: \x00 (prevents null byte injection)
    - Removes control characters (ASCII 0-31)
    - Removes dangerous characters: < > : " | ? * (invalid on Windows)
    - Normalizes Unicode to NFC form (consistent representation)
    - Limits filename length to 255 characters
    - Ensures filename is not empty after sanitization
    """
    if not filename:
        return 'unnamed_file'
    
    # Normalize Unicode to NFC (Canonical Decomposition, followed by Canonical Composition)
    # This ensures consistent representation of Vietnamese characters like ê, ơ, ư
    filename = unicodedata.normalize('NFC', filename)
    
    # Remove null bytes (security: null byte injection)
    filename = filename.replace('\x00', '')
    
    # Remove or replace dangerous characters
    dangerous_chars = {
        '/': '',   # Path separator (Unix)
        '\\': '',  # Path separator (Windows)
        '<': '',   # Invalid on Windows
        '>': '',   # Invalid on Windows
        ':': '',   # Drive letter separator on Windows
        '"': '',   # Quote
        '|': '',   # Pipe (invalid on Windows)
        '?': '',   # Wildcard (invalid on Windows)
        '*': '',   # Wildcard (invalid on Windows)
    }
    
    for char, replacement in dangerous_chars.items():
        filename = filename.replace(char, replacement)
    
    # Remove leading/trailing spaces and dots
    filename = filename.strip().strip('.')

    # Prevent traversal attempts manually (extra layer)
    while '..' in filename:
        filename = filename.replace('..', '.')
    
    # Remove control characters (ASCII 0-31) except newline/tab which we'll remove anyway
    filename = ''.join(char for char in filename if ord(char) >= 32 or char in '\t\n')
    filename = filename.replace('\t', '').replace('\n', '')
    
    # Remove leading/trailing dots and spaces (Windows issue: files can't start/end with these)
    filename = filename.strip('. ')
    
    # Prevent parent directory reference (security: path traversal)
    # Remove any occurrence of '..' 
    while '..' in filename:
        filename = filename.replace('..', '.')
    
    # Limit filename length (255 is typical max for most filesystems)
    # Reserve some space for potential extensions
    max_length = 255
    if len(filename) > max_length:
        # Try to preserve extension if present
        name_parts = filename.rsplit('.', 1)
        if len(name_parts) == 2 and len(name_parts[1]) <= 10:
            # Has extension, preserve it
            name = name_parts[0][:max_length - len(name_parts[1]) - 1]
            filename = f"{name}.{name_parts[1]}"
        else:
            # No extension or very long extension, just truncate
            filename = filename[:max_length]
    
    # Final safety check: ensure filename is not empty and not reserved
    if not filename or filename in ('.', '..'):
        return 'unnamed_file'
    
    # Windows reserved names (case-insensitive)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    
    # Check if filename (without extension) is a reserved name
    name_without_ext = filename.rsplit('.', 1)[0].upper()
    if name_without_ext in reserved_names:
        filename = f"file_{filename}"
    
    return filename

def _is_safe_path(base_dir, target_path):
    """
    Security check: Prevent Path Traversal attacks.
    Ensures target_path is within base_dir.
    """
    base_abs = os.path.abspath(base_dir)
    target_abs = os.path.abspath(target_path)
    return target_abs.startswith(base_abs)
