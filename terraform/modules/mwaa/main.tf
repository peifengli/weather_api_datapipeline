resource "aws_s3_bucket" "mwaa" {
  bucket = "${var.project}-mwaa-${var.environment}"
  tags   = var.tags
}

resource "aws_s3_bucket_versioning" "mwaa" {
  bucket = aws_s3_bucket.mwaa.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_object" "requirements" {
  bucket = aws_s3_bucket.mwaa.id
  key    = "requirements.txt"
  source = "${path.root}/requirements.txt"
  etag   = filemd5("${path.root}/requirements.txt")
}

resource "aws_iam_role" "mwaa" {
  name = "${var.project}-mwaa-role-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = ["airflow.amazonaws.com", "airflow-env.amazonaws.com"] }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "mwaa" {
  name = "${var.project}-mwaa-policy-${var.environment}"
  role = aws_iam_role.mwaa.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject*", "s3:GetBucket*", "s3:List*"]
        Resource = ["${aws_s3_bucket.mwaa.arn}", "${aws_s3_bucket.mwaa.arn}/*"]
      },
      {
        Effect   = "Allow"
        Action   = ["glue:StartJobRun", "glue:GetJobRun", "glue:GetJobRuns", "glue:BatchStopJobRun"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents", "logs:GetLogEvents"]
        Resource = "arn:aws:logs:*:*:log-group:airflow-*"
      },
      {
        Effect   = "Allow"
        Action   = ["airflow:PublishMetrics"]
        Resource = "arn:aws:airflow:${var.region}:*:environment/${var.project}-${var.environment}"
      },
      {
        Effect   = "Allow"
        Action   = ["sqs:ChangeMessageVisibility", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:GetQueueUrl", "sqs:ReceiveMessage", "sqs:SendMessage"]
        Resource = "arn:aws:sqs:${var.region}:*:airflow-celery-*"
      },
      {
        Effect   = "Allow"
        Action   = ["kms:Decrypt", "kms:DescribeKey", "kms:GenerateDataKey*", "kms:Encrypt"]
        Resource = "*"
        Condition = {
          StringLike = {
            "kms:ViaService" = ["sqs.${var.region}.amazonaws.com"]
          }
        }
      }
    ]
  })
}

resource "aws_mwaa_environment" "this" {
  name              = "${var.project}-${var.environment}"
  airflow_version   = "2.9.2"
  environment_class = var.environment_class
  min_workers       = var.min_workers
  max_workers       = var.max_workers

  source_bucket_arn    = aws_s3_bucket.mwaa.arn
  dag_s3_path          = "dags/"
  requirements_s3_path = "requirements.txt"

  execution_role_arn = aws_iam_role.mwaa.arn

  network_configuration {
    security_group_ids = var.security_group_ids
    subnet_ids         = var.subnet_ids
  }

  logging_configuration {
    dag_processing_logs {
      enabled   = true
      log_level = "INFO"
    }
    scheduler_logs {
      enabled   = true
      log_level = "INFO"
    }
    task_logs {
      enabled   = true
      log_level = "INFO"
    }
    webserver_logs {
      enabled   = true
      log_level = "INFO"
    }
    worker_logs {
      enabled   = true
      log_level = "INFO"
    }
  }

  airflow_configuration_options = {
    "core.default_timezone"        = "utc"
    "core.load_examples"           = "false"
    "scheduler.catchup_by_default" = "false"
  }

  tags = var.tags
}
