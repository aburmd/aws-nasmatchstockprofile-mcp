#!/usr/bin/env node
import { App } from 'aws-cdk-lib';
import { BaseInfraStack } from '../lib/base-infra';

const app = new App();

// Step 1: only BaseInfra (we’ll add WsMcp etc. in later steps)
new BaseInfraStack(app, 'BaseInfra', {
  env: { account: process.env.CDK_DEFAULT_ACCOUNT, region: process.env.CDK_DEFAULT_REGION },
});


