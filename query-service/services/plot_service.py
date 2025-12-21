import io
import base64
import pandas as pd
import matplotlib

# Use Agg backend for headless plotting
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

try:
    import seaborn as sns
    sns.set_theme(
        style="darkgrid",
        rc={
            "axes.facecolor": "#111827",
            "figure.facecolor": "#111827",
            "axes.labelcolor": "white",
            "text.color": "white",
            "xtick.color": "white",
            "ytick.color": "white",
            "grid.alpha": 0.3,
        },
    )
except Exception:
    sns = None

def downsample_df(df: pd.DataFrame, max_points: int = 400) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step]

def generate_cpu_png(data: list, sysname: str) -> bytes:
    """Generate a PNG image bytes for CPU usage."""
    if not data:
        return None
        
    df = pd.DataFrame(data)
    if 'time' in df and 'percent' in df:
         # Ensure types
        df['time'] = pd.to_datetime(df['time'])
        df['percent'] = pd.to_numeric(df['percent'])
    else:
        return None

    df = downsample_df(df.dropna(subset=["percent"]), 400)
    
    fig, ax = plt.subplots(figsize=(12, 3))
    ax.plot(df["time"], df["percent"], linewidth=1.8, color="#00d6ff")
    ax.set_ylim(0, 100)
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    ax.set_title(f"CPU Usage (%) – {sysname}", fontsize=12)
    ax.set_ylabel("Percent")
    ax.set_xlabel("Time")
    ax.axhline(80, color="red", linestyle="--", alpha=0.5, linewidth=1)
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#111827", transparent=False, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf.getvalue()

def generate_history_plot_base64(cpu_data: list, sysname: str) -> dict:
    """Generate base64 encoded plot for history page."""
    if not cpu_data:
        return None

    # Filter valid points
    times = [p.get("time") for p in cpu_data if p.get("percent") is not None]
    values = [float(p.get("percent")) for p in cpu_data if p.get("percent") is not None]
    
    if not times or not values:
        return None

    fig, ax = plt.subplots(figsize=(8, 3))
    if sns:
        sns.lineplot(x=times, y=values, ax=ax)
    else:
        ax.plot(times, values, color="#4dbd74")

    ax.set_title(f"CPU Percent ({sysname})")
    ax.set_xlabel("Time")
    ax.set_ylabel("Percent")
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    
    return {"image": f"data:image/png;base64,{encoded}", "points": len(values)}

def _create_plot_response(fig, sysname, title):
    """Helper to finalize plot and return bytes."""
    ax = fig.gca()
    # Common styling
    ax.set_title(f"{title} – {sysname}", fontsize=12)
    ax.set_xlabel("Time")
    fig.autofmt_xdate()
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#111827", transparent=False, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    encoded = base64.b64encode(buf.read()).decode("ascii")
    return {"image": f"data:image/png;base64,{encoded}"}

def generate_memory_plot(data: list, sysname: str) -> dict:
    if not data: return None
    df = pd.DataFrame(data)
    if df.empty: return None
    df['time'] = pd.to_datetime(df['time'])
    
    # Check if we have downsampled columns (total, free, buffers, cached)
    # If using 'mem_usage' view or similar, columns might differ. 
    # Assuming standard structure from get_memory_metrics
    
    # Convert to GB
    # Fallback to 0 for missing columns
    for col in ['total', 'free', 'buffers', 'cached', 'used']:
         if col not in df.columns: df[col] = 0

    df['used_gb'] = (df['total'] - df['free'] - df['buffers'] - df['cached']) / 1e9
    df['cached_gb'] = df['cached'] / 1e9
    df['buffers_gb'] = df['buffers'] / 1e9

    df = downsample_df(df, 400)
    
    fig, ax = plt.subplots(figsize=(8, 3))
    
    # Stackplot needs sorted x
    df = df.sort_values('time')
    
    ax.stackplot(df['time'], df['used_gb'], df['cached_gb'], df['buffers_gb'],
                 labels=['App Used', 'Cached', 'Buffers'],
                 colors=['#9B8CFF', '#4DA3FF', '#a29bfe'], alpha=0.8)
    
    ax.set_ylabel("GB")
    ax.legend(loc='upper left', facecolor='#1f2937', edgecolor='none', labelcolor='white')
    return _create_plot_response(fig, sysname, "Memory Usage")

def generate_disk_plot(data: list, sysname: str) -> dict:
    if not data: return None
    df = pd.DataFrame(data)
    if df.empty: return None
    df['time'] = pd.to_datetime(df['time'])
    df['percent'] = pd.to_numeric(df['percent'])
    
    df = downsample_df(df, 400)
    
    fig, ax = plt.subplots(figsize=(8, 3))
    
    if sns:
        sns.lineplot(data=df, x='time', y='percent', hue='mount', ax=ax, palette="viridis", linewidth=2)
    else:
        # Fallback if no seaborn
        for mount, grp in df.groupby('mount'):
            ax.plot(grp['time'], grp['percent'], label=mount)
            
    ax.set_ylabel("Used %")
    ax.set_ylim(0, 100)
    ax.legend(loc='upper right', facecolor='#1f2937', edgecolor='none', labelcolor='white')
    return _create_plot_response(fig, sysname, "Disk Usage")

def generate_network_plot(data: list, sysname: str) -> dict:
    if not data: return None
    df = pd.DataFrame(data)
    if df.empty: return None
    df['time'] = pd.to_datetime(df['time'])
    
    # Convert to MB/s
    df['rx_mb'] = pd.to_numeric(df['recv_bytes_s']) / 1e6
    df['tx_mb'] = pd.to_numeric(df['send_bytes_s']) / 1e6

    # Aggregate if multiple interfaces (though usually one primary)
    df_agg = df.groupby('time')[['rx_mb', 'tx_mb']].sum().reset_index()
    df_agg = downsample_df(df_agg, 400)

    fig, ax = plt.subplots(figsize=(8, 3))
    
    ax.plot(df_agg['time'], df_agg['tx_mb'], label='TX (Upload)', color='#FF6B6B', linewidth=1.5)
    ax.plot(df_agg['time'], df_agg['rx_mb'], label='RX (Download)', color='#1DD1A1', linewidth=1.5)
    
    ax.set_ylabel("MB/s")
    ax.legend(loc='upper left', facecolor='#1f2937', edgecolor='none', labelcolor='white')
    return _create_plot_response(fig, sysname, "Network Traffic")

def generate_temp_plot(data: list, sysname: str) -> dict:
    if not data: return None
    df = pd.DataFrame(data)
    if df.empty: return None
    df['time'] = pd.to_datetime(df['time'])
    df['cpu_temp'] = pd.to_numeric(df['cpu_temp'])
    
    df = downsample_df(df, 400)
    
    fig, ax = plt.subplots(figsize=(8, 3))
    ax.plot(df['time'], df['cpu_temp'], color='#FF4757', linewidth=2)
    
    ax.set_ylabel("Celsius")
    return _create_plot_response(fig, sysname, "CPU Temperature")

