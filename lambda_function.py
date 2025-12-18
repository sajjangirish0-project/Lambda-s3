import boto3
import os
from PIL import Image
from io import BytesIO
from datetime import datetime

s3 = boto3.client("s3")
dynamodb = boto3.resource("dynamodb")

def lambda_handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']

    response = s3.get_object(Bucket=bucket, Key=key)
    image = Image.open(response['Body'])

    image.thumbnail((100, 100))

    buffer = BytesIO()
    image.save(buffer, "JPEG")
    buffer.seek(0)

    thumbnail_bucket = os.environ["THUMBNAIL_BUCKET"]
    s3.put_object(
        Bucket=thumbnail_bucket,
        Key=key,
        Body=buffer,
        ContentType="image/jpeg"
    )

    table = dynamodb.Table(os.environ["DYNAMODB_TABLE"])
    table.put_item(
        Item={
            "ImageName": key,
            "ImageSize": response["ContentLength"],
            "CreationDate": datetime.utcnow().isoformat()
        }
    )

    return {
        "statusCode": 200,
        "body": "Thumbnail created successfully"
    }
