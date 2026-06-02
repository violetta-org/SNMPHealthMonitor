import os
import sys

def main():
    try:
        import rjsmin
        import rcssmin
    except ImportError:
        print("Error: rjsmin or rcssmin is not installed. Please install them first.")
        sys.exit(1)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    static_dir = os.path.join(base_dir, 'static')

    for root, dirs, files in os.walk(static_dir):
        # Skip vendor directory to avoid minifying third-party libraries (e.g. chart.js) which are already minified
        if 'vendor' in root:
            continue
            
        for file in files:
            # We only process files that do NOT contain '.src' in their names
            if '.src' in file:
                continue
                
            file_type = None
            if file.endswith('.js'):
                file_type = 'js'
            elif file.endswith('.css'):
                file_type = 'css'
                
            if not file_type:
                continue
                
            src = os.path.join(root, file)
            src_src = src.replace('.css', '.src.css').replace('.js', '.src.js')
            
            # Rename original to .src if it doesn't exist yet
            if os.path.exists(src) and not os.path.exists(src_src):
                print(f"Renaming {src} -> {src_src} (preserving source)")
                os.rename(src, src_src)
                
            if not os.path.exists(src_src):
                continue
                
            print(f"Minifying {src_src} -> {src}")
            with open(src_src, 'r', encoding='utf-8') as f:
                content = f.read()
                
            if file_type == 'js':
                minified = rjsmin.jsmin(content)
            else:
                minified = rcssmin.cssmin(content)
                
            with open(src, 'w', encoding='utf-8') as f:
                f.write(minified)

if __name__ == '__main__':
    main()
