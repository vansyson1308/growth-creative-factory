<div align="center">

# Growth Creative Factory

**Xưởng sản xuất creative mã nguồn mở cho dân performance marketing.**
Dữ liệu quảng cáo → copy do AI viết → ảnh đăng mạng xã hội đúng nhận diện thương hiệu, cho mọi vị trí hiển thị, hàng loạt.

[English](README.md) · [Tiếng Việt](README.vi.md)

<img src="docs/assets/showcase-grid.jpg" alt="Sáu mẫu quảng cáo của sáu thương hiệu giả định" width="100%">

<sub>Toàn bộ ảnh trên được render bởi chính repo này, chạy offline, từ vài dòng copy. Các thương hiệu đều là giả định.</sub>

</div>

---

## Vì sao cần công cụ này

Creative là đòn bẩy lớn nhất còn lại của quảng cáo mạng xã hội — nhưng lại là khâu chậm nhất.
Mỗi biến thể cần copywriter, designer, rồi resize cho từng vị trí đăng, nên đa số team chỉ test
được vài mẫu mỗi tuần.

Growth Creative Factory gói cả vòng lặp đó vào một lệnh:

1. **Tìm ad đang yếu** — import hiệu suất (CSV, Google Ads, Meta Ads), lọc theo CTR / CPA / ROAS.
2. **Viết copy tốt hơn** — Claude (hoặc copywriter offline có sẵn) chẩn đoán nguyên nhân, viết
   headline/description theo 5 góc tiếp cận, sau đó checker + bộ lọc chính sách loại bỏ nội dung vi phạm.
3. **Ra ảnh, không chỉ ra bảng tính** — mọi biến thể được render thành PNG sẵn sàng upload cho
   Feed 1:1, Feed 4:5, Stories/Reels 9:16, Link 1.91:1 và 16:9, theo brand kit của bạn.
4. **Học từ kết quả** — kết quả test quay lại memory log để vòng sau tránh các góc đã thua.

## Tính năng chính

| | |
|---|---|
| 🎨 **Creative engine** | 6 template thiết kế × 5 kích thước, brand kit, tự căn cỡ chữ, vùng an toàn cho Stories, dùng ảnh sản phẩm hoặc art tự sinh. Thuần Python (Pillow) — không cần trình duyệt, không cần Figma. |
| ✍️ **Copy đúng chuẩn** | Giới hạn ký tự (mặc định 30/90), cấm chữ IN HOA toàn bộ, blocklist chính sách ("cam kết", "tuyệt đối", "#1", "100%"…), checker AI, loại trùng lặp và đảm bảo đa dạng góc tiếp cận. |
| 🌏 **Tiếng Việt chuẩn** | Font OFL nhúng sẵn, hiển thị đầy đủ dấu tiếng Việt; copy, CTA và badge tự nhận ngôn ngữ. |
| 🧪 **Chạy thử miễn phí** | Chế độ `dry` dùng copywriter offline hiểu ngữ cảnh sản phẩm — không cần API key, không tốn phí. |
| 🔌 **Kết nối** | Kéo dữ liệu Google Ads / Meta Ads, đẩy sang Google Sheets, plugin Figma cho layout tuỳ biến. |
| 🧭 **An toàn chi phí** | Giới hạn số lần gọi API, retry có backoff, cache, xử lý refusal, kiểm tra cấu hình chặt chẽ. |
| 🖥️ **3 cách dùng** | CLI, ứng dụng Streamlit (Creative Studio + Ads Wizard) và Python API. |

## Bằng chứng, không chỉ lời hứa

Mọi ảnh trong phần này đều do chính repo tạo ra, không phải ảnh dựng bằng công cụ thiết kế.
Chú thích mỗi ảnh ghi lệnh đã tạo ra nó. Cả bộ ảnh được tạo lại bằng **`gcf demo`**
(mã nguồn: [`gcf/demo.py`](gcf/demo.py), dữ liệu đầu vào trong [`examples/`](examples/)), mất
khoảng 40 giây trên laptop, chạy offline, không cần API key. CI chạy lệnh này ở mỗi lần push và
đính kèm kết quả vào bản build. Thời gian chạy, phiên bản và copy được sinh ra đều lưu trong
[`docs/demo/demo.json`](docs/demo/demo.json).

### 1 · Quảng cáo kém hiệu quả vào, chẩn đoán và creative mới ra

`gcf run --input examples/demo_ads.csv --mode dry`: tool lọc các quảng cáo yếu theo CTR, CPA và
ROAS, chẩn đoán nguyên nhân bằng chính số liệu của từng quảng cáo, viết copy mới rồi kiểm duyệt,
và render mỗi biến thể thành ảnh theo brand kit của nhà quảng cáo đó.

<img src="docs/demo/01-before-after.jpg" alt="Quảng cáo kém hiệu quả, chẩn đoán và creative mới" width="100%">

### 2 · Một lần chạy, 75 ảnh khác nhau

<img src="docs/demo/02-one-run-at-scale.jpg" alt="75 creative từ một lần chạy" width="100%">

### 3 · App chạy thật, quay trực tiếp

<img src="docs/demo/08-studio-app.gif" alt="Quay màn hình Creative Studio" width="100%">

### 4 · Một brief thành cả tuần bài đăng

<img src="docs/demo/04-brief-to-posts-vi.jpg" alt="Sáu bài đăng tiếng Việt từ một brief" width="100%">

<img src="docs/demo/03-brief-to-posts-en.jpg" alt="Six English posts from one brief" width="100%">

### 5 · Thương hiệu của bạn, logo của bạn

