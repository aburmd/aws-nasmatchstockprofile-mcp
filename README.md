# Welcome to your CDK TypeScript project

This is a blank project for CDK development with TypeScript.

The `cdk.json` file tells the CDK Toolkit how to execute your app.

## Useful commands

* `npm run build`   compile typescript to js
* `npm run watch`   watch for changes and compile
* `npm run test`    perform the jest unit tests
* `npx cdk deploy`  deploy this stack to your default AWS account/region
* `npx cdk diff`    compare deployed stack with current state
* `npx cdk synth`   emits the synthesized CloudFormation template


aws-nasmatchstockprofile-mcp/
│── cdk/                          # AWS CDK Infrastructure (TypeScript)
│   ├── bin/
│   │   └── aws-nasmatchstockprofile-mcp.ts   # CDK entry point
│   ├── lib/
│   │   └── aws-nasmatchstockprofile-mcp-stack.ts  # Main stack
│   ├── package.json
│   ├── cdk.json
│   └── tsconfig.json
│
│── src/                          # Python Runtime (MCP + AI Agent)
│   ├── mcp_server/
│   │   ├── __init__.py
│   │   ├── main.py               # MCP server entry
│   │   ├── excel_handler.py      # Logic for Excel updates
│   │   ├── data_extractor.py     # Logic for parsing website Excel
│   │   └── config.py             # Configurations (e.g. S3 bucket, env vars)
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # AI agent orchestration
│   │   └── prompts.py            # System prompts, reasoning templates
│   │
│   ├── tests/
│   │   └── test_excel_handler.py
│   │
│   └── requirements.txt
│
│── .gitignore
│── README.md




git remote set-url origin https://aburmd@github.com/aburmd/aws-nasmatchstockprofile-mcp.git

ssh-keygen -t ed25519 -C "aburmd@gmail.com"

cat ~/.ssh/id_ed25519.pub

Copy the output → Go to GitHub → Settings → SSH and GPG keys → New SSH key → Paste.

git remote remove origin
git remote add origin git@github.com:aburmd/aws-nasmatchstockprofile-mcp.git

ssh -T git@github.com

You should see: "Hi aburmd! You've successfully authenticated."

git push -u origin main




Here’s a single, copy-pasteable **master prompt** you can give to your code assistant to scaffold the entire repo. It bakes in every requirement: **CDK in TypeScript**, **all runtime in Python**, **API Gateway WebSocket for MCP-style tools**, and **Step Functions + ECS Fargate** for ETL.

---

# 🔧 MASTER PROMPT (copy–paste below this line)

You are an expert AWS/CDK solution engineer and senior Python backend developer.
Generate a production-ready Git repository that implements the following, with **all Infrastructure as Code in TypeScript (CDK v2)** and **all runtime code in Python 3.11**.

## High-Level Goal

* Build an **MCP-style tool endpoint** over **API Gateway WebSocket** so any AI agent can call tools like:

  * `mapping.propose` (Bedrock → Claude; column mapping with confidences)
  * `mapping.apply` (DynamoDB upserts)
  * `excel.replace_table` (S3 + openpyxl; writes a table into a target sheet of an Excel template)
* Build a daily **deterministic ETL** that:

  * Reads `raw/source.xlsx` from S3
  * Normalizes to CSV/Parquet (`staging/`)
  * Publishes a curated `master.xlsx` to `curated/` using an Excel template
* Orchestration via **Step Functions** running an **ECS Fargate** task (Python container) for heavy ETL steps.
* All configs/versioned artifacts live in S3 (`config/`, `raw/`, `staging/`, `curated/`).

## Repository Layout (create these paths & files)

```
aws-excel-mcp/
  README.md
  .gitignore
  package.json
  cdk.json
  tsconfig.json
  bin/app.ts
  lib/
    kms-stack.ts
    storage-stack.ts
    ecr-stack.ts
    network-stack.ts
    ecs-runner-stack.ts
    ws-mcp-stack.ts
    stepfn-stack.ts
    events-stack.ts
  containers/
    excel-runner/
      Dockerfile
      app/handler.py
  runtime/
    mcp_router/handler.py
    mapping_propose/handler.py
    mapping_apply/handler.py
    excel_replace/
      handler.py
      requirements.txt
  s3_bootstrap/config/
    mapping.yaml
    master_template.xlsx   # put a placeholder binary or describe in README to upload
  .github/workflows/cdk-deploy.yml
```

