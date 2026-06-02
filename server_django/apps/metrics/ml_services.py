"""
Predictive AIOps — Machine Learning Services for Resource Forecasting.

Implements Linear Regression-based prediction for:
1. Disk Exhaustion Forecast (Dự đoán đầy ổ cứng)
2. Memory Leak Detection (Phát hiện rò rỉ RAM)
3. CPU Saturation Trend (Xu hướng quá tải CPU)
4. Thermal Runaway Warning (Cảnh báo nhiệt độ CPU)

Algorithm: scikit-learn LinearRegression on time-series data.
X-axis: Unix Epoch Timestamps (handles data gaps from power outages).
Y-axis: Metric percentage (0-100%).

Edge Cases Covered:
- Cold Start (< min data points) → reject with message
- Noisy data (R² < 0.3) → report "stable, no risk"
- Negative slope (resource decreasing) → report "safe, infinite TTF"
- Prediction > 100% or < 0% → clamp(0, 100)
- No data in DB → graceful fallback
- Data gaps from power outages → handled by Unix timestamps
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================
MIN_DATA_POINTS = 10          # Minimum records needed for prediction
MIN_TIME_SPAN_MINUTES = 30    # Minimum time span needed (minutes)
FORECAST_HOURS = 24           # How far into the future to predict
FORECAST_POINTS = 50          # Number of predicted data points to generate
R_SQUARED_THRESHOLD = 0.15    # Below this → data too noisy, no reliable prediction

# Thresholds for warnings
DISK_DANGER_PERCENT = 95
MEMORY_DANGER_PERCENT = 90
CPU_DANGER_PERCENT = 90
TEMP_DANGER_CELSIUS = 85


# =============================================================================
# Helper: Fetch raw time-series from DB
# =============================================================================
def _dictfetchall(cursor) -> List[Dict[str, Any]]:
    """Return all rows from a cursor as dicts."""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_metric_timeseries(
    sysname: str,
    table: str,
    value_column: str,
    hours_back: int = 24,
    extra_where: str = "",
    group_column: str = "",
) -> List[Dict[str, Any]]:
    """
    Generic function to fetch time-series data from a metric table.
    Returns list of {time: datetime, value: float}.
    
    Uses raw SQL for performance and flexibility.
    """
    try:
        now = datetime.now()
        start = now - timedelta(hours=hours_back)
        
        group_clause = ""
        if group_column:
            group_clause = f"AND {group_column} = (SELECT {group_column} FROM {table} WHERE sysname = %s {extra_where} ORDER BY time DESC LIMIT 1)"
        
        # Build query with optional group filter
        params = [sysname, start, now]
        if group_column:
            params = [sysname] + params  # extra param for subquery
        
        sql = f"""
            SELECT time, {value_column} as value
            FROM {table}
            WHERE sysname = %s 
              AND time >= %s AND time <= %s
              AND {value_column} IS NOT NULL
              {extra_where}
              {group_clause}
            ORDER BY time ASC
        """
        
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            return _dictfetchall(cursor)
    except Exception as e:
        logger.exception(f"Error fetching timeseries from {table}: {e}")
        return []


# =============================================================================
# Core ML: Linear Regression Prediction
# =============================================================================
def _run_linear_regression(
    data_points: List[Dict[str, Any]],
    metric_name: str,
    danger_threshold: float = 100.0,
    is_percentage: bool = True,
    forecast_hours: int = FORECAST_HOURS,
) -> Dict[str, Any]:
    """
    Run Linear Regression on time-series data and generate forecast.
    
    Args:
        data_points: List of {time: datetime, value: float}
        metric_name: Human-readable name for the metric
        danger_threshold: Value at which alert is triggered
        is_percentage: Whether to clamp values to 0-100
        forecast_hours: How far to predict into the future
    
    Returns:
        Dict with prediction results, trendline, and metadata.
    
    Edge Cases:
        - Too few points → insufficient_data
        - Too short time span → insufficient_data
        - R² too low → stable (no reliable trend)
        - Negative slope → safe (decreasing)
        - Prediction hits threshold → calculate exact TTF
    """
    try:
        import numpy as np
        from sklearn.linear_model import LinearRegression
        from sklearn.metrics import r2_score
    except ImportError:
        return {
            "status": "error",
            "metric": metric_name,
            "message": "Thiếu thư viện ML. Chạy: pip install scikit-learn numpy",
        }
    
    # ── Edge Case 1: Cold Start (insufficient data) ─────────────────────
    if len(data_points) < MIN_DATA_POINTS:
        return {
            "status": "insufficient_data",
            "metric": metric_name,
            "message": f"Chưa đủ dữ liệu lịch sử (có {len(data_points)} điểm, cần tối thiểu {MIN_DATA_POINTS}). AI đang tiếp tục học...",
            "data_points_count": len(data_points),
            "forecast": [],
            "trendline": [],
        }
    
    # Convert to numpy arrays: X = unix timestamps, Y = values
    timestamps = []
    values = []
    for dp in data_points:
        t = dp['time']
        v = dp['value']
        if t is not None and v is not None:
            if isinstance(t, datetime):
                ts = t.timestamp()
            else:
                ts = float(t)
            timestamps.append(ts)
            values.append(float(v))
    
    if len(timestamps) < MIN_DATA_POINTS:
        return {
            "status": "insufficient_data",
            "metric": metric_name,
            "message": f"Dữ liệu hợp lệ không đủ ({len(timestamps)} điểm).",
            "data_points_count": len(timestamps),
            "forecast": [],
            "trendline": [],
        }
    
    # ── Edge Case 5: Time span too short ─────────────────────────────────
    time_span_minutes = (timestamps[-1] - timestamps[0]) / 60.0
    if time_span_minutes < MIN_TIME_SPAN_MINUTES:
        return {
            "status": "insufficient_data",
            "metric": metric_name,
            "message": f"Khoảng thời gian quá ngắn ({time_span_minutes:.0f} phút, cần tối thiểu {MIN_TIME_SPAN_MINUTES} phút).",
            "data_points_count": len(timestamps),
            "forecast": [],
            "trendline": [],
        }
    
    X = np.array(timestamps).reshape(-1, 1)
    Y = np.array(values)
    
    # ── Fit Linear Regression ────────────────────────────────────────────
    model = LinearRegression()
    model.fit(X, Y)
    
    slope = float(model.coef_[0])
    intercept = float(model.intercept_)
    
    # Calculate R² score
    y_pred_train = model.predict(X)
    r_squared = float(r2_score(Y, y_pred_train))
    
    # Current value (latest reading)
    current_value = float(values[-1])
    current_time = datetime.fromtimestamp(timestamps[-1])
    
    # ── Edge Case 2: Noisy data (R² too low) ────────────────────────────
    if r_squared < R_SQUARED_THRESHOLD:
        return {
            "status": "stable",
            "metric": metric_name,
            "message": f"Trạng thái ổn định. Dữ liệu dao động ngẫu nhiên, không phát hiện xu hướng tăng/giảm rõ ràng (R²={r_squared:.3f}).",
            "current_value": round(current_value, 2),
            "r_squared": round(r_squared, 4),
            "slope_per_hour": round(slope * 3600, 4),
            "data_points_count": len(timestamps),
            "forecast": [],
            "trendline": _generate_trendline(model, timestamps, is_percentage),
        }
    
    # ── Edge Case 3: Negative slope (resource decreasing) ────────────────
    slope_per_hour = slope * 3600  # Convert from per-second to per-hour
    
    if slope <= 0:
        return {
            "status": "safe",
            "metric": metric_name,
            "message": f"Xu hướng an toàn (đang giảm {abs(slope_per_hour):.2f}%/giờ). Thời gian sống: ∞ (Vô hạn).",
            "current_value": round(current_value, 2),
            "slope_per_hour": round(slope_per_hour, 4),
            "r_squared": round(r_squared, 4),
            "trend_direction": "decreasing",
            "data_points_count": len(timestamps),
            "time_to_failure": None,
            "failure_time": None,
            "forecast": _generate_forecast(model, timestamps[-1], forecast_hours, is_percentage),
            "trendline": _generate_trendline(model, timestamps, is_percentage),
        }
    
    # ── Slope is positive: Calculate Time To Failure (TTF) ───────────────
    # Solve: danger_threshold = slope * future_ts + intercept
    # future_ts = (danger_threshold - intercept) / slope
    ttf_seconds = None
    failure_time = None
    ttf_human = None
    
    if slope > 0:
        future_ts = (danger_threshold - intercept) / slope
        ttf_seconds = future_ts - timestamps[-1]
        
        if ttf_seconds > 0:
            failure_time = datetime.fromtimestamp(future_ts)
            # Human-readable TTF
            ttf_delta = timedelta(seconds=ttf_seconds)
            days = ttf_delta.days
            hours = ttf_delta.seconds // 3600
            minutes = (ttf_delta.seconds % 3600) // 60
            
            parts = []
            if days > 0:
                parts.append(f"{days} ngày")
            if hours > 0:
                parts.append(f"{hours} giờ")
            if minutes > 0:
                parts.append(f"{minutes} phút")
            ttf_human = " ".join(parts) if parts else "< 1 phút"
        else:
            # Already past threshold
            ttf_seconds = 0
            ttf_human = "ĐÃ VƯỢT NGƯỠNG!"
            failure_time = current_time
    
    # Determine status based on TTF
    if ttf_seconds is not None and ttf_seconds <= 0:
        status = "critical"
        emoji = "🔴"
        message = f"{emoji} NGHIÊM TRỌNG: {metric_name} đã vượt ngưỡng nguy hiểm ({danger_threshold}%)! Giá trị hiện tại: {current_value:.1f}%."
    elif ttf_seconds is not None and ttf_seconds < 3600 * 6:  # < 6 hours
        status = "warning"
        emoji = "⚠️"
        message = f"{emoji} CẢNH BÁO: {metric_name} dự kiến đạt {danger_threshold}% trong {ttf_human}. Tốc độ tăng: {slope_per_hour:.2f}%/giờ."
    elif ttf_seconds is not None and ttf_seconds < 3600 * 48:  # < 48 hours
        status = "caution"
        emoji = "🟡"
        message = f"{emoji} Lưu ý: {metric_name} có xu hướng tăng dần ({slope_per_hour:.2f}%/giờ). Dự kiến đạt {danger_threshold}% trong {ttf_human}."
    else:
        status = "healthy"
        emoji = "✅"
        message = f"{emoji} Sức khỏe tốt. {metric_name} đang tăng chậm ({slope_per_hour:.4f}%/giờ). Không có nguy cơ trong thời gian gần."
    
    return {
        "status": status,
        "metric": metric_name,
        "message": message,
        "current_value": round(current_value, 2),
        "slope_per_hour": round(slope_per_hour, 4),
        "r_squared": round(r_squared, 4),
        "trend_direction": "increasing",
        "data_points_count": len(timestamps),
        "time_to_failure": ttf_human,
        "failure_time": failure_time.isoformat() if failure_time else None,
        "forecast": _generate_forecast(model, timestamps[-1], forecast_hours, is_percentage),
        "trendline": _generate_trendline(model, timestamps, is_percentage),
    }


def _generate_forecast(
    model, last_timestamp: float, hours: int, is_percentage: bool
) -> List[List]:
    """
    Generate future prediction points for chart rendering.
    Returns list of [unix_timestamp_ms, predicted_value].
    
    Edge Case 4: Clamp values to [0, 100] if is_percentage.
    """
    import numpy as np
    
    future_timestamps = np.linspace(
        last_timestamp,
        last_timestamp + hours * 3600,
        FORECAST_POINTS,
    )
    
    predictions = model.predict(future_timestamps.reshape(-1, 1))
    
    result = []
    for ts, val in zip(future_timestamps, predictions):
        clamped = float(val)
        if is_percentage:
            clamped = max(0.0, min(100.0, clamped))
        # ApexCharts expects milliseconds
        result.append([int(ts * 1000), round(clamped, 2)])
    
    return result


def _generate_trendline(
    model, timestamps: list, is_percentage: bool
) -> List[List]:
    """
    Generate trendline points overlaying the historical data.
    Returns list of [unix_timestamp_ms, trend_value].
    """
    import numpy as np
    
    ts_array = np.array(timestamps).reshape(-1, 1)
    trend_values = model.predict(ts_array)
    
    result = []
    for ts, val in zip(timestamps, trend_values):
        clamped = float(val)
        if is_percentage:
            clamped = max(0.0, min(100.0, clamped))
        result.append([int(ts * 1000), round(clamped, 2)])
    
    return result


# =============================================================================
# Public API: Predict All Metrics for a Device
# =============================================================================
def predict_all_metrics(sysname: str, hours_back: int = 24) -> Dict[str, Any]:
    """
    Run predictive analysis on ALL resource types for a given device.
    Returns a comprehensive forecast report.
    
    This is the main entry point called by the API endpoint.
    """
    results = {}
    
    # ── 1. Disk Usage Prediction ─────────────────────────────────────────
    disk_data = _fetch_metric_timeseries(
        sysname=sysname,
        table="disk_usage",
        value_column="percent",
        hours_back=hours_back,
        extra_where="AND mount = '/' AND device_partition NOT LIKE 'tmpfs' AND device_partition NOT LIKE '%%tmpfs%%'",
    )
    results["disk"] = _run_linear_regression(
        data_points=disk_data,
        metric_name="Ổ cứng (Disk Usage /)",
        danger_threshold=DISK_DANGER_PERCENT,
        is_percentage=True,
    )
    
    # ── 2. Memory Usage Prediction ───────────────────────────────────────
    memory_data = _fetch_metric_timeseries(
        sysname=sysname,
        table="memory",
        value_column="percent",
        hours_back=hours_back,
    )
    results["memory"] = _run_linear_regression(
        data_points=memory_data,
        metric_name="Bộ nhớ RAM (Memory)",
        danger_threshold=MEMORY_DANGER_PERCENT,
        is_percentage=True,
    )
    
    # ── 3. CPU Load Prediction (using load_1m as indicator) ──────────────
    # Note: CPU percent fluctuates wildly, load_1m is smoother
    # We normalize load_1m: on a 4-core system, load 4.0 = 100%
    # Since we don't know core count, we use raw cpu_percent average
    cpu_data = _fetch_metric_timeseries(
        sysname=sysname,
        table="cpu_percent",
        value_column="percent",
        hours_back=hours_back,
        extra_where="AND cpu = 'cpu_avg'",
    )
    
    # If cpu_avg doesn't exist, try to get average from all cores
    if not cpu_data or len(cpu_data) < MIN_DATA_POINTS:
        try:
            now = datetime.now()
            start = now - timedelta(hours=hours_back)
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT time, AVG(percent) as value
                    FROM cpu_percent
                    WHERE sysname = %s AND time >= %s AND time <= %s
                      AND percent IS NOT NULL
                    GROUP BY time
                    ORDER BY time ASC
                """, [sysname, start, now])
                cpu_data = _dictfetchall(cursor)
        except Exception as e:
            logger.warning(f"CPU avg query fallback failed: {e}")
            cpu_data = []
    
    results["cpu"] = _run_linear_regression(
        data_points=cpu_data,
        metric_name="CPU Usage",
        danger_threshold=CPU_DANGER_PERCENT,
        is_percentage=True,
    )
    
    # ── 4. Temperature Prediction ────────────────────────────────────────
    temp_data = _fetch_metric_timeseries(
        sysname=sysname,
        table="temperature",
        value_column="cpu_temp",
        hours_back=hours_back,
    )
    results["temperature"] = _run_linear_regression(
        data_points=temp_data,
        metric_name="Nhiệt độ CPU (Temperature)",
        danger_threshold=TEMP_DANGER_CELSIUS,
        is_percentage=False,  # Temperature is in °C, not %
        forecast_hours=12,    # Temperature prediction: 12h ahead
    )
    
    # ── Overall Health Summary ───────────────────────────────────────────
    statuses = [r.get("status", "unknown") for r in results.values()]
    
    if "critical" in statuses:
        overall = "critical"
        overall_message = "🔴 HỆ THỐNG ĐANG GẶP SỰ CỐ NGHIÊM TRỌNG!"
    elif "warning" in statuses:
        overall = "warning"
        overall_message = "⚠️ Phát hiện xu hướng đáng lo ngại, cần can thiệp sớm."
    elif "caution" in statuses:
        overall = "caution"
        overall_message = "🟡 Hệ thống hoạt động bình thường, có một số xu hướng cần theo dõi."
    else:
        overall = "healthy"
        overall_message = "✅ Tất cả chỉ số đều ổn định. Hệ thống khỏe mạnh."
    
    return {
        "ok": True,
        "sysname": sysname,
        "analyzed_at": datetime.now().isoformat(),
        "lookback_hours": hours_back,
        "forecast_hours": FORECAST_HOURS,
        "overall_status": overall,
        "overall_message": overall_message,
        "predictions": results,
    }