<img src="docs/demo/05-one-copy-any-brand.jpg" alt="Cùng một copy trên sáu brand kit" width="100%">

### 6 · Mọi vị trí hiển thị từ một dòng copy

<img src="docs/demo/06-every-placement.jpg" alt="Một creative trên mọi kích thước" width="100%">

### 7 · Trang duyệt ảnh cho cả team

<img src="docs/demo/07-review-gallery.jpg" alt="Trang gallery HTML để duyệt ảnh" width="100%">

> **Về chế độ dry.** Các ảnh trên dùng copywriter offline để ai cũng tái tạo được miễn phí.
> Copy của nó dựa trên mẫu câu và cố ý không bịa thông tin (không có số lượt đánh giá, điểm sao
> hay cam kết giao hàng giả). Chế độ live đưa cùng pipeline này qua Claude để có copy sắc nét
> và cụ thể hơn.

## Bắt đầu nhanh (2 phút, không cần API key)

```bash
git clone https://github.com/vansyson1308/growth-creative-factory.git
cd growth-creative-factory
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[ui]"                                   # hoặc: pip install -r requirements.txt
```

**1 · Từ dữ liệu quảng cáo ra creative**

```bash
gcf run --input examples/ads_sample.csv --mode dry
# mở output/gallery.html bằng trình duyệt để duyệt toàn bộ ảnh
```

**2 · Từ brief sản phẩm ra cả tuần bài đăng**

```bash
gcf create --product "Cà phê Arabica Cầu Đất" \
  --audience "dân văn phòng" --offer "Giảm 25% tuần này" \
  --benefit "Hương thơm đậm đà" --benefit "Rang mới mỗi tuần" \
  --n 8 --brand noir --formats square,story
```

**3 · Từ bảng copy bất kỳ (hoặc file TSV cho Figma) ra ảnh**

```bash
gcf render --input examples/posts_sample.csv --formats all --brand verde
```

**4 · Giao diện web**

```bash
streamlit run app.py
```

Tab **🎨 Creative Studio**: nhập brief → sinh bài → render → tải ZIP.
Tab **🧙 Ads Wizard**: upload CSV → chọn ad yếu → sinh biến thể → tải file + render ảnh.

## Template & kích thước

<img src="docs/assets/templates.jpg" alt="Cùng một copy trên sáu template" width="100%">

| Template | Phù hợp |
|---|---|
| `bold` | Quảng cáo feed cần gây chú ý, ra mắt sản phẩm |
| `editorial` | Cao cấp, thời trang, lifestyle, B2B |
| `split` | Kể chuyện sản phẩm, thương mại điện tử |
| `glass` | Công nghệ, SaaS, app, làm đẹp |
| `promo` | Sale, coupon, mua 1 tặng 1, sự kiện mùa |
| `photo` | Ảnh lifestyle, du lịch, ẩm thực |

| Format | Kích thước | Vị trí |
|---|---|---|
| `square` | 1080×1080 | Feed Facebook & Instagram, carousel |
| `portrait` | 1080×1350 | Feed 4:5 |
| `story` | 1080×1920 | Stories, Reels, TikTok (có vùng an toàn trên/dưới) |
| `landscape` | 1200×628 | Link ads Facebook, LinkedIn, Google Display |
| `wide` | 1600×900 | X/Twitter, thumbnail YouTube, slide |

## Brand kit

Có sẵn 6 preset (`gcf brands`). Với thương hiệu của bạn: sao chép
[`examples/brand_kit.yaml`](examples/brand_kit.yaml), chỉnh màu, logo, font rồi truyền
`--brand duong/dan/brand_kit.yaml` (hoặc đặt `render.brand` trong `config.yaml`).

## Chế độ live (Claude)

```bash
cp .env.example .env     # điền ANTHROPIC_API_KEY
gcf run --input input/ads.csv --mode live
```

Mặc định trong `config.yaml`: model `claude-opus-5`, `effort: low` (copy ngắn không cần suy luận sâu),
fallback khi bị từ chối, giới hạn số lần gọi mỗi lượt chạy, retry và cache SQLite.

## Kết quả mỗi lần chạy

| File | Nội dung |
|---|---|
| `output/creatives/<format>/*.png` | Ảnh sẵn sàng upload + `manifest.csv` |
| `output/gallery.html` | Trang duyệt ảnh có lọc theo format/template, chạy offline |
| `output/contact_sheet.png` | Ảnh tổng quan để gửi nhanh cho team |
| `output/new_ads.csv` | Mọi tổ hợp headline × description, tag không trùng |
| `output/figma_variations.tsv` | Dán vào plugin Figma (UTF-8, không BOM) |
| `output/handoff.csv` | Bảng duyệt có cột `status` / `notes` |
| `output/report.md` | Chẩn đoán, chiến lược và thống kê từng ad |

## Kết nối & Figma

- [Google Ads](docs/CONNECT_GOOGLE_ADS.md) · [Meta Ads](docs/CONNECT_META_ADS.md) · [Google Sheets](docs/CONNECT_GOOGLE_SHEETS.md)
- Plugin Figma: import `figma_plugin/manifest.json`, đặt tên text layer `H1` / `DESC`, dán nội dung
  `output/figma_variations.tsv` → plugin nhân bản tối đa 100 frame và export PNG.

## Phát triển

```bash
pip install -e ".[all,dev]"
black . && ruff check . && pytest -q
```

## Giấy phép

Mã nguồn: MIT ([LICENSE](LICENSE)). Font nhúng (Be Vietnam Pro, Playfair Display): SIL Open Font License.