## Core Requirements

### Infrastructure (CDK TypeScript)

* **KMS** CMK (`alias/excel-pipeline-kms`) for S3 + DynamoDB encryption.
* **S3** bucket (versioned, KMS-encrypted) with prefixes: `raw/`, `staging/`, `curated/`, `config/`.
* **DynamoDB**:

  * `MappingOverrides` (PK `dataset_id` STRING, SK `source_col` STRING).
  * `WsConnections` (PK `connection_id` STRING) for WebSocket connection management.
* **API Gateway WebSocket**:

  * Stage `prod`, routes: `$connect`, `$disconnect`, `$default`, plus explicit routes `mapping.propose`, `mapping.apply`, `excel.replace_table`.
  * **Router Lambda (Python)** handles connect/disconnect/default and dispatches to tool Lambdas; responds over `@connections` API.
* **Tool Lambdas (Python)**:

  * `mapping_propose`: calls **Amazon Bedrock** (Claude 3.5 Sonnet model id `anthropic.claude-3-5-sonnet-20240620-v1:0`). Input: `source_cols[]`, `canonical_cols[]`. Output: JSON array `[{from,to,confidence}]`. Return **strict JSON** only.
  * `mapping_apply`: upserts items into `MappingOverrides`.
  * `excel_replace`: loads `config/master_template.xlsx` from S3, writes tabular data to given `sheet`/`start_cell` with **openpyxl**, and saves to `curated/master.xlsx`.
* **VPC** with public + private subnets; VPC endpoints for S3 (Gateway) and Bedrock Runtime (Interface).
* **ECR** repository for the ETL container: `excel-runner`.
* **ECS Fargate**:

  * Cluster + TaskDefinition (1 vCPU/2GB) to run `containers/excel-runner`.
* **Step Functions** state machine:

  1. `Transform` → run ECS task with args to read `raw/source.xlsx`, normalize to `staging/orders.parquet` + `staging/orders.csv`.
  2. `ProposeMapping` → call `mapping_propose` Lambda.
  3. `ApplyMapping` → call `mapping_apply` Lambda.
  4. `Publish` → run ECS task to create/overwrite `staging/master_draft.xlsx` and promote to `curated/master.xlsx` via template.
* **EventBridge** schedule: daily 06:05 AM PT (cron hour 13 UTC), triggers the state machine.
* **IAM** least privilege:

  * Router: `execute-api:ManageConnections`, `lambda:InvokeFunction` for tool Lambdas, RW on `WsConnections`.
  * Tool Lambdas: scoped S3, DDB; Bedrock invoke for mapping\_propose.
  * ECS task role: scoped S3 RW.
* Use **`@aws-cdk/aws-apigatewayv2-alpha`** and **`@aws-cdk/aws-apigatewayv2-integrations-alpha`** for WebSocket + Lambda integration.
* Use **`@aws-cdk/aws-lambda-python-alpha`** `PythonFunction` to bundle Python Lambdas and `requirements.txt` for `excel_replace`.

### Runtime Code (Python 3.11)

* **Router Lambda**:

  * On `$connect`: store `connection_id` in DDB, send handshake JSON `{ "mcp": "hello", "tools": ["mapping.propose","mapping.apply","excel.replace_table"] }`.
  * On `$disconnect`: delete `connection_id`.
  * On `$default` or explicit tool route: parse body JSON; figure out tool name (either routeKey or `body.tool`); invoke the right tool Lambda synchronously; respond to client with `{ ok: true, tool, result }`.
* **mapping\_propose Lambda**:

  * Prompt template to **strictly** return JSON array; parse LLM output robustly; if parse fails, return `[]`.
* **mapping\_apply Lambda**:

  * Input: `{ "dataset_id": "orders_v1", "mapping": [{from,to,confidence}] }`. Upsert to DDB; return count.
* **excel\_replace Lambda**:

  * Input: `{template_key, out_key, sheet, start_cell, data:[{...}]}`.
  * Use openpyxl to clear a reasonable range, write headers + rows, save to S3.
