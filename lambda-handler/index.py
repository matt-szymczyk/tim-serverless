import json
import boto3
from decimal import Decimal
import os
import time

client = boto3.client('dynamodb')
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ['table'])  # Single DynamoDB table

def handler(event, context):
    print(event)
    statusCode = 200
    headers = {
        "Content-Type": "application/json"
    }
    body = {}

    # Get the authenticated user from HTTP API Gateway
    authorized_user_id = event["requestContext"]["authorizer"]["jwt"]["claims"]["cognito:username"]

    # stuff = [event, context]
    # return {
    #     "statusCode": statusCode,
    #     "headers": headers,
    #     "body": json.dumps(str(stuff))
    # }

    # Helper functions
    def get_user_access_role(warehouse_id, user_id):
        """
        Returns the role (str) if user has an ACCESS row in that warehouse partition,
        or None if no access row found.
        """
        resp = table.get_item(
            Key={
                "PK": f"WAREHOUSE#{warehouse_id}",
                "SK": f"ACCESS#{user_id}"
            }
        )
        item = resp.get("Item")
        if item:
            return item.get("role")
        return None

    def require_access(warehouse_id, user_id, allowed_roles=None):
        """
        Raises a 403 error if user_id does not have one of the allowed_roles in the warehouse.
        If allowed_roles is None, any valid role is accepted.
        """
        role = get_user_access_role(warehouse_id, user_id)
        if role is None:
            raise PermissionError("No access to this warehouse.")
        if allowed_roles and role not in allowed_roles:
            raise PermissionError(f"Must have one of {allowed_roles} roles to perform this action.")
        # If we get here, user has valid permission

    try:
        route_key = event['routeKey']
        path_parameters = event.get('pathParameters', {})
        request_body = {}
        if event.get('body'):
            request_body = json.loads(event['body'])

        # --------------------------------------------------------------------
        # 1. WAREHOUSE MANAGEMENT
        # --------------------------------------------------------------------
        # 1A) CREATE WAREHOUSE (POST /warehouses)
        if route_key == "POST /warehouses":
            warehouse_id = request_body.get('warehouseId')
            warehouse_name = request_body.get('warehouseName', '')
            created_at = int(time.time())

            # Check if warehouse already exists
            resp = table.get_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": "METADATA"
                }
            )
            if resp.get("Item"):
                statusCode = 400
                body = {"error": f"Warehouse {warehouse_id} already exists."}
                return build_response(statusCode, body, headers)

            # Create the warehouse metadata row
            table.put_item(
                Item={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": "METADATA",
                    "warehouseName": warehouse_name,
                    "createdAt": created_at
                }
            )

            # Also create an ACCESS row for the creating user => role="owner"
            table.put_item(
                Item={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ACCESS#{authorized_user_id}",
                    "role": "owner",
                    "addedAt": created_at
                }
            )

            body = {
                "message": f"Created warehouse {warehouse_id}.",
                "warehouseId": warehouse_id
            }

        # 1B) LIST WAREHOUSES (GET /warehouses)
        elif route_key == "GET /warehouses":
            # For demonstration, we do a table scan:
            #  - find all PKs that start with "WAREHOUSE#",
            #  - filter to those that have an ACCESS row for authorized_user_id
            #  - then get the METADATA row for each to build a list
            # Production: consider using a GSI to find all warehouse partitions
            # that user_id has an access row in.
            resp = table.scan()
            items = resp.get("Items", [])

            # Step 1: collect all warehouses user can access
            user_warehouses = set()
            for it in items:
                if (it["SK"].startswith("ACCESS#") 
                    and it["SK"] == f"ACCESS#{authorized_user_id}"
                    and it["PK"].startswith("WAREHOUSE#")):
                    # user has an ACCESS row here
                    wh_id = it["PK"].replace("WAREHOUSE#", "")
                    user_warehouses.add(wh_id)

            # Step 2: get the METADATA items for those warehouses
            results = []
            for it in items:
                if it["SK"] == "METADATA":
                    wh_id = it["PK"].replace("WAREHOUSE#", "")
                    if wh_id in user_warehouses:
                        results.append({
                            "warehouseId": wh_id,
                            "warehouseName": it.get("warehouseName", ""),
                            "createdAt": it.get("createdAt")
                        })

            body = results

        # 1C) GET WAREHOUSE (GET /warehouses/{warehouseId})
        elif route_key == "GET /warehouses/{warehouseId}":
            warehouse_id = path_parameters.get("warehouseId")

            # Check user has some role in this warehouse (owner, editor, viewer, etc)
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=None)
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # If user has access, retrieve the warehouse
            resp = table.get_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": "METADATA"
                }
            )
            item = resp.get("Item")
            if not item:
                statusCode = 404
                body = {"error": "Warehouse not found"}
            else:
                body = {
                    "warehouseId": warehouse_id,
                    "warehouseName": item.get("warehouseName", ""),
                    "createdAt": item.get("createdAt", "")
                }

        # 1D) UPDATE WAREHOUSE (PUT /warehouses/{warehouseId})
        elif route_key == "PUT /warehouses/{warehouseId}":
            warehouse_id = path_parameters.get("warehouseId")
            new_name = request_body.get('warehouseName', '')

            # Only owners (or possibly "admin") can update warehouse details
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Update the warehouse name
            table.update_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": "METADATA"
                },
                UpdateExpression="SET warehouseName = :wn",
                ExpressionAttributeValues={
                    ":wn": new_name
                }
            )
            body = {"message": f"Warehouse {warehouse_id} updated."}

        # 1E) DELETE WAREHOUSE (DELETE /warehouses/{warehouseId})
        elif route_key == "DELETE /warehouses/{warehouseId}":
            warehouse_id = path_parameters.get("warehouseId")

            # Only owners can delete the entire warehouse
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Delete all items (METADATA, ACCESS#, ITEM#)
            # In production: you might do a 'Query' on PK = WAREHOUSE#<id> and batch delete
            scan_resp = table.scan()
            items = scan_resp.get("Items", [])
            for it in items:
                if it["PK"] == f"WAREHOUSE#{warehouse_id}":
                    table.delete_item(
                        Key={
                            "PK": it["PK"],
                            "SK": it["SK"]
                        }
                    )

            body = {"message": f"Warehouse {warehouse_id} and all related records deleted."}

        # --------------------------------------------------------------------
        # 2. WAREHOUSE ACCESS MANAGEMENT
        # --------------------------------------------------------------------
        # 2A) GRANT/UPDATE ACCESS (POST /warehouses/{warehouseId}/access)
        elif route_key == "POST /warehouses/{warehouseId}/access":
            warehouse_id = path_parameters.get("warehouseId")
            user_to_grant = request_body.get("userId")
            new_role = request_body.get("role")  # e.g. "editor", "viewer", etc.

            # Only owner can grant or update roles
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Insert or update the ACCESS row
            now = int(time.time())
            table.put_item(
                Item={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ACCESS#{user_to_grant}",
                    "role": new_role,
                    "addedAt": now
                }
            )
            body = {"message": f"User {user_to_grant} given role '{new_role}' in warehouse {warehouse_id}."}

        # 2B) LIST USERS WITH ACCESS (GET /warehouses/{warehouseId}/access)
        elif route_key == "GET /warehouses/{warehouseId}/access":
            warehouse_id = path_parameters.get("warehouseId")

            # Only owner can see who else has access
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Get all ACCESS rows for this warehouse
            # Production: would use a Query with KeyConditionExpression
            resp = table.scan()
            items = resp.get("Items", [])
            access_list = []
            for it in items:
                if it["PK"] == f"WAREHOUSE#{warehouse_id}" and it["SK"].startswith("ACCESS#"):
                    access_list.append({
                        "userId": it["SK"].replace("ACCESS#", ""),
                        "role": it["role"]
                    })
            body = access_list

        # 2C) REVOKE ACCESS (DELETE /warehouses/{warehouseId}/access/{userId})
        elif route_key == "DELETE /warehouses/{warehouseId}/access/{userId}":
            warehouse_id = path_parameters.get("warehouseId")
            user_to_revoke = path_parameters.get("userId")

            # Only owner can revoke access
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Delete the ACCESS row for that user
            table.delete_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ACCESS#{user_to_revoke}"
                }
            )
            body = {"message": f"Revoked access for user {user_to_revoke} in warehouse {warehouse_id}."}

        # --------------------------------------------------------------------
        # 3. ITEM MANAGEMENT (similar to previous example)
        # --------------------------------------------------------------------
        # 3A) CREATE ITEM (POST /warehouses/{warehouseId}/items)
        elif route_key == "POST /warehouses/{warehouseId}/items":
            warehouse_id = path_parameters.get("warehouseId")
            item_id = request_body.get("itemId")
            item_name = request_body.get("itemName", "")
            quantity = request_body.get("quantity", 0)

            # Suppose "owner" or "editor" can create items
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner", "editor"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # Check if item already exists
            resp = table.get_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ITEM#{item_id}"
                }
            )
            if "Item" in resp:
                statusCode = 400
                body = {"error": f"Item {item_id} already exists in warehouse {warehouse_id}."}
                return build_response(statusCode, body, headers)

            table.put_item(
                Item={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ITEM#{item_id}",
                    "itemName": item_name,
                    "quantity": Decimal(str(quantity))
                }
            )
            body = {"message": f"Created item {item_id} in warehouse {warehouse_id}."}

        # 3B) LIST ITEMS (GET /warehouses/{warehouseId}/items)
        elif route_key == "GET /warehouses/{warehouseId}/items":
            warehouse_id = path_parameters.get("warehouseId")

            # Any valid role can read items
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=None)
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            # In production: do a Query for PK = WAREHOUSE#warehouse_id, SK begins_with ITEM#
            scan_resp = table.scan()
            all_items = scan_resp.get("Items", [])
            warehouse_items = []
            for it in all_items:
                if it["PK"] == f"WAREHOUSE#{warehouse_id}" and it["SK"].startswith("ITEM#"):
                    warehouse_items.append({
                        "itemId": it["SK"].replace("ITEM#", ""),
                        "itemName": it.get("itemName"),
                        "quantity": int(it.get("quantity", 0))
                    })
            body = warehouse_items

        # 3C) GET SINGLE ITEM (GET /warehouses/{warehouseId}/items/{itemId})
        elif route_key == "GET /warehouses/{warehouseId}/items/{itemId}":
            warehouse_id = path_parameters.get("warehouseId")
            item_id = path_parameters.get("itemId")

            # Any valid role can read
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=None)
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            resp = table.get_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ITEM#{item_id}"
                }
            )
            item = resp.get("Item")
            if not item:
                statusCode = 404
                body = {"error": "Item not found"}
            else:
                body = {
                    "itemId": item["SK"].replace("ITEM#", ""),
                    "itemName": item.get("itemName"),
                    "quantity": int(item.get("quantity", 0))
                }

        # 3D) UPDATE ITEM (PUT /warehouses/{warehouseId}/items/{itemId})
        elif route_key == "PUT /warehouses/{warehouseId}/items/{itemId}":
            warehouse_id = path_parameters.get("warehouseId")
            item_id = path_parameters.get("itemId")
            new_name = request_body.get("itemName")
            new_quantity = request_body.get("quantity")

            # Suppose "owner" or "editor" can update items
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner", "editor"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            update_expr = []
            expression_values = {}
            if new_name is not None:
                update_expr.append("itemName = :nm")
                expression_values[":nm"] = new_name
            if new_quantity is not None:
                update_expr.append("quantity = :qt")
                expression_values[":qt"] = Decimal(str(new_quantity))

            if update_expr:
                table.update_item(
                    Key={
                        "PK": f"WAREHOUSE#{warehouse_id}",
                        "SK": f"ITEM#{item_id}"
                    },
                    UpdateExpression="SET " + ", ".join(update_expr),
                    ExpressionAttributeValues=expression_values
                )
                body = {"message": f"Item {item_id} updated in warehouse {warehouse_id}."}
            else:
                body = {"message": "No fields to update."}

        # 3E) DELETE ITEM (DELETE /warehouses/{warehouseId}/items/{itemId})
        elif route_key == "DELETE /warehouses/{warehouseId}/items/{itemId}":
            warehouse_id = path_parameters.get("warehouseId")
            item_id = path_parameters.get("itemId")

            # Suppose "owner" or "editor" can delete items
            try:
                require_access(warehouse_id, authorized_user_id, allowed_roles=["owner", "editor"])
            except PermissionError as pe:
                statusCode = 403
                body = {"error": str(pe)}
                return build_response(statusCode, body, headers)

            table.delete_item(
                Key={
                    "PK": f"WAREHOUSE#{warehouse_id}",
                    "SK": f"ITEM#{item_id}"
                }
            )
            body = {"message": f"Deleted item {item_id} from warehouse {warehouse_id}."}

        # --------------------------------------------------------------------
        # FALLBACK: No matching route
        # --------------------------------------------------------------------
        else:
            statusCode = 400
            body = {"error": f"Unsupported route: {route_key}"}

    except PermissionError as pe:
        statusCode = 403
        body = {"error": str(pe)}
    except Exception as e:
        print("ERROR:", e)
        statusCode = 500
        body = {"error": str(e)}

    return build_response(statusCode, body, headers)

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # convert to str or float
            return float(obj)
        return super(DecimalEncoder, self).default(obj)

def build_response(status_code, body, headers):
    return {
        "statusCode": status_code,
        "headers": headers,
        "body": json.dumps(body, cls=DecimalEncoder)
    }
