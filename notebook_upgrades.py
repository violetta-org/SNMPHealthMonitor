"""
Advanced Visualization Functions for System Diagnosis
Upgrades to data_exploration.ipynb
"""

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from typing import List, Dict, Optional, Tuple
import numpy as np

# %% [markdown]
"""
## Upgraded Visualization Functions

Advanced diagnostic visualizations for system performance analysis.
"""

# %%
def plot_disk_usage(df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Plot disk usage per mount point, filtering out virtual filesystems."""
    print(f"[DEBUG] Plotting disk usage for {sysname}")
    fig, ax = plt.subplots(figsize=(12, 6))
    
    if not df.empty and 'time' in df.columns and 'mount' in df.columns:
        # Filter out virtual filesystems
        virtual_patterns: List[str] = ['/run', '/dev', '/sys', '/proc']
        physical_mounts: pd.DataFrame = df[
            ~df['mount'].str.contains('|'.join(virtual_patterns), case=False, na=False)
        ]
        
        if not physical_mounts.empty:
            for mount in physical_mounts['mount'].unique():
                mount_df = physical_mounts[physical_mounts['mount'] == mount]
                if 'percent' in mount_df.columns:
                    ax.plot(mount_df['time'], mount_df['percent'], label=f'{mount}', marker='o', markersize=3)
            ax.set_xlabel('Time')
            ax.set_ylabel('Disk Usage (%)')
            ax.set_title(f'Disk Usage Over Time - {sysname} (Physical Storage Only)')
            ax.legend()
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
        else:
            ax.text(0.5, 0.5, 'No physical storage data available', ha='center', va='center', transform=ax.transAxes)
    else:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
    
    return fig

# %%
def calculate_disk_io_rates(df: pd.DataFrame) -> pd.DataFrame:
    """Calculate read/write bytes per second from disk I/O counters."""
    if df.empty or 'time' not in df.columns:
        return pd.DataFrame()
    
    result_df: pd.DataFrame = df.copy()
    result_df = result_df.sort_values(['disk', 'time'])
    
    # Calculate rates per disk
    result_df['read_bytes_s'] = None
    result_df['write_bytes_s'] = None
    
    for disk in result_df['disk'].unique():
        disk_df = result_df[result_df['disk'] == disk].copy()
        disk_df = disk_df.sort_values('time')
        
        if len(disk_df) > 1:
            # Calculate time differences in seconds
            time_diffs = disk_df['time'].diff().dt.total_seconds()
            
            # Calculate bytes differences
            read_bytes_diff = disk_df['read_bytes'].diff()
            write_bytes_diff = disk_df['write_bytes'].diff()
            
            # Calculate rates (bytes per second)
            disk_df.loc[disk_df.index[1:], 'read_bytes_s'] = (
                read_bytes_diff[1:] / time_diffs[1:]
            ).fillna(0)
            disk_df.loc[disk_df.index[1:], 'write_bytes_s'] = (
                write_bytes_diff[1:] / time_diffs[1:]
            ).fillna(0)
            
            result_df.loc[disk_df.index, 'read_bytes_s'] = disk_df['read_bytes_s']
            result_df.loc[disk_df.index, 'write_bytes_s'] = disk_df['write_bytes_s']
    
    return result_df

# %%
def plot_disk_io(df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Plot disk I/O rates (Read/Write bytes per second) over time."""
    print(f"[DEBUG] Plotting disk I/O for {sysname}")
    fig, ax = plt.subplots(figsize=(12, 6))
    
    if not df.empty and 'time' in df.columns and 'disk' in df.columns:
        # Calculate I/O rates
        df_with_rates = calculate_disk_io_rates(df)
        
        # Filter out virtual devices (loop, ram, zram, sr)
        physical_disks = df_with_rates[
            ~df_with_rates['disk'].str.contains('loop|ram|zram|sr', case=False, na=False)
        ]
        
        if not physical_disks.empty:
            for disk in physical_disks['disk'].unique():
                disk_df = physical_disks[physical_disks['disk'] == disk]
                
                if 'read_bytes_s' in disk_df.columns:
                    ax.plot(disk_df['time'], disk_df['read_bytes_s'] / 1e6, 
                           label=f'{disk} - Read', linestyle='-', marker='o', markersize=2, alpha=0.7)
                if 'write_bytes_s' in disk_df.columns:
                    ax.plot(disk_df['time'], disk_df['write_bytes_s'] / 1e6, 
                           label=f'{disk} - Write', linestyle='--', marker='s', markersize=2, alpha=0.7)
            
            ax.set_xlabel('Time')
            ax.set_ylabel('Disk I/O (MB/s)')
            ax.set_title(f'Disk I/O Rates Over Time - {sysname}')
            ax.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
            ax.grid(True, alpha=0.3)
            plt.xticks(rotation=45)
            plt.tight_layout()
        else:
            ax.text(0.5, 0.5, 'No physical disk I/O data available', ha='center', va='center', transform=ax.transAxes)
    else:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
    
    return fig

# %%
def plot_cpu_vs_network(cpu_df: pd.DataFrame, network_df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Dual-axis chart: CPU Usage vs Network Throughput."""
    print(f"[DEBUG] Plotting CPU vs Network interaction for {sysname}")
    fig, ax1 = plt.subplots(figsize=(14, 6))
    
    if cpu_df.empty or network_df.empty:
        ax1.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax1.transAxes)
        return fig
    
    # Calculate total CPU usage (average across all cores)
    if 'cpu' in cpu_df.columns and 'percent' in cpu_df.columns:
        cpu_total = cpu_df.groupby('time')['percent'].mean().reset_index()
        cpu_total.columns = ['time', 'cpu_percent']
        
        ax1.plot(cpu_total['time'], cpu_total['cpu_percent'], 
                color='blue', label='CPU Usage (%)', linewidth=2)
        ax1.set_xlabel('Time')
        ax1.set_ylabel('CPU Usage (%)', color='blue')
        ax1.tick_params(axis='y', labelcolor='blue')
        ax1.grid(True, alpha=0.3)
    
    # Calculate total network throughput
    if 'bytes_sent' in network_df.columns and 'bytes_recv' in network_df.columns:
        network_total = network_df.groupby('time').agg({
            'bytes_sent': 'sum',
            'bytes_recv': 'sum'
        }).reset_index()
        
        # Calculate rates (assuming time is sorted)
        network_total = network_total.sort_values('time')
        network_total['time_diff'] = network_total['time'].diff().dt.total_seconds()
        network_total['sent_mbps'] = (network_total['bytes_sent'].diff() / network_total['time_diff'] / 1e6).fillna(0)
        network_total['recv_mbps'] = (network_total['bytes_recv'].diff() / network_total['time_diff'] / 1e6).fillna(0)
        network_total['total_mbps'] = network_total['sent_mbps'] + network_total['recv_mbps']
        
        ax2 = ax1.twinx()
        ax2.plot(network_total['time'], network_total['total_mbps'], 
                color='red', label='Network Throughput (MB/s)', linewidth=2, linestyle='--')
        ax2.set_ylabel('Network Throughput (MB/s)', color='red')
        ax2.tick_params(axis='y', labelcolor='red')
    
    ax1.set_title(f'CPU vs Network Interaction - {sysname}\n(High CPU + High Network = Traffic Processing)')
    ax1.legend(loc='upper left')
    if 'ax2' in locals():
        ax2.legend(loc='upper right')
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    return fig

# %%
def plot_load_vs_cpu(load_df: pd.DataFrame, cpu_df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Overlay Load Average on CPU Usage to identify I/O bottlenecks."""
    print(f"[DEBUG] Plotting Load vs CPU interaction for {sysname}")
    fig, ax = plt.subplots(figsize=(14, 6))
    
    if load_df.empty or cpu_df.empty:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
        return fig
    
    # Calculate average CPU usage across all cores
    if 'cpu' in cpu_df.columns and 'percent' in cpu_df.columns:
        cpu_avg = cpu_df.groupby('time')['percent'].mean().reset_index()
        cpu_avg.columns = ['time', 'cpu_avg']
        
        # Plot CPU as area chart
        ax.fill_between(cpu_avg['time'], 0, cpu_avg['cpu_avg'], 
                       alpha=0.3, color='blue', label='CPU Usage (%)')
        ax.plot(cpu_avg['time'], cpu_avg['cpu_avg'], 
               color='blue', linewidth=2, alpha=0.7)
    
    # Plot Load Average as line
    if 'load_1m' in load_df.columns:
        ax2 = ax.twinx()
        ax2.plot(load_df['time'], load_df['load_1m'], 
                color='red', linewidth=2, marker='o', markersize=3, label='Load Average (1m)')
        ax2.set_ylabel('Load Average (1m)', color='red')
        ax2.tick_params(axis='y', labelcolor='red')
    
    ax.set_xlabel('Time')
    ax.set_ylabel('CPU Usage (%)', color='blue')
    ax.tick_params(axis='y', labelcolor='blue')
    ax.set_title(f'Load Average vs CPU Usage - {sysname}\n(High Load + Low CPU = I/O Wait Bottleneck)')
    ax.legend(loc='upper left')
    if 'ax2' in locals():
        ax2.legend(loc='upper right')
    ax.grid(True, alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    
    return fig

# %%
def create_correlation_heatmap(summary_df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Create correlation heatmap for all numeric metrics."""
    print(f"[DEBUG] Creating correlation heatmap for {sysname}")
    fig, ax = plt.subplots(figsize=(12, 10))
    
    if summary_df.empty:
        ax.text(0.5, 0.5, 'No data available', ha='center', va='center', transform=ax.transAxes)
        return fig
    
    # Select only numeric columns
    numeric_df = summary_df.select_dtypes(include=[np.number])
    
    if numeric_df.empty:
        ax.text(0.5, 0.5, 'No numeric data available', ha='center', va='center', transform=ax.transAxes)
        return fig
    
    # Calculate correlation matrix
    corr_matrix = numeric_df.corr()
    
    # Create heatmap
    sns.heatmap(corr_matrix, annot=True, fmt='.2f', cmap='coolwarm', 
                center=0, vmin=-1, vmax=1, square=True, linewidths=0.5,
                cbar_kws={"shrink": 0.8}, ax=ax)
    
    ax.set_title(f'Metric Correlation Heatmap - {sysname}\n(Pearson Correlation: -1 to +1)')
    plt.xticks(rotation=45, ha='right')
    plt.yticks(rotation=0)
    plt.tight_layout()
    
    return fig

# %%
def create_diagnostic_pairplot(summary_df: pd.DataFrame, sysname: str) -> plt.Figure:
    """Create pairplot for key diagnostic metrics."""
    print(f"[DEBUG] Creating diagnostic pairplot for {sysname}")
    
    # Select specific metrics for pairplot
    required_cols: List[str] = [
        'cpu_percent', 'memory_percent', 'load_1m', 
        'bytes_recv', 'bytes_sent', 'cpu_temp'
    ]
    
    available_cols: List[str] = [col for col in required_cols if col in summary_df.columns]
    
    if len(available_cols) < 2:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, f'Insufficient data. Available: {available_cols}', 
               ha='center', va='center', transform=ax.transAxes)
        return fig
    
    pairplot_df = summary_df[available_cols].copy()
    
    # Remove rows with too many NaN values
    pairplot_df = pairplot_df.dropna(thresh=len(available_cols) * 0.5)
    
    if pairplot_df.empty:
        fig, ax = plt.subplots(figsize=(8, 6))
        ax.text(0.5, 0.5, 'No complete data available for pairplot', 
               ha='center', va='center', transform=ax.transAxes)
        return fig
    
    # Create pairplot
    g = sns.pairplot(pairplot_df, diag_kind='kde', plot_kws={'alpha': 0.6, 's': 20})
    g.fig.suptitle(f'Diagnostic Pairplot - {sysname}\n(Key Metrics Relationships)', y=1.02)
    plt.tight_layout()
    
    return g.fig

# %%
def create_summary_dataframe(
    cpu_df: pd.DataFrame,
    memory_df: pd.DataFrame,
    load_df: pd.DataFrame,
    network_df: pd.DataFrame,
    temp_df: pd.DataFrame,
    disk_io_df: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """Merge multiple dataframes on time index for correlation analysis."""
    print("[DEBUG] Creating summary dataframe for correlation analysis")
    
    summary_dfs: List[pd.DataFrame] = []
    
    # CPU: Average across all cores per time point
    if not cpu_df.empty and 'time' in cpu_df.columns and 'percent' in cpu_df.columns:
        cpu_summary = cpu_df.groupby('time')['percent'].mean().reset_index()
        cpu_summary.columns = ['time', 'cpu_percent']
        summary_dfs.append(cpu_summary)
    
    # Memory: Use percent directly
    if not memory_df.empty and 'time' in memory_df.columns and 'percent' in memory_df.columns:
        memory_summary = memory_df[['time', 'percent']].copy()
        memory_summary.columns = ['time', 'memory_percent']
        summary_dfs.append(memory_summary)
    
    # Load Average: Use load_1m
    if not load_df.empty and 'time' in load_df.columns and 'load_1m' in load_df.columns:
        load_summary = load_df[['time', 'load_1m']].copy()
        summary_dfs.append(load_summary)
    
    # Network: Sum bytes_recv and bytes_sent per time point
    if not network_df.empty and 'time' in network_df.columns:
        if 'bytes_recv' in network_df.columns and 'bytes_sent' in network_df.columns:
            network_summary = network_df.groupby('time').agg({
                'bytes_recv': 'sum',
                'bytes_sent': 'sum'
            }).reset_index()
            summary_dfs.append(network_summary)
    
    # Temperature
    if not temp_df.empty and 'time' in temp_df.columns and 'cpu_temp' in temp_df.columns:
        temp_summary = temp_df[['time', 'cpu_temp']].copy()
        summary_dfs.append(temp_summary)
    
    # Disk I/O: Sum read/write bytes per time point
    if disk_io_df is not None and not disk_io_df.empty and 'time' in disk_io_df.columns:
        if 'read_bytes' in disk_io_df.columns and 'write_bytes' in disk_io_df.columns:
            disk_io_summary = disk_io_df.groupby('time').agg({
                'read_bytes': 'sum',
                'write_bytes': 'sum'
            }).reset_index()
            disk_io_summary.columns = ['time', 'disk_read_bytes', 'disk_write_bytes']
            summary_dfs.append(disk_io_summary)
    
    if not summary_dfs:
        return pd.DataFrame()
    
    # Merge all dataframes on time (inner join to align timestamps)
    result_df = summary_dfs[0]
    for df in summary_dfs[1:]:
        result_df = pd.merge(result_df, df, on='time', how='inner')
    
    # Set time as index for easier correlation analysis
    result_df = result_df.set_index('time').sort_index()
    
    print(f"[DEBUG] Summary dataframe created with {len(result_df)} time points and {len(result_df.columns)} metrics")
    return result_df