* **ECS runner container** (`excel-runner`):

  * CLI with `--op transform` and `--op publish`.
  * `transform`: read Excel from `raw/`, apply `mapping.yaml` rules (rename/dtypes/filters/dedupe), write Parquet + CSV to `staging/`.
  * `publish`: read CSV + template from S3, write to target sheet/cell, put draft to `staging/master_draft.xlsx` and final to `curated/master.xlsx`.

### Config Files

* `s3_bootstrap/config/mapping.yaml` (sample):

  ```yaml
  dataset_id: "orders_v1"
  source:
    sheet: "Export_Orders"
    sheets:
      - name: "Export_Orders"
        rename:
          "Order Id": order_id
          "Customer Name": customer
          "Order Date": order_date
          "Total": total_amount
        dtypes:
          order_date: datetime
          total_amount: float
        dedupe_keys: [order_id]
  targets:
    - sheet: "Raw_Orders"
      mode: replace_table
  ai:
    min_confidence_auto_apply: 0.85
  ```
* Put a placeholder `master_template.xlsx` (or document that the user should upload theirs).

### Dockerfile (Python)

* `containers/excel-runner/Dockerfile`: based on `python:3.11-slim`; install `pandas`, `openpyxl`, `pyarrow`, `boto3`, `pyyaml`.

### GitHub Actions (optional)

* `cdk-deploy.yml` that builds CDK, synthesizes, and deploys (OIDC role assumed via secrets).

## Non-Functional Requirements

* Clear, defensive error handling (no crashes on malformed JSON or empty datasets).
* Logging with useful context: request IDs, S3 keys, row counts, confidence stats.
* Idempotent publishes (only promote to `curated/` after successful run).
* Versioning: rely on S3 versioning for rollbacks.
* Security: least-privilege IAM, KMS at rest, private VPC traffic to Bedrock/S3 where possible.

## README.md (include)

* High-level architecture diagram (ASCII ok).
* Setup steps:

  1. `npm install`, `cdk bootstrap`
  2. `cdk deploy Kms Storage Ecr Net`
  3. Build & push `excel-runner` image to ECR
  4. `cdk deploy EcsRunner WsMcp StepFn Events`
  5. Upload `s3_bootstrap/config/*` and a sample `raw/source.xlsx`
* How to test WebSocket with `wscat`:

  ```
  wscat -c wss://<api-id>.execute-api.<region>.amazonaws.com/prod
  > {"tool":"mapping.propose","source_cols":["Order Id","Cust Name"],"canonical_cols":["order_id","customer"]}
  ```
* How to start a manual Step Functions execution and where outputs land in S3.
* Cost notes (API GW WS pay-per-message; no ALB).

## Acceptance Criteria

1. `cdk synth` and `cdk deploy` succeed with no manual edits beyond region/account.
2. WebSocket connection succeeds; `$connect` returns tool list; calling `mapping.propose` returns a JSON array (mockable if Bedrock isn’t enabled).
3. Running the state machine processes a sample `raw/source.xlsx` into `staging/*.parquet/.csv` and publishes `curated/master.xlsx`.
4. `excel.replace_table` writes to a *hidden* or staging sheet without corrupting formulas in the template (document that the visible sheets reference `Raw_Orders`).
5. IAM policies are restricted to necessary resources only.

## Coding Standards

* Python: 3.11, type hints where reasonable, small functions, explicit returns, PEP8.
* CDK TS: clear stack boundaries, export key ARNs/URLs via stack class properties, no hardcoded ARNs.
* Use environment variables for Bucket name, DDB table, Model ID.
* Tool Lambdas return **strict JSON**; router always wraps in `{ok, tool, result}`.

## Bonus (if time allows)

* Add a `sfn.start` tool (Lambda) so agents can kick the batch via WebSocket.
* Step Functions choice state to require human approval if any mapping confidence < 0.85.
* API GW authorizer (Cognito or IAM) for WebSocket.

**Deliverables**: fully generated repo tree with all files populated per above, ready to commit and deploy. Do not omit any file listed. Print the final repository tree and any post-deploy instructions at the end.

# 🔧 END MASTER PROMPT

---

Want me to tailor the sample `mapping.yaml` to your exact column names? If you share a dummy `source.xlsx` header row and target sheet name, I’ll plug them in.


