# Connect Google Sheets (Optional)

This project supports **optional** Google Sheets handoff.
If you skip this setup, local CSV/TSV files continue to work.

## 1) Create a Service Account
1. Open Google Cloud Console.
2. Create/select a project.
3. Enable **Google Sheets API** and **Google Drive API**.
4. Create a **Service Account**.
5. Create a JSON key and download it (keep it private).

## 2) Share the target Sheet
Open your Google Sheet and share it with the service-account email (Editor access).

## 3) Configure credentials path
Use either environment variable:

```bash
export GCF_GOOGLE_CREDS_JSON=/absolute/path/to/service-account.json
# or
export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
```

## 4) Test and push via CLI
```bash
python -m gcf sheets push --spreadsheet_id <SHEET_ID> --worksheet Variations --input output/figma_variations.tsv
python -m gcf sheets push --spreadsheet_id <SHEET_ID> --worksheet Ads --input output/new_ads.csv
```

## 5) Streamlit usage
Open the **Handoff** tab and input:
- Spreadsheet ID
- Worksheet names

Then click:
- **Push TSV to Google Sheets**
- **Push CSV to Google Sheets**

If credentials are missing, the app shows setup instructions and continues to support local files.
