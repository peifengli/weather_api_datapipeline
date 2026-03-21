resource "aws_s3_bucket" "raw" {
  bucket = "${var.project}-raw-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket" "processed" {
  bucket = "${var.project}-processed-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket" "athena_results" {
  bucket = "${var.project}-athena-results-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    id     = "expire-raw-after-90-days"
    status = "Enabled"
    filter {
      prefix = "weather/"
    }
    expiration {
      days = 90
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    id     = "expire-query-results"
    status = "Enabled"
    expiration {
      days = 7
    }
  }
}
