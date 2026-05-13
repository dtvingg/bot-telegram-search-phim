import json
import threading
from datetime import datetime
from pathlib import Path


class HistoryManager:
    """
    Lưu lịch sử tìm kiếm của từng user vào file JSON.
    Thread-safe nhờ Lock.

    Cấu trúc file:
    {
        "123456789": {                        # user_id (str)
            "username": "nguyen_van_a",
            "searches": [
                {
                    "query": "Doraemon",
                    "timestamp": "2024-01-15 20:30:00",
                    "results_count": 3
                },
                ...
            ]
        },
        ...
    }
    """

    def __init__(self, file_path: str = "data/history.json", max_per_user: int = 50):
        self.file_path   = Path(file_path)
        self.max_per_user = max_per_user
        self._lock        = threading.Lock()

        # Tạo thư mục nếu chưa có
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        # Tạo file nếu chưa có
        if not self.file_path.exists():
            self._write({})

    # ─── Internal I/O ─────────────────────────────────────────────────────────

    def _read(self) -> dict:
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _write(self, data: dict) -> None:
        with open(self.file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    # ─── Public API ───────────────────────────────────────────────────────────

    def add(self, user_id: int, username: str, query: str, results_count: int) -> None:
        """Thêm 1 lượt tìm kiếm vào lịch sử của user."""
        uid = str(user_id)
        entry = {
            "query":         query,
            "timestamp":     datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "results_count": results_count,
        }

        with self._lock:
            data = self._read()

            if uid not in data:
                data[uid] = {"username": username, "searches": []}

            # Cập nhật username mới nhất
            data[uid]["username"] = username or data[uid].get("username", "")

            searches = data[uid]["searches"]
            searches.append(entry)

            # Giữ tối đa max_per_user bản ghi gần nhất
            if len(searches) > self.max_per_user:
                data[uid]["searches"] = searches[-self.max_per_user:]

            self._write(data)

    def get(self, user_id: int, limit: int = 10) -> list[dict]:
        """Lấy `limit` lượt tìm kiếm gần nhất của user (mới nhất lên đầu)."""
        uid = str(user_id)
        with self._lock:
            data  = self._read()
            searches = data.get(uid, {}).get("searches", [])
            return list(reversed(searches[-limit:]))

    def clear(self, user_id: int) -> None:
        """Xoá toàn bộ lịch sử của 1 user."""
        uid = str(user_id)
        with self._lock:
            data = self._read()
            if uid in data:
                data[uid]["searches"] = []
                self._write(data)

    def stats(self, user_id: int) -> dict:
        """Thống kê nhanh cho 1 user."""
        uid = str(user_id)
        with self._lock:
            data     = self._read()
            user     = data.get(uid, {})
            searches = user.get("searches", [])

        if not searches:
            return {"total": 0, "top_queries": []}

        # Top từ khoá tìm nhiều nhất
        from collections import Counter
        counter    = Counter(s["query"].lower() for s in searches)
        top_queries = [q for q, _ in counter.most_common(5)]

        return {
            "total":       len(searches),
            "top_queries": top_queries,
            "first_search": searches[0]["timestamp"],
            "last_search":  searches[-1]["timestamp"],
        }