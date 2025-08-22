import os
import boto3

dynamodb = boto3.resource('dynamodb')
CONN_TABLE = dynamodb.Table(os.environ['CONN_TABLE'])

def main(event, context):
    connection_id = event['requestContext']['connectionId']
    try:
        CONN_TABLE.delete_item(Key={'connection_id': connection_id})
    except Exception:
        pass
    return {'statusCode': 200}
