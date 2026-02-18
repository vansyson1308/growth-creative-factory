# Growth Creative Factory

**Growth Creative Factory** là một bộ công cụ **local-first** giúp team marketing tạo *creative quảng cáo hàng loạt* nhanh hơn rất nhiều:

- Import hiệu suất quảng cáo (CSV) hoặc **pull từ Google Ads / Meta Ads** (tuỳ chọn)
- Chọn ads kém hiệu quả → tạo biến thể copy (headline/description) theo ràng buộc (ví dụ: 30/90 ký tự)
- Xuất `TSV` để **Figma Plugin** tự nhân bản template thành tối đa **100 frames** và export PNG hàng loạt
- Có **memory log** + ingest results để ghi lại giả thuyết/biến thể/kết quả test (tối ưu dần theo campaign)

> BYO Credentials: Repo này **không chứa secret**. Ai dùng tự cấu hình key/token/credentials của họ.

---

## Demo workflow (siêu nhanh)

1) Pull/Import performance (CSV hoặc connector)  
2) Generate variations (dry-run hoặc live mode với LLM)  
3) Copy `output/figma_variations.tsv`  
4) Mở Figma → chạy plugin → tạo 100 frames từ template  
5) Export PNG hàng loạt → đem đi test ads

---

## Yêu cầu trước khi chạy (Prerequisites)

- **Git**
- **Python 3.10+** (khuyến nghị 3.11)
- (Tuỳ chọn) **Node.js 18+** — chỉ cần nếu bạn muốn build lại Figma plugin từ TypeScript

---

## Quickstart (5 phút, DRY-RUN, không cần key)

### Windows (CMD)
```bat
git clone https://github.com/vansyson1308/growth-creative-factory.git
cd growth-creative-factory

py -m venv .venv
.\.venv\Scripts\activate

python -m pip install -U pip
pip install -r requirements.txt

python -m gcf --version
python -m gcf run --input examples/ads_sample.csv --out output --mode dry
```

### macOS / Linux
```bash
git clone https://github.com/vansyson1308/growth-creative-factory.git
cd growth-creative-factory

python3 -m venv .venv
source .venv/bin/activate

python -m pip install -U pip
pip install -r requirements.txt

python -m gcf --version
python -m gcf run --input examples/ads_sample.csv --out output --mode dry
```

Kết quả tạo ra:
- `output/new_ads.csv`
- `output/figma_variations.tsv` (**UTF-8 no BOM**)
- `output/report.md`

---

## Chạy UI (Streamlit)

```bash
streamlit run app.py
```

App có wizard theo bước (Import → Select → Generate → Export) để marketing không cần biết code vẫn dùng được.

---

## Live mode (tuỳ chọn, có thể tốn phí)

Nếu bạn muốn dùng LLM để “thông minh” hơn (selector/headline/description/checker), tạo file `.env` theo mẫu `.env.example`:

```env
ANTHROPIC_API_KEY=YOUR_KEY_HERE
```

Sau đó chạy (ví dụ):
```bash
python -m gcf run --input examples/ads_sample.csv --out output --mode live
```

> Lưu ý: Live mode sẽ gọi API và có thể tính phí theo token. Repo có guardrails (retry/backoff/caching/budget) tuỳ cấu hình.

---

## Figma Plugin (tạo hàng loạt + export PNG)

### Import plugin
1) Mở Figma  
2) **Plugins → Development → Import plugin from manifest…**  
3) Chọn file: `figma_plugin/manifest.json`

### Chuẩn bị template trong Figma
- Tạo một Frame làm template, ví dụ tên: `AD_TEMPLATE`
- Trong frame, đặt tên các text layer theo mapping bạn dùng:
  - `H1` (headline)
  - `DESC` (description)
  - (Tuỳ chọn) `CTA`, `H2`, ...

### Dùng plugin
- Chạy plugin
- Paste nội dung từ `output/figma_variations.tsv`
- Bấm Generate → plugin tạo tối đa **100 frames** và sắp grid
- Export PNG hàng loạt ngay trong plugin (nếu bật)

### Nếu thiếu `figma_plugin/dist/code.js` (hoặc bạn muốn build lại)
```bash
cd figma_plugin
npm install
npx tsc -p tsconfig.json
```

---

## Input / Output format

### Input CSV
Bạn có thể dùng file CSV bất kỳ miễn là có các cột cần thiết (repo sẽ validate và báo thiếu cột rõ ràng).  
Ví dụ sample: `examples/ads_sample.csv`

### Output TSV cho Figma
File `output/figma_variations.tsv` có header tối thiểu:
- `H1` (headline)
- `DESC` (description)
- `TAG` (angle/tag/experiment label)

---

## Connectors (tuỳ chọn)

Repo hỗ trợ **self-host + BYO credentials** để cộng đồng tự connect account của họ.

### Google Ads (pull performance → CSV theo schema)
```bash
python -m gcf google-ads pull --customer_id <id> --date_range LAST_30_DAYS --out input/ads.csv
```

Hướng dẫn chi tiết: `docs/CONNECT_GOOGLE_ADS.md`

### Meta Ads (pull insights → CSV theo schema)
```bash
python -m gcf meta-ads pull --date_preset last_30d --out input/ads.csv
```

Hướng dẫn chi tiết: `docs/CONNECT_META_ADS.md`

### Google Sheets (handoff tuỳ chọn)
Push output sang Google Sheets (dùng credentials của bạn):
```bash
python -m gcf sheets push --spreadsheet_id <id> --worksheet Variations --input output/figma_variations.tsv
python -m gcf sheets push --spreadsheet_id <id> --worksheet Ads --input output/new_ads.csv
```

Hướng dẫn chi tiết: `docs/CONNECT_GOOGLE_SHEETS.md`

---

## Memory & Learning loop (tuỳ chọn)

Tool có thể ghi log experiment (hypothesis / variants / tag / results) để lần sau generate tốt hơn.

- Memory file: `memory/memory.jsonl`
- Ingest results (ví dụ):
```bash
python -m gcf ingest-results --input results/performance.csv
```

---

## Troubleshooting

### CI fail “Format check: would reformat”
Chạy format trước khi push:
```bash
black .
ruff check . --fix
pytest -q
```

### Anthropic API 529 / overloaded
Đây là lỗi server quá tải. Hãy retry, hoặc giảm số variants / bật cache / chạy lại sau.

### “Thiếu cột” khi import CSV
Repo sẽ báo các cột bắt buộc bị thiếu. Hãy map cột đúng tên hoặc dùng schema unified output từ connectors.

### Figma plugin lỗi font
Plugin sẽ cố load fonts; nếu có node font không load được, nó sẽ báo rõ và skip node thay vì crash.

---

## Cấu trúc thư mục

- `gcf/` — core pipeline, schema, providers, connectors
- `prompts/` — prompt templates (selector/headline/description/checker)
- `figma_plugin/` — plugin TypeScript + UI
- `tests/` — pytest suite
- `docs/` — tài liệu kết nối & hướng dẫn
- `scripts/` — helper scripts (format/run)

---

## Đóng góp (Contributing)

Xem `CONTRIBUTING.md`.  
Trước khi PR, nên chạy:
```bash
black .
ruff check . --fix
pytest -q
```

---

## Bảo mật (Security)

- Không commit `.env`, token, credentials JSON.
- Xem `SECURITY.md` để report vulnerability.

---

## License

MIT — xem `LICENSE`.

---

## Credits

Cảm ơn cộng đồng OSS, và những chia sẻ workflow thực chiến về growth/creative automation đã truyền cảm hứng cho repo này.