mkdir aws-nasmatchstockprofile-mcp
cd aws-nasmatchstockprofile-mcp

# Initialize CDK with TypeScript
cdk init app --language typescript


install cdk

node -v
npm -v

If not installed, grab it via Node.js official site
 or Homebrew:
brew install node

npm install -g aws-cdk

cdk bootstrap aws://654654547262/us-east-1
cdk deploy


npm run build

# Deploy core data plane first
cdk deploy BaseInfra

# Deploy networking + ECS runner
cdk deploy Net EcsRunner

# Deploy WebSocket + Lambdas
cdk deploy WsMcp

# Deploy Step Functions + schedule
cdk deploy StepFn Events





-----------------------------------------------------------------------------------------------

Got it 👍 — let’s walk through **step by step** so you can learn how to approach this with **MCP (Model Context Protocol)** and **AWS CDK**.

We’ll treat this as:

1. **Business Requirement** → Update Excel based on another Excel.
2. **Architecture** → AWS cost-effective, scalable, Git-based infra.
3. **MCP Role** → Automate infra + runtime workflows via AI agent.
4. **Step-by-Step CDK Build** → Start small (base stack), then extend.

---

## 1. Business Requirement

* You have **Excel File A** (source) and **Excel File B** (target).
* The system should update B based on values from A (rules defined by you).
* This must be **automated, repeatable, and cloud-based**.

---

## 2. Architecture (AWS Components)

* **S3** → Store input & output Excel files.
* **Lambda (Python runtime)** → Process Excel updates (using `openpyxl` or `pandas`).
* **EventBridge / S3 Trigger** → Kick off processing when new file uploaded.
* **IAM Roles** → Secure access.
* (Optional) **Step Functions** if workflow grows complex.

This is all **CDK-driven**, deployed via Git.

---

## 3. Role of MCP (Model Context Protocol)

* MCP allows you to **define actions for AI agents** (like me) to orchestrate infra and runtime code.
* Example:

  * Define a **tool in MCP** for "Deploy CDK stack".
  * Define another for "Process Excel".
* Then your AI agent can **decide autonomously**: upload file → trigger Lambda → update Excel → store output → notify you.

So MCP is the glue to:

* **Describe capabilities** (e.g., "Excel Processor").
* **Expose them to AI agent** (so it knows it can invoke CDK/Lambda).
* **Automate workflows** (instead of you clicking manually).

---

## 4. Step-by-Step CDK Build Plan

Here’s how we’ll build incrementally:

### Step 1: **Base Stack**

* VPC (if needed), S3 bucket(s).
* IAM roles & policies.
* Output: "We can upload Excel files."

### Step 2: **Lambda Runtime**

* Python code (using `openpyxl`) packaged & deployed.
* Connected to S3.
* Output: "Lambda runs when file uploaded."

### Step 3: **Event Trigger**

* Configure S3 → EventBridge → Lambda.
* Output: "Automation kicks off on upload."

### Step 4: **Excel Processing Logic**

* Lambda reads `fileA.xlsx` & `fileB.xlsx`, applies rules, writes back to S3.
* Output: "Excel files updated automatically."

### Step 5: **MCP Exposure**

* Define MCP tool(s) → “Upload Excel”, “Run Processor”, “Deploy Stack”.
* Output: "AI agent can handle Excel updates end-to-end."

---

💡 Cost:

* S3 = pennies per GB.
* Lambda = free tier + \$0.20 per 1M requests.
* EventBridge = \$1 per 1M events.
* IAM roles = free.
  👉 Essentially **close to \$0 monthly** unless you process huge Excel files.

---

Do you want me to **start with Step 1 (Base Stack CDK code)** and explain the CDK resources we’ll add before we write the code?



# aws-nasmatchstockprofile-mcp

Foundational CDK app for an MCP-controlled, cost-effective Excel processing pipeline on AWS.

## Step 1 (this repo state)
- KMS CMK (alias: `alias/excel-pipeline-kms`)
- S3 bucket (versioned, KMS-encrypted)
- DynamoDB tables:
  - `MappingOverrides` (PK: dataset_id, SK: source_col)
  - `WsConnections`   (PK: connection_id)

## Install & Deploy

