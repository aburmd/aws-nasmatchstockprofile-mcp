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