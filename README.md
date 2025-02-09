# Serverless-backend for your my university project

# Stack will deploy the following services: 
- Amazon API Gateway - Entry point for your backend
- AWS Lambda - Process JSON POST request
- Amazon DynamoDB - Table for to store metadata
- Amazon Cognito - Secure your backend with User Pool 
- AWS IAM - Creates permissions 


# Prerequisites:

* An active AWS account
* AWS Command Line Interface (AWS CLI) (Install and configure) 
* AWS CDK Toolkit, (Install and configure)


# Deploy Stack

Since the stack's definition requires the user to provide a uniqe S3 bucket name, you will need to pass in your desired bucket name as a parameter. 
Use the command below to deploy the CDK stack: 

```cdk deploy ServerlessBackendStack --parameters uploadBucketName=globallyuniquebucketname```


## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation
