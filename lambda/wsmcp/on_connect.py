import os
import boto3

dynamodb = boto3.resource('dynamodb')
CONN_TABLE = dynamodb.Table(os.environ['CONN_TABLE'])

def main(event, context):
    connection_id = event['requestContext']['connectionId']
    CONN_TABLE.put_item(Item={'connection_id': connection_id})
    return {'statusCode': 200}
