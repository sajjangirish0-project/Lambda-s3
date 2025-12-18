terraform {
  required_version = ">= 1.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.5"
    }
  }
}

provider "aws" {
  region = "us-east-2"
}

# -------------------------------------------------
# Random suffix for global uniqueness
# -------------------------------------------------
resource "random_string" "suffix" {
  length  = 8
  upper   = false
  special = false
}

locals {
  suffix = random_string.suffix.result
}

# -------------------------------------------------
# S3 Buckets
# -------------------------------------------------
resource "aws_s3_bucket" "source_images" {
  bucket = "source-images-bucket-${local.suffix}"

  tags = {
    Name = "Source Images"
  }
}

resource "aws_s3_bucket" "thumbnails" {
  bucket = "thumbnails-bucket-${local.suffix}"

  tags = {
    Name = "Thumbnails"
  }
}

resource "aws_s3_bucket_versioning" "source_images" {
  bucket = aws_s3_bucket.source_images.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_versioning" "thumbnails" {
  bucket = aws_s3_bucket.thumbnails.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "source_images" {
  bucket                  = aws_s3_bucket.source_images.id
  block_public_acls        = true
  block_public_policy      = true
  ignore_public_acls       = true
  restrict_public_buckets  = true
}

resource "aws_s3_bucket_public_access_block" "thumbnails" {
  bucket                  = aws_s3_bucket.thumbnails.id
  block_public_acls        = true
  block_public_policy      = true
  ignore_public_acls       = true
  restrict_public_buckets  = true
}

# -------------------------------------------------
# DynamoDB Table
# -------------------------------------------------
resource "aws_dynamodb_table" "image_metadata" {
  name         = "ImageMetadata-${local.suffix}"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ImageName"

  attribute {
    name = "ImageName"
    type = "S"
  }
}

# -------------------------------------------------
# IAM Role for Lambda
# -------------------------------------------------
resource "aws_iam_role" "lambda_role" {
  name = "thumbnail-lambda-role-${local.suffix}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_policy" "lambda_policy" {
  name = "thumbnail-lambda-policy-${local.suffix}"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # CloudWatch Logs permissions
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      },
      # Source bucket READ permissions
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:HeadObject"
        ]
        Resource = [
          aws_s3_bucket.source_images.arn,
          "${aws_s3_bucket.source_images.arn}/*"
        ]
      },
      # Thumbnail bucket FULL permissions (CRITICAL FIX)
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:PutObjectAcl",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:HeadBucket",
          "s3:HeadObject",
          "s3:DeleteObject"  # Optional, for cleanup
        ]
        Resource = [
          aws_s3_bucket.thumbnails.arn,
          "${aws_s3_bucket.thumbnails.arn}/*"
        ]
      },
      # DynamoDB permissions
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:UpdateItem",
          "dynamodb:DescribeTable"
        ]
        Resource = aws_dynamodb_table.image_metadata.arn
      }
    ]
  })
}
resource "aws_iam_role_policy_attachment" "lambda_attach" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_policy.arn
}



# -------------------------------------------------
# Lambda Function
# -------------------------------------------------
resource "aws_lambda_function" "thumbnail_generator" {
  function_name = "thumbnail-generator-${local.suffix}"
  role          = aws_iam_role.lambda_role.arn
  runtime       = "python3.9"
  handler       = "lambda_function.lambda_handler"
  filename      = "thumbnail_generator.zip"

  source_code_hash = filebase64sha256("thumbnail_generator.zip")

  timeout     = 30
  memory_size = 512

  environment {
    variables = {
      THUMBNAIL_BUCKET = aws_s3_bucket.thumbnails.bucket
      DYNAMODB_TABLE   = aws_dynamodb_table.image_metadata.name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_attach
  ]
}

# -------------------------------------------------
# Allow S3 to Invoke Lambda
# -------------------------------------------------
resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowS3Invoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.thumbnail_generator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.source_images.arn
}

# -------------------------------------------------
# S3 Event Notification
# -------------------------------------------------
resource "aws_s3_bucket_notification" "trigger_lambda" {
  bucket = aws_s3_bucket.source_images.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.thumbnail_generator.arn
    events              = ["s3:ObjectCreated:Put"]
  }

  depends_on = [
    aws_lambda_permission.allow_s3
  ]
}

# -------------------------------------------------
# Outputs
# -------------------------------------------------
output "source_bucket" {
  value = aws_s3_bucket.source_images.bucket
}

output "thumbnail_bucket" {
  value = aws_s3_bucket.thumbnails.bucket
}

output "lambda_function" {
  value = aws_lambda_function.thumbnail_generator.function_name
}

output "dynamodb_table" {
  value = aws_dynamodb_table.image_metadata.name
}
