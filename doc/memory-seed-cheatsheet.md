# Memory Seed & Master Prompt — aws-nasmatchstockprofile-mcp

This document is for re-initializing ChatGPT in a new chat with the full project context.

---

## 🚀 Quick Bootstrapping Snippet

When opening a new chat, paste this (replace with your repo link):

```
Please refer to my repo: https://github.com/aburmd/aws-nasmatchstockprofile-mcp

TL;DR seed: aws-nasmatchstockprofile-mcp updates Excel portfolio from Fidelity CSV, with standardized S3 keys (positions-YYYY-MM-DD.csv, portfolio-template.xlsx, etc.), AWS CDK infra, handler.py + on_message.py Lambdas, and RunReport outputs. Docs are under /docs.
```

This anchors ChatGPT to both the repo + memory seed.

---

## 📌 TL;DR (Memory Seed)

- Project: **aws-nasmatchstockprofile-mcp**
- Updates Excel portfolio template from Fidelity positions CSV
- **S3 Standard Keys:**
  - CSV: `source/positions-YYYY-MM-DD.csv`
  - Template: `source/portfolio-template.xlsx`
  - Output Excel: `output/portfolio-updated-YYYYMMDD-HHMMSS.xlsx`
  - RunReport JSON: `output/reports/YYYYMMDD-HHMMSS-report.json`
- **Infra via CDK:** S3, DynamoDB, Lambda (handler.py), WebSocket (on_message.py)
- **Lambda Logic:** parse CSV → map AccountName → Excel headers → write Qty row24, Cost row39 → RunReport JSON + sheet
- **Docs:** `SETUP.md`, `Prerequisites-And-Setup-Guide.pdf`, `ExcelProcessorSetup.pdf`, `initial-setup/README.md`

---

## 📖 Full Master Prompt

1. **Business Requirement**
   - Upload Fidelity positions CSV (daily)
   - Use Excel template
   - Update rows 24 & 39 per ticker sheet
   - Match CSV AccountName → Excel header (env map or DynamoDB)
   - Generate Excel + RunReport JSON + RunReport sheet

2. **Standard Filenames**
   - CSV: `source/positions-YYYY-MM-DD.csv`
   - Template: `source/portfolio-template.xlsx`
   - Output: `output/portfolio-updated-YYYYMMDD-HHMMSS.xlsx`
   - Report: `output/reports/YYYYMMDD-HHMMSS-report.json`

3. **Architecture**
   - AWS CDK infra: S3, DDB (MappingOverrides, WsConnections), Lambda, WebSocket API
   - IAM roles least privilege
   - Costs minimal

4. **Python Lambdas**
   - `handler.py`: parse CSV, map accounts, write Qty/Cost, generate report
   - `on_message.py`: MCP tool `process_excel`, defaults apply, WebSocket integration

5. **CDK Env Config**
   ```ts
   environment: {
     BUCKET_NAME: this.bucket.bucketName,
     MAPPING_TABLE: this.mappingTable.tableName,
     SOURCE_PREFIX: 'source/',
     OUTPUT_PREFIX: 'output/',
     DEFAULT_DATASET_ID: 'default',
     DEFAULT_CSV_PREFIX: 'positions-',
     TEMPLATE_KEY: 'source/portfolio-template.xlsx',
     COST_MODE: 'total_basis',
     ROW_QTY: '24',
     ROW_COST: '39',
     ACCOUNT_NAME_MAP_JSON: JSON.stringify({
       "BrokerageLink": "401K",
       "BrokerageLink Roth": "401 ROTH",
       "Health Savings Account": "HSA",
       "ROTH IRA (after-tax Mega BackDoor Roth)": "ROTH IRA1",
       "INDIVIDUAL-Margin": "Brokerage"
     }),
   }
   ```

6. **Docs**
   - `docs/Prerequisites-And-Setup-Guide.pdf`
   - `docs/SETUP.md`
   - `docs/ExcelProcessorSetup.pdf`
   - `docs/initial-setup/README.md`
   - `docs/README.md`

---

💡 Store this file under `docs/memory-seed-cheatsheet.md` so you always have a quick way to reload context.
