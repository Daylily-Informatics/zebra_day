#!/usr/bin/env python3
"""
Apply IAM policy to daylily-service user for zebra_day DynamoDB access.
"""
import json
import sys
import time

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    print("ERROR: boto3 is not installed. Install with: pip install boto3")
    sys.exit(1)

POLICY_FILE = "iam-policy-daylily-service-zebra-day.json"
POLICY_NAME = "ZebraDayDynamoDBAccess"
USER_NAME = "daylily-service"
ACCOUNT_ID = "108782052779"


def main():
    # Get AWS profile from command line or environment
    profile = sys.argv[1] if len(sys.argv) > 1 else None

    # Load policy document
    try:
        with open(POLICY_FILE, "r") as f:
            policy_document = json.load(f)
    except FileNotFoundError:
        print(f"ERROR: Policy file '{POLICY_FILE}' not found")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in policy file: {e}")
        sys.exit(1)

    # Create IAM client
    session_kwargs = {}
    if profile:
        session_kwargs["profile_name"] = profile
        print(f"Using AWS profile: {profile}")

    session = boto3.Session(**session_kwargs)
    iam = session.client("iam")

    # Step 1: Create the policy
    print(f"Creating IAM policy '{POLICY_NAME}'...")
    policy_arn = f"arn:aws:iam::{ACCOUNT_ID}:policy/{POLICY_NAME}"
    
    try:
        response = iam.create_policy(
            PolicyName=POLICY_NAME,
            PolicyDocument=json.dumps(policy_document),
            Description="Grants zebra_day access to DynamoDB table and S3 backup buckets",
        )
        print(f"✓ Policy created: {response['Policy']['Arn']}")
        policy_arn = response["Policy"]["Arn"]
    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            print(f"⚠ Policy '{POLICY_NAME}' already exists, using existing policy")
            print(f"  ARN: {policy_arn}")
        else:
            print(f"ERROR creating policy: {e}")
            sys.exit(1)

    # Step 2: Attach policy to user
    print(f"\nAttaching policy to user '{USER_NAME}'...")
    try:
        iam.attach_user_policy(
            UserName=USER_NAME,
            PolicyArn=policy_arn,
        )
        print(f"✓ Policy attached to user '{USER_NAME}'")
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchEntity":
            print(f"ERROR: User '{USER_NAME}' does not exist")
            sys.exit(1)
        else:
            print(f"ERROR attaching policy: {e}")
            sys.exit(1)

    # Step 3: Verify attachment
    print(f"\nVerifying policy attachment...")
    try:
        response = iam.list_attached_user_policies(UserName=USER_NAME)
        attached_policies = response.get("AttachedPolicies", [])
        
        found = False
        for policy in attached_policies:
            if policy["PolicyName"] == POLICY_NAME:
                found = True
                print(f"✓ Policy '{POLICY_NAME}' is attached to '{USER_NAME}'")
                break
        
        if not found:
            print(f"⚠ WARNING: Policy not found in attached policies list")
        
        print(f"\nAll attached policies for '{USER_NAME}':")
        for policy in attached_policies:
            print(f"  - {policy['PolicyName']} ({policy['PolicyArn']})")
    except ClientError as e:
        print(f"ERROR verifying attachment: {e}")
        sys.exit(1)

    # Step 4: Wait for IAM propagation
    print(f"\n⏳ Waiting 60 seconds for IAM policy propagation...")
    time.sleep(60)
    print("✓ Wait complete")

    # Step 5: Test DynamoDB access
    print(f"\nTesting DynamoDB access to 'zebra-day-config' in us-west-2...")
    try:
        dynamodb = session.client("dynamodb", region_name="us-west-2")
        response = dynamodb.describe_table(TableName="zebra-day-config")
        print(f"✓ Successfully accessed table 'zebra-day-config'")
        print(f"  Status: {response['Table']['TableStatus']}")
        print(f"  Items: {response['Table']['ItemCount']}")
    except ClientError as e:
        if e.response["Error"]["Code"] == "AccessDeniedException":
            print(f"⚠ WARNING: Still getting AccessDeniedException")
            print(f"  This may indicate:")
            print(f"  1. IAM propagation needs more time (wait another 30-60s)")
            print(f"  2. AWS credentials are not using the 'daylily-service' user")
            print(f"  3. Additional permissions are needed")
        elif e.response["Error"]["Code"] == "ResourceNotFoundException":
            print(f"⚠ WARNING: Table 'zebra-day-config' does not exist in us-west-2")
            print(f"  Run: zday dynamo init --region us-west-2")
        else:
            print(f"ERROR testing DynamoDB access: {e}")
    except Exception as e:
        print(f"ERROR: {e}")

    print(f"\n{'='*60}")
    print(f"IAM policy setup complete!")
    print(f"{'='*60}")
    print(f"\nNext steps:")
    print(f"1. Test the GUI backend switch at https://localhost:8118/config")
    print(f"2. If still getting errors, wait another 30-60 seconds for IAM propagation")
    print(f"3. Verify AWS credentials are using the 'daylily-service' user:")
    print(f"   aws sts get-caller-identity")


if __name__ == "__main__":
    main()

