import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import seaborn as sns
import pandas as pd
from datetime import datetime

# Set up style
try:
    sns.set_theme(style="whitegrid") # Printer-friendly
except:
    pass

def generate_history_pdf(sysname: str, data: dict, start_time: datetime, end_time: datetime) -> bytes:
    """
    Generate a multi-page PDF report for system history.
    """
    buf = io.BytesIO()
    
    with PdfPages(buf) as pdf:
        # ==========================================
        # PAGE 1: Summary & CPU
        # ==========================================
        fig = plt.figure(figsize=(11.69, 8.27)) # A4 Landscape
        fig.suptitle(f"System History Report: {sysname}", fontsize=18, weight='bold')

        # Meta Info
        meta_text = (
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Report Range:\n"
            f"  Start: {start_time}\n"
            f"  End:   {end_time}\n\n"
            f"System Info:\n"
            f"  Hostname: {sysname}\n"
            # Add more static info if available in data['device_info']
        )
        fig.text(0.1, 0.85, meta_text, fontsize=12, family="monospace")

        # CPU Plot
        if 'cpu_percent' in data and data['cpu_percent']:
            ax_cpu = fig.add_axes([0.1, 0.1, 0.8, 0.5]) # [left, bottom, width, height]
            _plot_cpu(ax_cpu, data['cpu_percent'])
        
        pdf.savefig(fig)
        plt.close(fig)

        # ==========================================
        # PAGE 2: Memory & Swap
        # ==========================================
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle("Memory & Usage", fontsize=16)

        ax_mem = fig.add_subplot(211)
        if 'memory' in data and data['memory']:
            _plot_memory(ax_mem, data['memory'])
            
        ax_swap = fig.add_subplot(212)
        if 'swap' in data and data['swap']:
           pass # TODO: Plot swap if needed, or maybe share page with disk
            # For now, let's put Network here if Swap is empty or just leave it
        
        pdf.savefig(fig)
        plt.close(fig)

        # ==========================================
        # PAGE 3: Disk & Network
        # ==========================================
        fig = plt.figure(figsize=(11.69, 8.27))
        fig.suptitle("Storage & Network", fontsize=16)

        ax_net = fig.add_subplot(211)
        if 'net_io' in data and data['net_io']:
            _plot_network(ax_net, data['net_io'])

        ax_disk = fig.add_subplot(212)
        if 'disk_usage' in data and data['disk_usage']:
            _plot_disk(ax_disk, data['disk_usage'])

        pdf.savefig(fig)
        plt.close(fig)

    buf.seek(0)
    return buf.getvalue()


def _plot_cpu(ax, data):
    df = pd.DataFrame(data)
    if df.empty: return
    df['time'] = pd.to_datetime(df['time'])
    df['percent'] = pd.to_numeric(df['percent'])

    sns.lineplot(x='time', y='percent', data=df, ax=ax, color="#2980b9", linewidth=2)
    ax.set_title("CPU Usage (%)")
    ax.set_ylim(0, 100)
    ax.axhline(80, color='orange', linestyle='--')
    ax.axhline(90, color='red', linestyle='--')
    ax.set_ylabel("% Usage")
    ax.set_xlabel("Time")

def _plot_memory(ax, data):
    df = pd.DataFrame(data)
    if df.empty: return
    df['time'] = pd.to_datetime(df['time'])
    # Convert to GB
    df['used_gb'] = (df['total'] - df['free'] - df['buffers'] - df['cached']) / 1e9
    df['cached_gb'] = df['cached'] / 1e9
    df['buffers_gb'] = df['buffers'] / 1e9
    
    # We want a stacked area plot equivalent
    # Matplotlib stackplot request x, y1, y2, y3...
    ax.stackplot(df['time'], df['used_gb'], df['cached_gb'], df['buffers_gb'], 
                 labels=['App Used', 'Cached', 'Buffers'],
                 colors=['#8e44ad', '#3498db', '#95a5a6'], alpha=0.7)
    
    ax.set_title("Memory Breakdown (GB)")
    ax.set_ylabel("GB")
    ax.legend(loc='upper left')

def _plot_network(ax, data):
    df = pd.DataFrame(data)
    if df.empty: return
    df['time'] = pd.to_datetime(df['time'])
    # Convert to MB/s
    df['rx_mb'] = df['recv_bytes_s'] / 1e6
    df['tx_mb'] = df['send_bytes_s'] / 1e6
    
    # Group by time if multiple ifaces
    df_agg = df.groupby('time')[['rx_mb', 'tx_mb']].sum().reset_index()

    sns.lineplot(data=df_agg, x='time', y='tx_mb', ax=ax, label='TX (Upload)', color='#c0392b')
    sns.lineplot(data=df_agg, x='time', y='rx_mb', ax=ax, label='RX (Download)', color='#27ae60')
    
    ax.set_title("Network Throughput (MB/s)")
    ax.set_ylabel("MB/s")

def _plot_disk(ax, data):
    df = pd.DataFrame(data)
    if df.empty: return
    df['time'] = pd.to_datetime(df['time'])
    
    # Line plot per mount
    sns.lineplot(data=df, x='time', y='percent', hue='mount', ax=ax)
    
    ax.set_title("Disk Usage (%) per Mount")
    ax.set_ylim(0, 100)
    ax.set_ylabel("% Used")
