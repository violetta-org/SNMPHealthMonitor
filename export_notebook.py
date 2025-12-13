"""
Script to export Jupyter notebook to PDF using nbconvert.
This works around the VS Code extension issue with jupyter nbconvert script wrapper.
"""
import sys
import subprocess
from pathlib import Path

def execute_notebook(notebook_path: Path, timeout: int = 600) -> bool:
    """Execute notebook cells to generate outputs before export."""
    print(f"[DEBUG] Executing notebook {notebook_path} to generate outputs...")
    
    try:
        import nbclient
        from nbclient import NotebookClient
        
        with open(notebook_path, 'r', encoding='utf-8') as f:
            import nbformat
            nb = nbformat.read(f, as_version=4)
        
        client = NotebookClient(nb, timeout=timeout, kernel_name='python3')
        client.execute()
        
        # Save executed notebook
        with open(notebook_path, 'w', encoding='utf-8') as f:
            nbformat.write(nb, f)
        
        print(f"[DEBUG] Notebook executed successfully")
        return True
    except ImportError:
        print("[WARNING] nbclient not available. Install with: pip install nbclient")
        print("[INFO] Exporting without executing (no outputs will be included)")
        return False
    except Exception as e:
        print(f"[WARNING] Failed to execute notebook: {e}")
        print("[INFO] Exporting without executing (no outputs will be included)")
        return False

def export_notebook(notebook_path: str, output_dir: str = None, execute: bool = True) -> None:
    """Export .ipynb notebook to PDF using nbconvert."""
    notebook_path = Path(notebook_path)
    
    if not notebook_path.exists():
        print(f"[ERROR] Notebook not found: {notebook_path}")
        return
    
    if notebook_path.suffix != '.ipynb':
        print(f"[ERROR] File must be a .ipynb notebook file")
        return
    
    # Execute notebook to generate outputs if requested
    if execute:
        execute_notebook(notebook_path)
    
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = notebook_path.parent
    
    print(f"[DEBUG] Exporting {notebook_path} to PDF...")
    print(f"[DEBUG] Output directory: {output_dir}")
    
    # Use python -m nbconvert instead of jupyter nbconvert
    cmd = [
        sys.executable,
        "-m", "nbconvert",
        "--to", "pdf",
        str(notebook_path),
        "--output-dir", str(output_dir)
    ]
    
    print(f"[DEBUG] Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            print(f"[SUCCESS] PDF exported successfully to {output_dir}")
            if result.stdout:
                print(f"[DEBUG] Output: {result.stdout}")
        else:
            print(f"[ERROR] Export failed with return code {result.returncode}")
            print(f"[DEBUG] stderr: {result.stderr}")
            if "xelatex" in result.stderr.lower():
                print("\n[INFO] xelatex error detected. Make sure:")
                print("  1. MiKTeX is installed and in PATH")
                print("  2. Run 'miktex update' to update packages")
                print("  3. Try: conda activate manager; xelatex --version")
    except subprocess.TimeoutExpired:
        print("[ERROR] Export timed out after 5 minutes")
    except Exception as e:
        print(f"[ERROR] Export failed: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python export_notebook.py <notebook.ipynb> [output_dir] [--no-execute]")
        print("Options:")
        print("  --no-execute  Skip executing notebook (export without outputs)")
        print("Examples:")
        print("  python export_notebook.py data_exploration.ipynb")
        print("  python export_notebook.py data_exploration.ipynb ./output")
        print("  python export_notebook.py data_exploration.ipynb --no-execute")
        sys.exit(1)
    
    notebook_path = sys.argv[1]
    output_dir = None
    execute = True
    
    # Parse arguments
    for arg in sys.argv[2:]:
        if arg == "--no-execute":
            execute = False
        elif not arg.startswith("--"):
            output_dir = arg
    
    export_notebook(notebook_path, output_dir, execute)
