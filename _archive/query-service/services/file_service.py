import os
import shutil
import json
import time

# File Manager: Secure home directory for managed files
# Default to a folder relative to project or user home. Using absolute path for safety.
# In query-service context, let's keep it consistent.
HOME_DIRECTORY = os.path.abspath(os.path.expanduser('~/managed_files'))
# Create HOME_DIRECTORY if it doesn't exist
if not os.path.exists(HOME_DIRECTORY):
    os.makedirs(HOME_DIRECTORY)
    print(f"Created managed files directory: {HOME_DIRECTORY}")

BACKUP_DIRECTORY = os.path.join(HOME_DIRECTORY, '.backups')
os.makedirs(BACKUP_DIRECTORY, exist_ok=True)
BACKUP_RETENTION = 10  # keep last N backups per file

TRASH_DIRECTORY = os.path.join(HOME_DIRECTORY, '.trash')
os.makedirs(TRASH_DIRECTORY, exist_ok=True)

MAX_EDIT_SIZE = 10 * 1024 * 1024  # 10 MB 

def create_backup_if_needed(abs_path):
    """Simple backup mechanism: copy file to .backups folder with timestamp."""
    try:
        if not os.path.exists(abs_path) or os.path.isdir(abs_path):
            return
            
        ts = str(int(time.time()))
        rel_path = os.path.relpath(abs_path, HOME_DIRECTORY).replace(os.sep, '_')
        backup_name = f"{rel_path}.{ts}"
        backup_path = os.path.join(BACKUP_DIRECTORY, backup_name)
        
        shutil.copy2(abs_path, backup_path)
        
        # Cleanup old backups
        _cleanup_old_backups(rel_path)
    except Exception as e:
        print(f"Backup error for {abs_path}: {e}")

def _cleanup_old_backups(rel_path_key):
    try:
        all_backups = []
        for f in os.listdir(BACKUP_DIRECTORY):
            if f.startswith(rel_path_key + '.'):
                all_backups.append(f)
        
        if len(all_backups) > BACKUP_RETENTION:
            all_backups.sort() # sort by timestamp (part of filename)
            to_delete = all_backups[:len(all_backups) - BACKUP_RETENTION]
            for f in to_delete:
                os.remove(os.path.join(BACKUP_DIRECTORY, f))
    except Exception:
        pass

def move_to_trash(abs_path):
    try:
        ts = str(int(time.time()))
        basename = os.path.basename(abs_path)
        trash_name = f"{ts}_{basename}"
        trash_path = os.path.join(TRASH_DIRECTORY, trash_name)
        
        # Save metadata
        meta = {
            "original_path": abs_path,
            "deletion_time": ts
        }
        with open(trash_path + '.json', 'w') as f:
            json.dump(meta, f)
            
        if os.path.isdir(abs_path):
            shutil.move(abs_path, trash_path)
        else:
            shutil.move(abs_path, trash_path)
        return True
    except Exception as e:
        print(f"Trash error: {e}")
        return False
