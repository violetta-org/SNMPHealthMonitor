import os
import re

TEMPLATE_DIR = r"c:\Users\LAPTOP T&T\VIOLETTA\Documents\MQF\Tài liệu học tập\Sixth Semester\Lập trình Python\PBL4\sources\SNMPHealthMonitor\server_django\templates"

def convert_jinja_to_django(content):
    # 1. Static files
    # {{ url_for('static', filename='path/to/file') }} -> {% static 'path/to/file' %}
    content = re.sub(r"\{\{\s*url_for\('static',\s*filename=['\"](.*?)['\"]\)\s*\}\}", r"{% static '\1' %}", content)
    
    # 2. Add {% load static %} if static is used and not present
    if "{% static" in content and "{% load static %}" not in content:
        # naive insertion at top (after extends if present)
        if "{% extends" in content:
            content = re.sub(r"({% extends .*? %})", r"\1\n{% load static %}", content)
        else:
            content = "{% load static %}\n" + content

    # 3. Common web routes replacements
    replacements = [
        (r"url_for\('web\.index'\)", r"url 'web:index'"),
        (r"url_for\('web\.login'\)", r"url 'web:login'"),
        (r"url_for\('web\.dashboard_default'\)", r"url 'web:dashboard_default'"),
        # dashboard_sys and topic are harder due to args, checking for simple invocations without args or simple known ones
        
        # Files/Edit/etc
        (r"url_for\('web\.files'\)", r"url 'web:files'"),
        (r"url_for\('web\.files',\s*req_path=(.*?)\)", r"url 'web:files' \1"), # Attempt to capture arg
        (r"url_for\('web\.trash'\)", r"url 'web:trash'"),
        (r"url_for\('web\.system'\)", r"url 'web:system'"),
        (r"url_for\('web\.logs_view'\)", r"url 'web:logs_view'"),
        (r"url_for\('web\.logout'\)", r"url 'web:logout'"),
        
        # Download
        (r"url_for\('web\.download',\s*filename=(.*?)\)", r"url 'web:download' \1"),
        
        # Edit
        (r"url_for\('web\.edit',\s*req_path=(.*?)\)", r"url 'web:edit' \1"),
        
        # API calls - replace with hardcoded /api/... for now to prevent breakage or url 'api_something' if I can guess names?
        # User didn't ask to migrate API, just Frontend. 
        # But if valid_links are required, I'll use placeholders.
        # "Replace any url_for('function_name') with standard Django {% url 'route_name' %}"
        # I'll replace 'api.api_save' with 'api:api_save' assuming I might shadow them later, or just '#'.
        # But wait, NinjaAPI uses different URL structure usually. defaults to /api/...
        # I'll just comment them out or leave them broken? No, they will cause TemplateSyntaxError.
        # I will replace them with '#'
    ]
    
    for old, new in replacements:
        # Regex for {{ old }} -> {% new %}
        # The key is catching the whole tag {{ ... }} if possible, or just the url_for part inside.
        # DTL use {% url ... %} instead of {{ url_for(...) }}
        # So {{ url_for(...) }} -> {% url ... %}
        
        # We need to handle {{ url_for(...) }} entirely.
        
        # Case 1: href="{{ url_for(...) }}" -> href="{% url ... %}"
        # Pattern: \{\{\s*url_for\(...\)\s*\}\}
        
        # Let's construct specific regexes
        pattern = r"\{\{\s*" + old + r"\s*\}\}"
        replacement = r"{% " + new + r" %}"
        content = re.sub(pattern, replacement, content)
        
    # Generic catch-all for remaining url_for (like api)
    # Replace {{ url_for('api.xyz') }} with '#'
    content = re.sub(r"\{\{\s*url_for\('api\..*?'\)\s*\}\}", r"#", content)
    content = re.sub(r"\{\{\s*url_for\('api\..*?',\s*.*?\)\s*\}\}", r"#", content)
    
    return content

for root, dirs, files in os.walk(TEMPLATE_DIR):
    for file in files:
        if file.endswith(".html"):
            path = os.path.join(root, file)
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            
            new_content = convert_jinja_to_django(content)
            
            if content != new_content:
                print(f"Converting {file}...")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(new_content)

print("Done.")
