"""
Predictive AIOps — API Endpoints for ML-based resource forecasting.

Endpoints:
- GET /api/ml/predict/{sysname}       → Full prediction report (all metrics)
- GET /api/ml/predict/{sysname}/{metric} → Single metric prediction

Used by the frontend Dashboard to render prediction charts and alerts.
"""
import logging
from ninja import Router
from .ml_services import predict_all_metrics

logger = logging.getLogger(__name__)

ml_router = Router(tags=["ml-prediction"])


@ml_router.get("/predict/{sysname}")
def predict_all(request, sysname: str, hours_back: int = 24):
    """
    Run predictive analysis on ALL resource types for a device.
    
    Query Params:
        hours_back (int): How many hours of historical data to analyze. Default: 24.
    
    Returns comprehensive forecast for: Disk, Memory, CPU, Temperature.
    """
    try:
        # Clamp hours_back to reasonable range
        hours_back = max(1, min(168, hours_back))  # 1h to 7 days
        
        result = predict_all_metrics(sysname, hours_back=hours_back)
        return result
    except Exception as e:
        logger.exception(f"Prediction error for {sysname}: {e}")
        return {
            "ok": False,
            "error": f"Lỗi khi chạy phân tích dự đoán: {str(e)[:300]}",
        }


@ml_router.get("/predict/{sysname}/{metric}")
def predict_single(request, sysname: str, metric: str, hours_back: int = 24):
    """
    Run predictive analysis on a SINGLE metric type.
    
    Path Params:
        metric: One of 'disk', 'memory', 'cpu', 'temperature'
    
    Query Params:
        hours_back (int): Historical data window. Default: 24.
    """
    valid_metrics = ['disk', 'memory', 'cpu', 'temperature']
    
    if metric not in valid_metrics:
        return {
            "ok": False,
            "error": f"Metric không hợp lệ: '{metric}'. Chọn một trong: {', '.join(valid_metrics)}",
        }
    
    try:
        hours_back = max(1, min(168, hours_back))
        full_result = predict_all_metrics(sysname, hours_back=hours_back)
        
        if full_result.get("ok") and "predictions" in full_result:
            single = full_result["predictions"].get(metric, {})
            return {
                "ok": True,
                "sysname": sysname,
                "metric": metric,
                "analyzed_at": full_result.get("analyzed_at"),
                "prediction": single,
            }
        
        return full_result  # Pass through error
    except Exception as e:
        logger.exception(f"Single prediction error: {e}")
        return {
            "ok": False,
            "error": f"Lỗi phân tích: {str(e)[:300]}",
        }
