from aws_cdk import (
    Stack,
    CfnParameter as _cfnParameter,
    aws_cognito as _cognito,
    aws_s3 as _s3,
    aws_dynamodb as _dynamodb,
    aws_lambda as _lambda,
    aws_apigateway as _apigateway,
    aws_apigatewayv2 as _apigatewayv2,
    aws_apigatewayv2_integrations as _apigatewayv2_integrations,
    aws_apigatewayv2_authorizers as _apigatewayv2_authorizers,

)
from constructs import Construct
import os


class ServerlessBackendStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        bucket_name = _cfnParameter(self, "uploadBucketName", type="String",
                                    description="The name of the Amazon S3 bucket where uploaded images will be stored.")
        user_pool = _cognito.UserPool(self, "UserPool")
        user_pool_client = user_pool.add_client("app-client", auth_flows=_cognito.AuthFlow(
            user_password=True,
            user_srp=True
        ),
            supported_identity_providers=[
                _cognito.UserPoolClientIdentityProvider.COGNITO]
        )
        # my_table = _dynamodb.Table(self, id='dynamoTable', table_name='formmetadata', partition_key=_dynamodb.Attribute(
        #     name='userid', type=_dynamodb.AttributeType.STRING)) #change primary key here
        my_table = _dynamodb.Table(self, 'dynamoTable',
        table_name='warehousedata',
        partition_key=_dynamodb.Attribute(name='PK', type=_dynamodb.AttributeType.STRING),
        sort_key=_dynamodb.Attribute(name='SK', type=_dynamodb.AttributeType.STRING)
        )
        my_bucket = _s3.Bucket(self, id='s3bucket',
                               bucket_name=bucket_name.value_as_string)
        my_lambda = _lambda.Function(self, id='lambdafunction', function_name="formlambda", runtime=_lambda.Runtime.PYTHON_3_12,
                                     handler='index.handler',
                                     code=_lambda.Code.from_asset(
                                         os.path.join("./", "lambda-handler")),
                                     environment={
                                         'bucket': my_bucket.bucket_name,
                                         'table': my_table.table_name
                                     }
                                     )
        my_bucket.grant_read_write(my_lambda)
        my_table.grant_read_write_data(my_lambda)
        tim_authorizer = _apigatewayv2_authorizers.HttpUserPoolAuthorizer(
            id='user-pool-authorizer', pool=user_pool, user_pool_clients=[user_pool_client]
        )
        tim_api = _apigatewayv2.HttpApi(self, id='api', api_name='tim-api')

        # tim_api.add_routes(
        #     path='/tim',
        #     methods=[_apigatewayv2.HttpMethod.POST],
        #     integration=_apigatewayv2_integrations.HttpLambdaIntegration(
        #         id='tim-integration',
        #         handler=my_lambda
        #     ),
        #     authorizer=tim_authorizer
        # )

        routes = [
            {
                "path": "/warehouses",
                "methods": [_apigatewayv2.HttpMethod.POST]
            },
            {
                "path": "/warehouses",
                "methods": [_apigatewayv2.HttpMethod.GET]
            },
            {
                "path": "/warehouses/{warehouseId}",
                "methods": [_apigatewayv2.HttpMethod.GET]
            },
            {
                "path": "/warehouses/{warehouseId}",
                "methods": [_apigatewayv2.HttpMethod.PUT]
            },
            {
                "path": "/warehouses/{warehouseId}",
                "methods": [_apigatewayv2.HttpMethod.DELETE]
            },
            {
                "path": "/warehouses/{warehouseId}/items",
                "methods": [_apigatewayv2.HttpMethod.POST]
            },
            {
                "path": "/warehouses/{warehouseId}/items",
                "methods": [_apigatewayv2.HttpMethod.GET]
            },
            {
                "path": "/warehouses/{warehouseId}/items/{itemId}",
                "methods": [_apigatewayv2.HttpMethod.GET]
            },
            {
                "path": "/warehouses/{warehouseId}/items/{itemId}",
                "methods": [_apigatewayv2.HttpMethod.PUT]
            },
            {
                "path": "/warehouses/{warehouseId}/items/{itemId}",
                "methods": [_apigatewayv2.HttpMethod.DELETE]
            },
            {
                "path": "/warehouses/{warehouseId}/access",
                "methods": [_apigatewayv2.HttpMethod.POST]
            },
            {
                "path": "/warehouses/{warehouseId}/access",
                "methods": [_apigatewayv2.HttpMethod.GET]
            },
            {
                "path": "/warehouses/{warehouseId}/access/{userId}",
                "methods": [_apigatewayv2.HttpMethod.DELETE]
            }
        ]

        for i, route_info in enumerate(routes):
            tim_api.add_routes(
                path=route_info["path"],
                methods=route_info["methods"],
                # Use a unique id for each integration
                integration=_apigatewayv2_integrations.HttpLambdaIntegration(
                    id=f"tim-integration-{i}",
                    handler=my_lambda
                ),
                authorizer=tim_authorizer
            )