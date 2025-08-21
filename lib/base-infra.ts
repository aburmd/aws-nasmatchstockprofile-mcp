import { Stack, StackProps, RemovalPolicy, CfnOutput, Duration } from 'aws-cdk-lib';
import { Construct } from 'constructs';
import { Key } from 'aws-cdk-lib/aws-kms';
import { Bucket, BucketEncryption, BlockPublicAccess } from 'aws-cdk-lib/aws-s3';
import { Table, AttributeType, BillingMode, TableEncryption } from 'aws-cdk-lib/aws-dynamodb';
import * as lambda from 'aws-cdk-lib/aws-lambda';
import * as s3 from 'aws-cdk-lib/aws-s3'; // you already import Bucket; this ensures EventType enum
import * as s3n from 'aws-cdk-lib/aws-s3-notifications';

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
        TARGET_TEMPLATE_KEY: 'source/nasmatch-portfolio.xlsx',          // 👈 add
        OUTPUT_KEY_TEMPLATE: 'output/nasmatch-portfolio-updated.xlsx',   // 👈 add
      },
    });


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