```bash
# from repo root
npm install
npm run build
npm run synth
npm run deploy -- BaseInfra


# after step4
aws-nasmatchstockprofile-mcp/
  bin/app.ts
  lib/base-infra.ts              # add WebSocket API + permissions here
  lambda/
    processor/                   # (already from step2/3)
      handler.py
      requirements.txt
    wsmcp/
      on_connect.py
      on_disconnect.py
      on_message.py
      requirements.txt



Got it 👍 — let’s walk through step by step so you can learn how to approach this with MCP (Model Context Protocol) and AWS CDK.

We’ll treat this as:

Business Requirement → Update Excel based on another Excel.

Architecture → AWS cost-effective, scalable, Git-based infra.

MCP Role → Automate infra + runtime workflows via AI agent.

Step-by-Step CDK Build → Start small (base stack), then extend.

1. Business Requirement

You have Excel File A (source) and Excel File B (target).

The system should update B based on values from A (rules defined by you).

This must be automated, repeatable, and cloud-based.

2. Architecture (AWS Components)

S3 → Store input & output Excel files.

Lambda (Python runtime) → Process Excel updates (using openpyxl or pandas).

EventBridge / S3 Trigger → Kick off processing when new file uploaded.

IAM Roles → Secure access.

(Optional) Step Functions if workflow grows complex.

This is all CDK-driven, deployed via Git.

3. Role of MCP (Model Context Protocol)

MCP allows you to define actions for AI agents (like me) to orchestrate infra and runtime code.

Example:

Define a tool in MCP for "Deploy CDK stack".

Define another for "Process Excel".

Then your AI agent can decide autonomously: upload file → trigger Lambda → update Excel → store output → notify you.

So MCP is the glue to:

Describe capabilities (e.g., "Excel Processor").

Expose them to AI agent (so it knows it can invoke CDK/Lambda).

Automate workflows (instead of you clicking manually).

4. Step-by-Step CDK Build Plan

Here’s how we’ll build incrementally:

Step 1: Base Stack

VPC (if needed), S3 bucket(s).

IAM roles & policies.

Output: "We can upload Excel files."

Step 2: Lambda Runtime

Python code (using openpyxl) packaged & deployed.

Connected to S3.

Output: "Lambda runs when file uploaded."

Step 3: Event Trigger

Configure S3 → EventBridge → Lambda.

Output: "Automation kicks off on upload."

Step 4: Excel Processing Logic

Lambda reads fileA.xlsx & fileB.xlsx, applies rules, writes back to S3.

Output: "Excel files updated automatically."

Step 5: MCP Exposure

Define MCP tool(s) → “Upload Excel”, “Run Processor”, “Deploy Stack”.

Output: "AI agent can handle Excel updates end-to-end."

💡 Cost:

S3 = pennies per GB.

Lambda = free tier + $0.20 per 1M requests.

EventBridge = $1 per 1M events.

IAM roles = free.
👉 Essentially close to $0 monthly unless you process huge Excel files.






aws lambda invoke --function-name BaseInfra-ExcelProcessorFnB7B43EA3-fRqa6Yu3FXTU \
--payload '{
    "source_key":"source/Portfolio_Positions_Aug-21-2025.csv",
    "target_key":"source/nasmatch-portfolio.xlsx",
    "output_key":"output/nasmatch-portfolio-updated.xlsx"
  }' \
/tmp/out.json && cat /tmp/out.json


# make sure the template exists
aws s3 cp ~/Downloads/nasmatch-portfolio.xlsx s3://baseinfra-excelbucket52f10cb5-wwsunmtzl4nc/source/nasmatch-portfolio.xlsx

# upload CSV (should auto-trigger lambda)
aws s3 cp ~/Downloads/Portfolio_Positions_Aug-21-2025.csv s3://baseinfra-excelbucket52f10cb5-wwsunmtzl4nc/source/Portfolio_Positions_Aug-21-2025.csv

# watch logs
aws logs tail /aws/lambda/BaseInfra-ExcelProcessorFnB7B43EA3-fRqa6Yu3FXTU --follow

# verify output
aws s3 cp s3://baseinfra-excelbucket52f10cb5-wwsunmtzl4nc/output/nasmatch-portfolio-updated.xlsx ./nasmatch-portfolio-updated.xlsx
