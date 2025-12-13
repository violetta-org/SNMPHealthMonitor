from typing import Any, Dict, Optional


def _is_namedtuple(obj: Any) -> bool:
    return hasattr(obj, "_asdict")


def flatten(value: Any) -> Any:
    """
    Làm phẳng đệ quy các cấu trúc dữ liệu lồng nhau phức tạp thành các kiểu Python đơn giản hơn.

    Hàm này duyệt qua các cấu trúc dữ liệu lồng nhau và chuyển đổi chúng thành các kiểu Python cơ bản
    (dictionary, list, và các giá trị nguyên thủy), giúp việc serialize hoặc xử lý dễ dàng hơn.

    Args:
        value (Any): Giá trị cần làm phẳng, có thể là bất kỳ kiểu nào.

    Returns:
        Any: Biểu diễn đã được làm phẳng của giá trị đầu vào:
            - None vẫn là None
            - NamedTuple được chuyển thành dictionary
            - Dictionary có các giá trị được làm phẳng đệ quy
            - List và tuple có các phần tử được làm phẳng đệ quy
            - Object có __dict__ được chuyển thành dictionary
            - Object không thể chuyển đổi được biểu diễn dưới dạng string
            - Các giá trị khác được trả về như cũ

    Examples:
        >>> flatten(None)
        None
        >>> flatten({'a': 1, 'b': [2, 3]})
        {'a': 1, 'b': [2, 3]}
        >>> from collections import namedtuple
        >>> Point = namedtuple('Point', ['x', 'y'])
        >>> flatten(Point(1, 2))
        {'x': 1, 'y': 2}
    """
    if value is None:
        return None
    if _is_namedtuple(value):
        return {k: flatten(v) for k, v in value._asdict().items()}
    if isinstance(value, dict):
        return {k: flatten(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [flatten(v) for v in value]
    if hasattr(value, "__dict__") and not isinstance(value, (str, bytes)):
        try:
            return {k: flatten(v) for k, v in vars(value).items()}
        except Exception:
            return str(value)
    return value


class Metric:
    """Là lớp đối tượng đại diện cho một điểm dữ liệu
    
    Attributes:
        name: Tên metric (ví dụ: 'cpu.percent', 'network.rx_bytes_total')
        value: Giá trị metric (sẽ được làm phẳng)
        unit: Đơn vị đo lường (ví dụ: '%', 'bytes', 'count')
        type: Loại metric - 'gauge' (giá trị tức thời) hoặc 'counter' (tích lũy)
        labels: Dict các cặp key-value label để nhận diện
        ts: Unix timestamp (giây) khi metric này được thu thập (bắt buộc)
    """
    
    def __init__(
        self,
        name: str,
        value: Any,
        unit: str,
        type: str = "gauge",
        labels: Optional[Dict[str, Any]] = None,
        ts: int = None,
    ):
        if ts is None:
            raise ValueError(f"Metric {name} must have a timestamp (ts)")
        
        self.name = name
        self.value = flatten(value)
        self.unit = unit
        self.type = type
        self.labels = flatten(labels) if labels else {}
        self.ts = ts
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dict for JSON encoding."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "type": self.type,
            "labels": self.labels,
            "ts": self.ts,
        }
    
    def __repr__(self):
        return f"Metric(name={self.name!r}, value={self.value}, type={self.type})"


