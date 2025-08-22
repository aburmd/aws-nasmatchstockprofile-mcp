# Prerequisites & Setup Guide — aws-nasmatchstockprofile-mcp

This guide covers a brand-new **macOS** laptop setup to build, deploy, and operate this repo.

---

## 1) Scope & Audience
Set up AWS CLI, Node.js, CDK, Docker, GitHub SSH, and Bedrock model access for this project.

## 2) System Requirements
- macOS admin user
- Internet access
- GitHub account
- AWS account (IAM or SSO)

## 3) Install Homebrew & Core Tools
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install git jq unzip wget
# Docker Desktop: install from docker.com and open it
docker info
```

## 4) Install Node.js & AWS CDK
```bash
brew install nvm && mkdir -p ~/.nvm
echo 'export NVM_DIR="$HOME/.nvm"' >> ~/.zshrc
echo '[ -s "/opt/homebrew/opt/nvm/nvm.sh" ] && . "/opt/homebrew/opt/nvm/nvm.sh"' >> ~/.zshrc
source ~/.zshrc
nvm install --lts && nvm use --lts
npm i -g aws-cdk@2
```

## 5) GitHub SSH
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519
pbcopy < ~/.ssh/id_ed25519.pub   # add to GitHub → Settings → SSH and GPG keys
ssh -T git@github.com
```

## 6) Clone the Repository
```bash
git clone git@github.com:aburmd/aws-nasmatchstockprofile-mcp.git
cd aws-nasmatchstockprofile-mcp
npm install
```

## 7) AWS CLI & Auth
```bash
brew install awscli
aws configure              # or: aws configure sso
aws sts get-caller-identity
```

## 8) CDK Bootstrap (first time in account/region)
```bash
cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
```

## 9) Bedrock Model Access & IAM
Enable in Console (us-east-1):
- amazon.titan-embed-text-v1
- anthropic.claude-3-5-sonnet-20240620-v1:0

Example IAM JSON:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["bedrock:InvokeModel","bedrock:InvokeModelWithResponseStream"],
    "Resource": [
      "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v1",
      "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-5-sonnet-20240620-v1:0"
    ]
  }]
}
```

## 10) Build & Deploy
```bash
npm run build
npx cdk deploy BaseInfra
```

## 11) Prepare Input Files (S3)
```bash
aws s3 cp ./nasmatch-portfolio.xlsx s3://<BucketFromOutputs>/source/nasmatch-portfolio.xlsx
aws s3 cp ./Portfolio_Positions_Aug-21-2025.csv s3://<BucketFromOutputs>/source/Portfolio_Positions_Aug-21-2025.csv
```

## 12) Invoke & Validate
```bash
aws lambda invoke   --function-name <ExcelProcessorFnName>   --cli-binary-format raw-in-base64-out   --payload '{"source_key":"source/Portfolio_Positions_Aug-21-2025.csv","target_key":"source/nasmatch-portfolio.xlsx","output_key":"output/nasmatch-portfolio-updated.xlsx"}'   /tmp/out.json && cat /tmp/out.json

BUCKET=$(jq -r .bucket /tmp/out.json)
REPORT=$(jq -r .report_key /tmp/out.json)
aws s3 cp "s3://$BUCKET/$REPORT" ./run-report.json
cat run-report.json
```

## 13) MCP Tool Test (WebSocket)
```bash
npm i -g wscat
wscat -c wss://<id>.execute-api.us-east-1.amazonaws.com/prod   -x '{"type":"call_tool","tool":"process_excel","args":{"source_key":"source/Portfolio_Positions_Aug-21-2025.csv","target_key":"source/nasmatch-portfolio.xlsx","output_key":"output/nasmatch-portfolio-updated.xlsx"},"request_id":"p1"}'
```

## 14) Troubleshooting
- Docker must be running for CDK bundling
- Bedrock: Model access (console) + IAM permissions (exact ARNs)
- per_ticker_writes = 0 → check run-report.json missing_accounts; add DDB/env mapping
- Wrong rows → set ROW_QTY/ROW_COST envs

## 15) Teardown
```bash
npx cdk destroy BaseInfra
# Empty S3 bucket first if RETAIN prevents deletion
```

## 16) Security Notes
- Prefer SSO over static keys
- Don’t commit secrets
- Use least privilege for Bedrock
