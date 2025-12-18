import boto3
import json
import os
from datetime import datetime
from io import BytesIO
from PIL import Image

print("✅ Lambda with Pillow - Ready!")

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    THUMBNAIL_BUCKET = os.environ['THUMBNAIL_BUCKET']
    DYNAMODB_TABLE = os.environ['DYNAMODB_TABLE']
    
    for record in event.get('Records', []):
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        
        print(f"Processing: {key}")
        
        # Download
        response = s3.get_object(Bucket=bucket, Key=key)
        image_bytes = response['Body'].read()
        
        # Create thumbnail
        img = Image.open(BytesIO(image_bytes))
        if img.mode != 'RGB':
            img = img.convert('RGB')
        img.thumbnail((100, 100))
        
        buffer = BytesIO()
        img.save(buffer, 'JPEG')
        
        # Upload thumbnail
        thumbnail_key = f"thumb-{key}"
        s3.put_object(
            Bucket=THUMBNAIL_BUCKET,
            Key=thumbnail_key,
            Body=buffer.getvalue(),
            ContentType='image/jpeg'
        )
        
        # Save metadata
        table = dynamodb.Table(DYNAMODB_TABLE)
        table.put_item(Item={
            'ImageName': key,
            'ImageSize': str(len(image_bytes)),
            'CreationDate': response['LastModified'].isoformat(),
            'ProcessedDate': datetime.now().isoformat()
        })
    
    return {'statusCode': 200}
