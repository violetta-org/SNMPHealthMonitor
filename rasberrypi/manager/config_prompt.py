import os
import sys
import json
from typing import Dict, Any, Optional

# Setup project root path for imports
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Paths
_CONFIG_DIR = os.path.join(project_root, 'config')
_CONFIG_FILE = os.path.join(_CONFIG_DIR, 'config.json')
_OIDS_DIR = os.path.join(project_root, 'oids')

# Global config dict - will be populated after prompt
_config_dict: Optional[Dict[str, Any]] = None


def get_oids_file_path(oids_file: str) -> str:
    """Get full path to OIDs file."""
    
    # Try relative to oids directory
    oids_path = os.path.join(_OIDS_DIR, oids_file)
    if os.path.exists(oids_path):
        print(f"[DEBUG] Found OIDs file in oids directory: {oids_path}")
        return oids_path
    # Return as-is if not found (will raise error later)
    print(f"[WARNING] OIDs file not found, returning as-is: {oids_file}")
    return oids_file


def load_config_from_file() -> Dict[str, Any]:
    """Load config from JSON file if exists."""
    if os.path.exists(_CONFIG_FILE):
        try:
            print(f"[DEBUG] Loading config from file: {_CONFIG_FILE}")
            with open(_CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load config file: {e}")
    else:
        print(f"[DEBUG] Config file not found: {_CONFIG_FILE}, using empty config")
    return {}


def prompt_with_default(prompt_text: str, default: Any, value_type: type = str) -> Any:
    """Prompt user with default value shown."""
    if value_type == str:
        default_str = str(default)
        user_input = input(f"{prompt_text} [{default_str}]: ").strip()
        return user_input if user_input else default_str
    elif value_type == int:
        default_str = str(default)
        user_input = input(f"{prompt_text} [{default_str}]: ").strip()
        if not user_input:
            return default
        try:
            return int(user_input)
        except ValueError:
            print(f"[WARNING] Invalid integer, using default: {default}")
            return default
    elif value_type == float:
        default_str = str(default)
        user_input = input(f"{prompt_text} [{default_str}]: ").strip()
        if not user_input:
            return default
        try:
            return float(user_input)
        except ValueError:
            print(f"[WARNING] Invalid float, using default: {default}")
            return default
    else:
        return default


def prompt_config_interactive() -> Dict[str, Any]:
    """Interactive prompt for all config values - loads defaults from config.json."""
    global _config_dict
    
    # Load defaults from config.json
    file_config = load_config_from_file()
    
    # Get defaults from config.json or use empty strings
    snmp_config = file_config.get('snmp', {})
    query_config = file_config.get('query_service', {})
    
    print("\n" + "="*60)
    print("SNMP Manager Configuration")
    print("="*60)
    print("Press Enter to use default values from config.json (shown in brackets)")
    print()
    
    config = {}
    
    # SNMP settings - load from config.json
    print("--- SNMP Settings ---")
    config['snmp'] = {
        'agent': prompt_with_default("SNMP Agent IP", snmp_config.get('agent', '')),
        'port': prompt_with_default("SNMP Port", snmp_config.get('port', 161), int),
        'community': prompt_with_default("SNMP Community", snmp_config.get('community', '')),
        'version': prompt_with_default("SNMP Version (1 or 2c)", snmp_config.get('version', '')),
        'oids_file': prompt_with_default("OIDs File (relative to oids/)", snmp_config.get('oids_file', '')),
    }
    
    # Pull interval
    print("\n--- Collection Settings ---")
    config['pull_interval'] = prompt_with_default("Pull Interval (seconds)", file_config.get('pull_interval', 4.0), float)
    
    # Query service
    print("\n--- Query Service Settings ---")
    config['query_service'] = {
        'host': prompt_with_default("Query Service Host", query_config.get('host', '')),
        'notify_port': prompt_with_default("Query Service Notify Port", query_config.get('notify_port', 6003), int),
    }
    
    print("\n" + "="*60)
    print("Configuration Summary:")
    print(f"  SNMP Agent: {config['snmp']['agent']}:{config['snmp']['port']}")
    print(f"  SNMP Community: {config['snmp']['community']}")
    print(f"  SNMP Version: {config['snmp']['version']}")
    print(f"  OIDs File: {config['snmp']['oids_file']}")
    print(f"  Pull Interval: {config['pull_interval']}s")
    print(f"  Query Service: {config['query_service']['host']}:{config['query_service']['notify_port']}")
    print("="*60)
    
    confirm = input("\nUse this configuration? [Y/n]: ").strip().lower()
    if confirm and confirm != 'y':
        print("[INFO] Configuration cancelled, using defaults from config.json")
        # Load from file and store in _config_dict
        _config_dict = file_config
        return file_config
    
    # Store config globally
    _config_dict = config
    
    return config

def get_config() -> Dict[str, Any]:
    """Get current config dict (from prompt or load from file)."""
    global _config_dict
    
    # If config was set from prompt, return it
    if _config_dict is not None:
        return _config_dict
    
    # Otherwise load from file
    _config_dict = load_config_from_file()
    return _config_dict


# Convenience functions to get individual config values
def get_snmp_agent() -> str:
    """Get SNMP agent IP."""
    config = get_config()
    return config.get('snmp', {}).get('agent', '')

def get_snmp_port() -> int:
    """Get SNMP port."""
    config = get_config()
    return config.get('snmp', {}).get('port', 161)

def get_snmp_community() -> str:
    """Get SNMP community."""
    config = get_config()
    return config.get('snmp', {}).get('community', '')

def get_snmp_version() -> str:
    """Get SNMP version."""
    config = get_config()
    return config.get('snmp', {}).get('version', '')

def get_snmp_oids_file() -> str:
    """Get SNMP OIDs file."""
    config = get_config()
    return config.get('snmp', {}).get('oids_file', '')

def get_pull_interval() -> float:
    """Get pull interval."""
    config = get_config()
    return config.get('pull_interval', 4.0)

def get_notify_host() -> str:
    """Get query service host."""
    config = get_config()
    return config.get('query_service', {}).get('host', '')

def get_notify_port() -> int:
    """Get query service notify port."""
    config = get_config()
    return config.get('query_service', {}).get('notify_port', 6003)
