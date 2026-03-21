resource "aws_glue_catalog_database" "weather" {
  name = "${var.project}_${var.environment}"
}

resource "aws_s3_object" "fetch_script" {
  bucket = var.scripts_bucket
  key    = "glue-scripts/fetch_weather.py"
  source = "${path.root}/../../src/glue/fetch_weather.py"
  etag   = filemd5("${path.root}/../../src/glue/fetch_weather.py")
}

resource "aws_s3_object" "process_script" {
  bucket = var.scripts_bucket
  key    = "glue-scripts/process_weather.py"
  source = "${path.root}/../../src/glue/process_weather.py"
  etag   = filemd5("${path.root}/../../src/glue/process_weather.py")
}

resource "aws_glue_job" "fetch_weather" {
  name         = "fetch_weather"
  role_arn     = var.glue_role_arn
  glue_version = "4.0"
  command {
    name            = "pythonshell"
    python_version  = "3.9"
    script_location = "s3://${var.scripts_bucket}/glue-scripts/fetch_weather.py"
  }
  default_arguments = {
    "--S3_RAW_BUCKET" = var.s3_raw_bucket
    "--SECRET_NAME"   = var.secret_name
    "--ENVIRONMENT"   = var.environment
    "--extra-py-files" = "s3://${var.scripts_bucket}/glue-scripts/src.zip"
    "--job-bookmark-option" = "job-bookmark-disable"
  }
  max_capacity = 0.0625  # 1/16 DPU (cheapest Python shell)
  tags = var.tags
}

resource "aws_glue_job" "process_weather" {
  name         = "process_weather"
  role_arn     = var.glue_role_arn
  glue_version = "4.0"
  command {
    name            = "pythonshell"
    python_version  = "3.9"
    script_location = "s3://${var.scripts_bucket}/glue-scripts/process_weather.py"
  }
  default_arguments = {
    "--S3_RAW_BUCKET"       = var.s3_raw_bucket
    "--S3_PROCESSED_BUCKET" = var.s3_processed_bucket
    "--ENVIRONMENT"         = var.environment
    "--extra-py-files"      = "s3://${var.scripts_bucket}/glue-scripts/src.zip"
    "--job-bookmark-option" = "job-bookmark-disable"
  }
  max_capacity = 0.0625
  tags = var.tags
}

resource "aws_glue_crawler" "weather" {
  name          = "${var.project}-crawler-${var.environment}"
  role          = var.glue_role_arn
  database_name = aws_glue_catalog_database.weather.name
  s3_target {
    path = "s3://${var.s3_processed_bucket}/weather/"
  }
  schedule = "cron(10 * * * ? *)"  # 10 minutes past every hour
  tags     = var.tags
}
