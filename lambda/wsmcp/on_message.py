import os
import json
import boto3

dynamodb = boto3.resource('dynamodb')
CONN_TABLE = dynamodb.Table(os.environ['CONN_TABLE'])
lambda_client = boto3.client('lambda')

# API Gateway Management API client (built per-connection)
apigw_mgmt = None

PROCESSOR_FN_ARN = os.environ['PROCESSOR_FN_ARN']
SCHEMA_MAPPER_FN_ARN = os.environ.get('SCHEMA_MAPPER_FN_ARN')  # optional

def _apigw_client(domain, stage):
    global apigw_mgmt
    apigw_mgmt = boto3.client('apigatewaymanagementapi', endpoint_url=f"https://{domain}/{stage}")
    return apigw_mgmt

def _post(domain, stage, connection_id, payload: dict):
    client = _apigw_client(domain, stage)
    client.post_to_connection(ConnectionId=connection_id, Data=json.dumps(payload).encode('utf-8'))

# ==== Tools ====

def _tool_process_excel(args: dict):
    payload = {
        "source_key": args.get("source_key"),
        "target_key": args.get("target_key"),
        "output_key": args.get("output_key"),
    }
    resp = lambda_client.invoke(
        FunctionName=PROCESSOR_FN_ARN,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload).encode('utf-8'),
    )
    return json.loads(resp['Payload'].read() or '{}')

def _tool_infer_mapping(args: dict):
    if not SCHEMA_MAPPER_FN_ARN:
        return {"ok": False, "error": "SCHEMA_MAPPER_FN_ARN not configured on server"}
    payload = {
        "csv_key": args.get("csv_key"),
        "template_key": args.get("template_key"),
        "dataset_id": args.get("dataset_id", "default"),
    }
    resp = lambda_client.invoke(
        FunctionName=SCHEMA_MAPPER_FN_ARN,
        InvocationType='RequestResponse',
        Payload=json.dumps(payload).encode('utf-8'),
    )
    return json.loads(resp['Payload'].read() or '{}')

TOOLS = {
    "process_excel": _tool_process_excel,
    "infer_mapping": _tool_infer_mapping,  # NEW
}

def _advertise_tools(domain, stage, connection_id):
    _post(domain, stage, connection_id, {
        "type": "tools",
        "tools": [
            {
                "name": "process_excel",
                "description": "Process a Fidelity CSV into Excel consolidate sheet and per-ticker cells.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "source_key": {"type": "string"},
                        "target_key": {"type": "string"},
                        "output_key": {"type": "string"}
                    },
                    "required": ["source_key"]
                }
            },
            {
                "name": "infer_mapping",
                "description": "Infer mapping from CSV Account Name → Excel account headers (row1) and save to DDB MappingOverrides.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "csv_key": {"type": "string"},
                        "template_key": {"type": "string"},
                        "dataset_id": {"type": "string"}
                    },
                    "required": ["csv_key", "template_key"]
                }
            }
        ]
    })

def main(event, context):
    domain = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    connection_id = event['requestContext']['connectionId']

    try:
        body = json.loads(event.get('body') or '{}')
    except Exception:
        body = {}

    t = body.get('type')
    req_id = body.get('request_id')

    if t == 'ping':
        _post(domain, stage, connection_id, {"type": "pong", "request_id": req_id})
        return {'statusCode': 200}

    if t == 'call_tool':
        tool = body.get('tool')
        args = body.get('args', {}) or {}
        func = TOOLS.get(tool)
        if not func:
            _post(domain, stage, connection_id, {
                "type": "tool_result", "ok": False,
                "error": f"unknown tool '{tool}'",
                "request_id": req_id
            })
            return {'statusCode': 200}
        try:
            result = func(args)
            _post(domain, stage, connection_id, {
                "type": "tool_result", "ok": True, "result": result, "request_id": req_id
            })
        except Exception as e:
            _post(domain, stage, connection_id, {
                "type": "tool_result", "ok": False, "error": str(e), "request_id": req_id
            })
        return {'statusCode': 200}

    # Default: advertise capabilities
    _advertise_tools(domain, stage, connection_id)
    return {'statusCode': 200}
