# Documentation Index — aws-nasmatchstockprofile-mcp

Welcome to the documentation section of this repository.  
Here you will find guides to set up your environment, deploy the stack, and understand the Excel Processor system.

---

## 📘 Guides

1. [Prerequisites & Setup Guide](Prerequisites-And-Setup-Guide.pdf)  
   Step-by-step instructions for preparing a brand-new laptop with AWS CLI, Node.js, CDK, GitHub SSH, Docker, and Bedrock model access.  
   Markdown version: [SETUP.md](SETUP.md)

2. [Excel Processor Setup Documentation](ExcelProcessorSetup.pdf)  
   Contains the requirements and implementation details for the Excel Processor Lambda, S3/DynamoDB/CDK infra, MCP tools, and validation.

---

## Usage Notes

- Always bootstrap your AWS account once per region before CDK deploy:  
  ```bash
  cdk bootstrap aws://<ACCOUNT_ID>/us-east-1
  ```

- Keep both PDF and Markdown versions in the `docs/` folder for easy offline and GitHub viewing.

- Suggested structure:
  ```
  aws-nasmatchstockprofile-mcp/
  └── docs/
      ├── README.md
      ├── SETUP.md
      ├── Prerequisites-And-Setup-Guide.pdf
      └── ExcelProcessorSetup.pdf
  ```
