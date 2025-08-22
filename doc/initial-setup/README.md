# Initial Setup — Standardized Filenames & S3 Layout

This guide standardizes input/output names and explains how to run the pipeline with **zero arguments**.

## 📁 S3 Keys (Standard)

**Inputs**
- CSV (daily positions): `source/positions-YYYY-MM-DD.csv`  
  _Example:_ `source/positions-2025-08-21.csv`
- Excel template: `source/portfolio-template.xlsx`

**Outputs**
- Excel (updated): `output/portfolio-updated-YYYYMMDD-HHMMSS.xlsx`  
- Run report (JSON): `output/reports/YYYYMMDD-HHMMSS-report.json`

## 🔁 Auto-Detection (No Args Needed)

If you invoke the Lambda **without any payload**, it will:
1) Pick the **latest** CSV matching `source/positions-*.csv`  
2) Use the template at `source/portfolio-template.xlsx`  
3) Write a timestamped output in `output/`

## 🧭 Local Repo Convention (Optional)

```text
aws-nasmatchstockprofile-mcp/
  data/
    positions-2025-08-21.csv
    portfolio-template.xlsx
```
When ready, upload these to the bucket from your CDK outputs using the standardized S3 keys above.

## 🚀 Example Commands

Upload files:
```bash
aws s3 cp ./data/portfolio-template.xlsx s3://<Bucket>/source/portfolio-template.xlsx
aws s3 cp ./data/positions-2025-08-21.csv s3://<Bucket>/source/positions-2025-08-21.csv
```

Invoke (no args):
```bash
aws lambda invoke   --function-name <ExcelProcessorFnName>   --cli-binary-format raw-in-base64-out   --payload '{}'   /tmp/out.json && cat /tmp/out.json
```

Fetch artifacts:
```bash
BUCKET=$(jq -r .bucket /tmp/out.json)
REPORT=$(jq -r .report_key /tmp/out.json)
OUTKEY=$(jq -r .output_key /tmp/out.json)

aws s3 cp "s3://$BUCKET/$REPORT" ./run-report.json && cat run-report.json
aws s3 cp "s3://$BUCKET/$OUTKEY" ./portfolio-updated.xlsx
```
