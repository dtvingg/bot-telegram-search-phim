import requests


class ServiceSearchPhim:
    def __init__(self, timeout: int = 10, max_slugs: int = 3):
        self.base_url = "https://ophim1.com/v1/api"
        self.timeout = timeout
        self.headers = {"accept": "application/json"}
        self.prefix_search = "tim-kiem"
        self.prefix_detail = "phim"
        self.max_slugs = max_slugs

    def search(self, query: str) -> list[dict]:
        """Tìm kiếm phim, trả về list metadata cơ bản."""
        print(f"Searching for: {query}")
        url = f"{self.base_url}/{self.prefix_search}"

        try:
            response = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
                params={"keyword": query},
            )
            data = response.json()

            if data.get("status") == "success":
                items = data.get("data", {}).get("items", [])
                return [{"slug": m.get("slug")} for m in items]

        except requests.RequestException as e:
            print("Search error:", e)

        return []

    def get_detail(self, slug: str) -> dict | None:
        """Lấy toàn bộ thông tin chi tiết phim từ API."""
        print(f"Getting detail for: {slug}")
        url = f"{self.base_url}/{self.prefix_detail}/{slug}"

        try:
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            data = response.json()
            print("data", data)

            if data.get("status") == "success":
                item = data.get("data", {}).get("item", {})

                # Rating: ưu tiên IMDB, fallback TMDB
                imdb  = item.get("imdb") or {}
                tmdb  = item.get("tmdb") or {}
                rating = imdb.get("vote_average") or tmdb.get("vote_average")

                # Episodes: gom tất cả server lại
                episodes = []
                for ep_group in item.get("episodes", []):
                    server_name = ep_group.get("server_name", "")
                    for server in ep_group.get("server_data", []):
                        link = server.get("link_m3u8") or server.get("link_embed")
                        if link:
                            episodes.append({
                                "name":        server.get("name"),
                                "filename":    server.get("filename"),
                                "link":        link,
                                "server_name": server_name,
                            })

                return {
                    # Định danh
                    "slug":          item.get("slug"),
                    "name":          item.get("name", slug),
                    "origin_name":   item.get("origin_name", ""),
                    # Thông tin phim
                    "year":          item.get("year"),
                    "quality":       item.get("quality", ""),
                    "lang":          item.get("lang", ""),
                    "time":          item.get("time", ""),
                    "type":          item.get("type", ""),
                    "status":        item.get("status", ""),
                    "episode_current": item.get("episode_current", ""),
                    "episode_total": item.get("episode_total", ""),
                    "view":          item.get("view", 0),
                    # Đánh giá
                    "rating":        round(rating, 1) if rating else None,
                    "imdb_id":       imdb.get("id"),
                    # Cast & Crew
                    "actors":        item.get("actor", []),
                    "directors":     item.get("director", []),
                    # Phân loại
                    "categories":    [c.get("name") for c in item.get("category", [])],
                    "countries":     [c.get("name") for c in item.get("country", [])],
                    # Nội dung
                    "description":   item.get("content", ""),
                    # Link xem
                    "episodes":      episodes,
                }

        except requests.RequestException as e:
            print("Detail error:", e)

        return None

    # Thứ tự ưu tiên chất lượng (index càng nhỏ = ưu tiên càng cao)
    QUALITY_RANK = {
        "4k":       0,
        "2k":       1,
        "fhd":      2,
        "full hd":  2,
        "hd":       3,
        "sd":       4,
        "cam":      5,
    }

    def _quality_rank(self, movie: dict) -> int:
        """Trả về số thứ tự ưu tiên của chất lượng (nhỏ hơn = tốt hơn)."""
        raw = (movie.get("quality") or "").lower().strip()
        for key, rank in self.QUALITY_RANK.items():
            if key in raw:
                return rank
        return 99  # Không xác định → xếp cuối

    def run(self, query: str) -> list[dict] | None:
        """Tìm kiếm + lấy chi tiết, trả về list phim sắp xếp chất lượng cao trước."""
        movies = self.search(query)
        if not movies:
            return None

        results = []
        for movie in movies[:self.max_slugs]:
            detail = self.get_detail(movie["slug"])
            if detail:
                results.append(detail)

        if not results:
            return None

        # Sắp xếp: chất lượng cao lên trước, cùng chất lượng thì rating cao hơn lên trước
        results.sort(key=lambda m: (self._quality_rank(m), -(m.get("rating") or 0)))
        return results