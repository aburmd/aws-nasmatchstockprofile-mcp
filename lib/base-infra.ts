import { Stack, StackProps, RemovalPolicy, CfnOutput, Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';
import { Bucket, BucketEncryption, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import { Table, AttributeType, BillingMode, TableEncryption } from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3'; // you already import Bucket; this ensures EventType enum
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';
import * as apigwv2 from 'aws-cdk-lib/aws-apigatewayv2';
import * as apigwIntegrations from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import * as iam from 'aws-cdk-lib/aws-iam';


export class BaseInfraStack extends Stack {
  public readonly bucket: Bucket;
  public readonly mappingTable: Table;
  public readonly connTable: Table;
  public readonly kmsKeyArn: string;

  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // KMS CMK
    const kms = new Key(this, 'DataKms', {
      alias: 'alias/excel-pipeline-kms',
      enableKeyRotation: true,
    });
    this.kmsKeyArn = kms.keyArn;

    // S3 (versioned, KMS)
    this.bucket = new Bucket(this, 'ExcelBucket', {
      versioned: true,
      encryption: BucketEncryption.KMS,
      encryptionKey: kms,
      blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // DDB: mapping overrides
    this.mappingTable = new Table(this, 'MappingOverrides', {
      partitionKey: { name: 'dataset_id', type: AttributeType.STRING },
      sortKey: { name: 'source_col', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kms,
      removalPolicy: RemovalPolicy.RETAIN,
    });

    // DDB: websocket connections (recreatable)
    this.connTable = new Table(this, 'WsConnections', {
      partitionKey: { name: 'connection_id', type: AttributeType.STRING },
      billingMode: BillingMode.PAY_PER_REQUEST,
      encryption: TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: kms,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    // === Lambda: Excel Processor (openpyxl) ===
    const processorFn = new lambda.Function(this, 'ExcelProcessorFn', {
      runtime: lambda.Runtime.PYTHON_3_11,
      architecture: lambda.Architecture.X86_64,
      handler: 'handler.main',
      memorySize: 1536,
      timeout: Duration.seconds(60),
      code: lambda.Code.fromAsset('lambda/processor', {
        bundling: {
          image: lambda.Runtime.PYTHON_3_11.bundlingImage,
          command: [
            'bash', '-lc',
            [
              'pip install -r requirements.txt -t /asset-output',
              'cp -au . /asset-output',
            ].join(' && ')
          ],
        },
      }),
      environment: {
        BUCKET_NAME: this.bucket.bucketName,
        MAPPING_TABLE: this.mappingTable.tableName,
        SOURCE_PREFIX: 'source/',
        OUTPUT_PREFIX: 'output/',
        DEFAULT_DATASET_ID: 'default',

        // ✅ Standard naming
        DEFAULT_CSV_PREFIX: 'positions-',
        TEMPLATE_KEY: 'source/portfolio-template.xlsx',

        // behavior toggles
        COST_MODE: 'total_basis',
        ROW_QTY: '24',
        ROW_COST: '39',

        ACCOUNT_NAME_MAP_JSON: JSON.stringify({
          "BrokerageLink": "401K",
          "BrokerageLink Roth": "401 ROTH",
          "Health Savings Account": "HSA1",
          "ROTH IRA (after-tax Mega BackDoor Roth)": "ROTH IRA1",
          "INDIVIDUAL-Margin": "Brokerage"
        }),
      },
    });

    // === WebSocket API for MCP ===

// Connect
const wsOnConnect = new lambda.Function(this, 'WsOnConnect', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'on_connect.main',
  code: lambda.Code.fromAsset('lambda/wsmcp'),
  timeout: Duration.seconds(10),
  environment: {
    CONN_TABLE: this.connTable.tableName,
  },
});
this.connTable.grantReadWriteData(wsOnConnect);

// Disconnect
const wsOnDisconnect = new lambda.Function(this, 'WsOnDisconnect', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'on_disconnect.main',
  code: lambda.Code.fromAsset('lambda/wsmcp'),
  timeout: Duration.seconds(10),
  environment: {
    CONN_TABLE: this.connTable.tableName,
  },
});
this.connTable.grantReadWriteData(wsOnDisconnect);

// === Lambda: Schema Mapper (uses Bedrock) ===
const schemaMapperFn = new lambda.Function(this, 'SchemaMapperFn', {
  runtime: lambda.Runtime.PYTHON_3_11,
  architecture: lambda.Architecture.X86_64,
  handler: 'mapper.main',
  timeout: Duration.seconds(60),
  memorySize: 1024,
  code: lambda.Code.fromAsset('lambda/mapper', {
    bundling: {
      image: lambda.Runtime.PYTHON_3_11.bundlingImage,
      command: [
        'bash','-lc',
        [
          'pip install -r requirements.txt -t /asset-output',
          'cp -au . /asset-output',
        ].join(' && ')
      ],
    },
  }),
  environment: {
    BUCKET_NAME: this.bucket.bucketName,
    MAPPING_TABLE: this.mappingTable.tableName,
    DEFAULT_DATASET_ID: 'default',
    // Bedrock model IDs (feel free to change region/model versions)
    BEDROCK_TEXT_MODEL_ID: 'anthropic.claude-3-5-sonnet-20240620-v1:0',
    BEDROCK_EMBED_MODEL_ID: 'amazon.titan-embed-text-v1:0',
  },
});


// Allow S3 read, DDB write
this.bucket.grantRead(schemaMapperFn);
this.mappingTable.grantReadWriteData(schemaMapperFn);

// Bedrock invoke permission (replace region if needed)
schemaMapperFn.addToRolePolicy(new iam.PolicyStatement({
  actions: ['bedrock:InvokeModel', 'bedrock:InvokeModelWithResponseStream'],
  resources: ['*'],
}));

// Default route: MCP tool router
const wsOnMessage = new lambda.Function(this, 'WsOnMessage', {
  runtime: lambda.Runtime.PYTHON_3_11,
  handler: 'on_message.main',
  code: lambda.Code.fromAsset('lambda/wsmcp', {
    bundling: {
      image: lambda.Runtime.PYTHON_3_11.bundlingImage,
      command: [
        'bash', '-lc',
        [
          'pip install -r requirements.txt -t /asset-output',
          'cp -au . /asset-output',
        ].join(' && ')
      ],
    },
  }),
  timeout: Duration.seconds(60),
  environment: {
    CONN_TABLE: this.connTable.tableName,
    BUCKET_NAME: this.bucket.bucketName,            // if future tools need S3
    PROCESSOR_FN_ARN: processorFn.functionArn,
    SCHEMA_MAPPER_FN_ARN: schemaMapperFn.functionArn,
  },
});

schemaMapperFn.grantInvoke(wsOnMessage);

this.connTable.grantReadWriteData(wsOnMessage);
this.bucket.grantReadWrite(wsOnMessage);
processorFn.grantInvoke(wsOnMessage);

// WebSocket API resources
const wsApi = new apigwv2.WebSocketApi(this, 'McpWsApi', {
  connectRouteOptions: { integration: new apigwIntegrations.WebSocketLambdaIntegration('ConnectInt', wsOnConnect) },
  disconnectRouteOptions: { integration: new apigwIntegrations.WebSocketLambdaIntegration('DisconnectInt', wsOnDisconnect) },
  defaultRouteOptions: { integration: new apigwIntegrations.WebSocketLambdaIntegration('DefaultInt', wsOnMessage) },
});

const wsStage = new apigwv2.WebSocketStage(this, 'McpWsStage', {
  webSocketApi: wsApi,
  stageName: 'prod',
  autoDeploy: true,
});

// Let the router send messages back to clients
wsApi.grantManageConnections(wsOnMessage);


// Output URL for clients
new CfnOutput(this, 'McpWebSocketUrl', { value: wsStage.url });


// Trigger the processor on any CSV uploaded to source/
this.bucket.addEventNotification(
  s3.EventType.OBJECT_CREATED_PUT,
  new s3n.LambdaDestination(processorFn),
  { prefix: 'source/', suffix: '.csv' }
);

// (Optional) handle multi-part uploads too
this.bucket.addEventNotification(
  s3.EventType.OBJECT_CREATED_COMPLETE_MULTIPART_UPLOAD,
  new s3n.LambdaDestination(processorFn),
  { prefix: 'source/', suffix: '.csv' }
);


    // Permissions
    this.bucket.grantReadWrite(processorFn);
    this.mappingTable.grantReadData(processorFn);
    kms.grantEncryptDecrypt(processorFn);

    // Outputs
    new CfnOutput(this, 'KmsKeyArn', { value: this.kmsKeyArn });
    new CfnOutput(this, 'BucketName', { value: this.bucket.bucketName });
    new CfnOutput(this, 'MappingTableName', { value: this.mappingTable.tableName });
    new CfnOutput(this, 'WsConnectionsTableName', { value: this.connTable.tableName });
    new CfnOutput(this, 'ExcelProcessorFnName', { value: processorFn.functionName });
    new CfnOutput(this, 'ExcelProcessorFnArn', { value: processorFn.functionArn });
  }
}
