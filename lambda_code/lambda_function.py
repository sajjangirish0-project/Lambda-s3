# Create a Lambda that logs EVERYTHING
import boto3
import json
import os
import sys
import urllib.parse
import traceback
from datetime import datetime
from io import BytesIO

print("=== FULL DEBUG LAMBDA ===")
print(f"Python: {sys.version}")
print(f"Current dir: {os.listdir('.')}")
print(f"Environment: {dict(os.environ)}")

# Try to import Pillow
try:
    from PIL import Image
    PILLOW_AVAILABLE = True
    print(f"✅ Pillow available: {Image.__version__}")
except ImportError as e:
    PILLOW_AVAILABLE = False
    print(f"❌ Pillow NOT available: {e}")

s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def lambda_handler(event, context):
    print("\n" + "="*80)
    print("🚀 LAMBDA INVOKED")
    print(f"Event type: {type(event)}")
    print(f"Event keys: {list(event.keys()) if isinstance(event, dict) else 'Not a dict'}")
    
    # Log the full event but truncated
    event_str = json.dumps(event, indent=2, default=str)
    if len(event_str) > 1000:
        print("Event (truncated):", event_str[:1000] + "...")
    else:
        print("Event:", event_str)
    
    # Get environment variables
    THUMBNAIL_BUCKET = os.environ.get('THUMBNAIL_BUCKET')
    DYNAMODB_TABLE = os.environ.get('DYNAMODB_TABLE')
    
    print(f"\n📊 ENVIRONMENT VARIABLES:")
    print(f"  THUMBNAIL_BUCKET: {THUMBNAIL_BUCKET}")
    print(f"  DYNAMODB_TABLE: {DYNAMODB_TABLE}")
    
    if not THUMBNAIL_BUCKET or not DYNAMODB_TABLE:
        print("❌ CRITICAL: Missing environment variables!")
        return {
            'statusCode': 500,
            'body': json.dumps('Missing environment variables')
        }
    
    if not PILLOW_AVAILABLE:
        print("❌ CRITICAL: Pillow not available!")
        return {
            'statusCode': 500,
            'body': json.dumps('Pillow library not available')
        }
    
    # Check if this is an S3 event
    if 'Records' not in event or not event['Records']:
        print("⚠️ No Records in event, not an S3 event")
        return {'statusCode': 200, 'body': 'Not an S3 event'}
    
    for i, record in enumerate(event.get('Records', [])):
        print(f"\n📋 Processing Record {i+1}")
        
        if 's3' not in record:
            print("⚠️ Not an S3 record, skipping")
            continue
        
        try:
            bucket = record['s3']['bucket']['name']
            key = record['s3']['object']['key']
            
            print(f"📥 Raw key from event: '{key}'")
            
            # URL decode
            decoded_key = urllib.parse.unquote_plus(key)
            print(f"🔓 Decoded key: '{decoded_key}'")
            key = decoded_key
            
            print(f"🎯 Target: s3://{bucket}/{key}")
            
            # STEP 1: Check if file exists
            print("\n1. 🔍 Checking if file exists...")
            try:
                head_resp = s3.head_object(Bucket=bucket, Key=key)
                print(f"   ✅ File exists: {key}")
                print(f"   📏 Size: {head_resp['ContentLength']} bytes")
            except Exception as e:
                print(f"   ❌ File not found: {e}")
                print("   Listing bucket for debugging:")
                resp = s3.list_objects_v2(Bucket=bucket, MaxKeys=5)
                if 'Contents' in resp:
                    for obj in resp['Contents']:
                        print(f"     - {obj['Key']}")
                continue
            
            # STEP 2: Download file
            print("\n2. ⬇️ Downloading file...")
            try:
                response = s3.get_object(Bucket=bucket, Key=key)
                image_data = response['Body'].read()
                file_size = len(image_data)
                print(f"   ✅ Downloaded: {file_size} bytes")
            except Exception as e:
                print(f"   ❌ Download failed: {e}")
                continue
            
            # STEP 3: Create thumbnail
            print("\n3. 🖼️ Creating thumbnail...")
            try:
                image = Image.open(BytesIO(image_data))
                print(f"   📐 Original size: {image.size}")
                print(f"   🎨 Mode: {image.mode}")
                print(f"   📁 Format: {image.format}")
                
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
                elif image.mode != 'RGB':
                    image = image.convert('RGB')
                
                image.thumbnail((100, 100))
                print(f"   📐 Thumbnail size: {image.size}")
                
                buffer = BytesIO()
                image.save(buffer, 'JPEG', quality=85)
                thumbnail_data = buffer.getvalue()
                print(f"   ✅ Thumbnail created: {len(thumbnail_data)} bytes")
                
            except Exception as e:
                print(f"   ❌ Thumbnail creation failed: {e}")
                traceback.print_exc()
                continue
            
            # STEP 4: Upload to thumbnail bucket
            print("\n4. ⬆️ Uploading thumbnail...")
            thumbnail_key = f"thumbnails/{key.replace(' ', '-')}.jpg"
            thumbnail_key = thumbnail_key.replace('//', '/')
            
            print(f"   📍 Thumbnail path: {thumbnail_key}")
            print(f"   🪣 Target bucket: {THUMBNAIL_BUCKET}")
            
            try:
                # Check if we can write to thumbnail bucket
                print("   🔍 Checking thumbnail bucket access...")
                try:
                    s3.head_bucket(Bucket=THUMBNAIL_BUCKET)
                    print("   ✅ Thumbnail bucket exists")
                except Exception as e:
                    print(f"   ❌ Cannot access thumbnail bucket: {e}")
                
                # Attempt upload
                print("   📤 Attempting upload...")
                s3.put_object(
                    Bucket=THUMBNAIL_BUCKET,
                    Key=thumbnail_key,
                    Body=thumbnail_data,
                    ContentType='image/jpeg'
                )
                print(f"   ✅ Upload SUCCESSFUL!")
                
                # Verify upload
                verify = s3.head_object(Bucket=THUMBNAIL_BUCKET, Key=thumbnail_key)
                print(f"   🔍 Verification: {verify['ContentLength']} bytes uploaded")
                
            except Exception as e:
                print(f"   ❌ Upload FAILED: {e}")
                print(f"   Error type: {type(e).__name__}")
                traceback.print_exc()
                
                # Test with a simple text file to check permissions
                print("   🧪 Testing permissions with text file...")
                try:
                    s3.put_object(
                        Bucket=THUMBNAIL_BUCKET,
                        Key="permission-test.txt",
                        Body=b"test",
                        ContentType='text/plain'
                    )
                    print("   ✅ Permission test PASSED")
                    s3.delete_object(Bucket=THUMBNAIL_BUCKET, Key="permission-test.txt")
                except Exception as perm_error:
                    print(f"   ❌ Permission test FAILED: {perm_error}")
                continue
            
            # STEP 5: Save to DynamoDB
            print("\n5. 💾 Saving metadata to DynamoDB...")
            try:
                table = dynamodb.Table(DYNAMODB_TABLE)
                
                # Check if table exists
                try:
                    table.load()
                    print("   ✅ DynamoDB table exists")
                except Exception as e:
                    print(f"   ❌ DynamoDB table error: {e}")
                
                item = {
                    'ImageName': key,
                    'ImageSize': str(file_size),
                    'CreationDate': response['LastModified'].isoformat(),
                    'ProcessedDate': datetime.now().isoformat(),
                    'ThumbnailKey': thumbnail_key
                }
                
                table.put_item(Item=item)
                print(f"   ✅ Metadata saved: {json.dumps(item, indent=2)}")
                
            except Exception as e:
                print(f"   ❌ DynamoDB save failed: {e}")
                traceback.print_exc()
            
            print(f"\n🎉 🎉 🎉 COMPLETE SUCCESS! 🎉 🎉 🎉")
            print(f"   Original: s3://{bucket}/{key}")
            print(f"   Thumbnail: s3://{THUMBNAIL_BUCKET}/{thumbnail_key}")
            
        except Exception as e:
            print(f"\n💥 UNEXPECTED ERROR in record processing: {e}")
            traceback.print_exc()
    
    print("\n" + "="*80)
    print("✅ LAMBDA EXECUTION FINISHED")
    return {
        'statusCode': 200,
        'body': json.dumps('Processing completed')
    }