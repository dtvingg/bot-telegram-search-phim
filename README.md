# Bot Telegram Tìm Kiếm Phim

Bot Telegram tìm kiếm phim nhanh, hiển thị thông tin chi tiết và link xem trực tiếp.

## Tính năng

- **Tìm kiếm phim** — tra cứu theo tên tiếng Việt hoặc tên gốc
- **Thông tin chi tiết** — năm, chất lượng, ngôn ngữ, thời lượng, rating IMDB/TMDB, đạo diễn, diễn viên, thể loại, mô tả
- **Link xem phim** — link m3u8 trực tiếp, phân trang từng 10 tập
- **Lịch sử tìm kiếm** — lưu theo từng user, tối đa 50 lượt
- **Ủng hộ tác giả** — hiển thị QR bank và thông tin chuyển khoản

## Lệnh bot

| Lệnh | Mô tả |
|------|-------|
| `/search <tên phim>` | Tìm kiếm phim |
| `/history` | Xem lịch sử tìm kiếm (10 lượt gần nhất) |
| `/clearhistory` | Xoá toàn bộ lịch sử |
| `/donate` | Ủng hộ tác giả |
| `/help` | Hướng dẫn sử dụng |

## Yêu cầu

- Docker & Docker Compose **hoặc** Python 3.12+ với [uv](https://docs.astral.sh/uv/)
- Telegram Bot Token (lấy từ [@BotFather](https://t.me/BotFather))

## Chạy bằng Docker (khuyến nghị)

**1. Clone và vào thư mục:**

```bash
git clone <repo-url>
cd bot-telegram-search-phim
```

**2. Tạo file `.env`:**

```bash
cp .env.example .env
```

Mở `.env` và điền token:

```env
BOT_TOKEN=123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**3. Tạo thư mục data:**

```bash
mkdir -p data
```

**4. Build và chạy:**

```bash
docker compose up --build -d
```

**Xem log:**

```bash
docker compose logs -f
```

**Dừng bot:**

```bash
docker compose down
```

## Chạy thủ công (không dùng Docker)

**1. Cài uv:**

```bash
pip install uv
```

**2. Cài dependencies:**

```bash
uv sync
```

**3. Đặt biến môi trường:**

```bash
export BOT_TOKEN=your_token_here
```

**4. Chạy bot:**

```bash
uv run python -m src.bot
```

## Cấu hình

Chỉnh file `src/config.yaml`:

```yaml
search:
  max_slugs: 3    # Số phim tối đa trả về mỗi lần tìm (tăng = chậm hơn)
  timeout: 10     # Timeout gọi API (giây)

history:
  file_path: "data/history.json"
  max_per_user: 50

donate:
  bank_name: "MB Bank"
  account_number: "0123456789"
  account_name: "NGUYEN VAN A"
  qr_image_path: "assets/qr.png"   # Đặt ảnh QR vào src/assets/
  message: "Cảm ơn bạn đã ủng hộ!"
```

## Cấu trúc project

```
bot-telegram-search-phim/
├── src/
│   ├── bot.py                  # Entry point, handlers Telegram
│   ├── service_search_phim.py  # Gọi API ophim1.com
│   ├── history_manager.py      # Lưu/đọc lịch sử (thread-safe)
│   ├── config.yaml             # Cấu hình bot
│   └── assets/
│       └── qr.png              # Ảnh QR donate
├── data/
│   └── history.json            # Lịch sử tìm kiếm (tự tạo khi chạy)
├── Dockerfile
├── docker-compose.yml
├── pyproject.toml
└── .env                        # Biến môi trường (không commit)
```

## Nguồn dữ liệu

Phim được lấy từ API công khai của [OPhim](https://ophim1.com). Kết quả tìm kiếm được sắp xếp theo chất lượng (4K > FHD > HD > SD) và rating.

## Lưu ý khi xem phim

Link phim trả về định dạng **m3u8 (HLS)**. Cần trình phát hỗ trợ:
- **Máy tính:** VLC, IINA, hoặc trình duyệt với extension HLS Player
- **Điện thoại:** VLC Mobile, nPlayer
