# lambda/wsmcp/on_message.py
# Expose MCP tool 'process_excel' that can run with empty args.
# When args are omitted, the processor Lambda defaults to:
#   - latest source/positions-*.csv
#   - template: source/portfolio-template.xlsx
#   - output:   output/portfolio-updated-<ts>.xlsx

import os
import json
import boto3

CONN_TABLE = os.environ["CONN_TABLE"]
PROCESSOR_FN_ARN = os.environ.get("PROCESSOR_FN_ARN")

dynamodb = boto3.resource("dynamodb")
conn_table = dynamodb.Table(CONN_TABLE)
apigw = None
lambda_client = boto3.client("lambda")

def _apigw_client(domain, stage):
    global apigw
    apigw = boto3.client("apigatewaymanagementapi", endpoint_url=f"https://{domain}/{stage}")
    return apigw

def _post(domain, stage, connection_id, payload: dict):
    _apigw_client(domain, stage).post_to_connection(
        ConnectionId=connection_id,
        Data=json.dumps(payload).encode("utf-8")
    )

def _tool_process_excel(args: dict):
    # Allow empty args -> defaults in handler
    payload = {
        "source_key": args.get("source_key"),
        "target_key": args.get("target_key"),
        "output_key": args.get("output_key"),
    }
    resp = lambda_client.invoke(
        FunctionName=PROCESSOR_FN_ARN,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8")
    )
    body = resp["Payload"].read()
    return json.loads(body or "{}")

def main(event, context):
    domain = event["requestContext"]["domainName"]
    stage = event["requestContext"]["stage"]
    connection_id = event["requestContext"]["connectionId"]

    try:
        body = json.loads(event.get("body") or "{}")
    except Exception:
        body = {}

    t = body.get("type")
    req_id = body.get("request_id")

    if t == "ping":
        _post(domain, stage, connection_id, {"type": "pong", "request_id": req_id})
        return {"statusCode": 200}

    if t == "call_tool":
        tool = body.get("tool")
        args = body.get("args") or {}
        try:
            if tool == "process_excel":
                result = _tool_process_excel(args)
                _post(domain, stage, connection_id, {"type": "tool_result", "ok": True, "result": result, "request_id": req_id})
            else:
                _post(domain, stage, connection_id, {"type": "tool_result", "ok": False, "error": f"unknown tool {tool}", "request_id": req_id})
        except Exception as e:
            _post(domain, stage, connection_id, {"type": "tool_result", "ok": False, "error": str(e), "request_id": req_id})
        return {"statusCode": 200}

    # Advertise capabilities
    _post(domain, stage, connection_id, {
        "type": "tools",
        "tools": [{
            "name": "process_excel",
            "description": "Process positions CSV into the portfolio workbook. Args optional; defaults apply.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "source_key": {"type": "string"},
                    "target_key": {"type": "string"},
                    "output_key": {"type": "string"}
                }
            }
        }]
    })
    return {"statusCode": 200}
