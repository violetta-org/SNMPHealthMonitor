import io
import base64
import pandas as pd
# import matplotlib
#
# # Use Agg backend for headless plotting
# matplotlib.use("Agg")
# import matplotlib.pyplot as plt
# import matplotlib.dates as mdates
#
# try:
#     import seaborn as sns
#     sns.set_theme(
#         style="darkgrid",
#         rc={
#             "axes.facecolor": "#111827",
#             "figure.facecolor": "#111827",
#             "axes.labelcolor": "white",
#             "text.color": "white",
#             "xtick.color": "white",
#             "ytick.color": "white",
#             "grid.alpha": 0.3,
#         },
#     )
# except Exception:
#     sns = None

def downsample_df(df: pd.DataFrame, max_points: int = 400) -> pd.DataFrame:
    if len(df) <= max_points:
        return df
    step = max(1, len(df) // max_points)
    return df.iloc[::step]

def generate_cpu_png(data: list, sysname: str) -> bytes:
    """Generate a PNG image bytes for CPU usage."""
    return None

def generate_history_plot_base64(cpu_data: list, sysname: str) -> dict:
    """Generate base64 encoded plot for history page."""
    return None

def _create_plot_response(fig, sysname, title):
    """Helper to finalize plot and return bytes."""
    return None

def generate_memory_plot(data: list, sysname: str) -> dict:
    return None

def generate_disk_plot(data: list, sysname: str) -> dict:
    return None

def generate_network_plot(data: list, sysname: str) -> dict:
    return None

def generate_temp_plot(data: list, sysname: str) -> dict:
    return None


