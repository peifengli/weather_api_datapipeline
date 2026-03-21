# =============================================================================
# EventBridge Scheduler → Lambda → Glue Workflow
# Replaces MWAA for near-zero cost hourly pipeline orchestration.
#
# Execution chain (all serverless, no always-on infra):
#   EventBridge Scheduler (cron)
#     → Lambda (trigger_pipeline)
#       → Glue Workflow: fetch_weather_{env}
#                          └─(on success)→ process_weather_{env}
# =============================================================================

# ── Glue Workflow ─────────────────────────────────────────────────────────────

resource "aws_glue_workflow" "pipeline" {
  name = "weather-pipeline-${var.environment}"
  tags = var.tags
}

resource "aws_glue_trigger" "start_fetch" {
  name          = "weather-start-${var.environment}"
  type          = "ON_DEMAND"
  workflow_name = aws_glue_workflow.pipeline.name

  actions {
    job_name = var.fetch_job_name
  }

  tags = var.tags
}

resource "aws_glue_trigger" "process_after_fetch" {
  name          = "weather-process-${var.environment}"
  type          = "CONDITIONAL"
  workflow_name = aws_glue_workflow.pipeline.name

  predicate {
    conditions {
      job_name = var.fetch_job_name
      state    = "SUCCEEDED"
    }
  }

  actions {
    job_name = var.process_job_name
  }

  tags = var.tags
}

# ── Lambda ────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name               = "${var.project}-pipeline-trigger-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic" {
  role       = aws_iam_role.lambda.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_policy" "lambda_glue" {
  name = "${var.project}-lambda-glue-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["glue:StartWorkflowRun", "glue:GetWorkflowRun", "glue:GetWorkflow"]
      Resource = "arn:aws:glue:${var.region}:*:workflow/weather-pipeline-${var.environment}"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "lambda_glue" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda_glue.arn
}

data "archive_file" "lambda_zip" {
  type        = "zip"
  source_file = "${path.root}/src/lambda/trigger_pipeline.py"
  output_path = "${path.module}/trigger_pipeline.zip"
}

resource "aws_lambda_function" "trigger" {
  function_name    = "${var.project}-pipeline-trigger-${var.environment}"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  role             = aws_iam_role.lambda.arn
  handler          = "trigger_pipeline.handler"
  runtime          = "python3.11"
  timeout          = 30

  environment {
    variables = {
      ENVIRONMENT        = var.environment
      AWS_DEFAULT_REGION = var.region
    }
  }

  tags = var.tags
}

# ── EventBridge Scheduler ─────────────────────────────────────────────────────

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project}-scheduler-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = var.tags
}

resource "aws_iam_policy" "scheduler_invoke" {
  name = "${var.project}-scheduler-invoke-${var.environment}"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = aws_lambda_function.trigger.arn
    }]
  })
}

resource "aws_iam_role_policy_attachment" "scheduler_invoke" {
  role       = aws_iam_role.scheduler.name
  policy_arn = aws_iam_policy.scheduler_invoke.arn
}

resource "aws_scheduler_schedule" "hourly" {
  name       = "weather-pipeline-hourly-${var.environment}"
  group_name = "default"

  flexible_time_window {
    mode = "OFF"
  }

  # 5 minutes past every hour
  schedule_expression          = "cron(5 * * * ? *)"
  schedule_expression_timezone = "UTC"

  target {
    arn      = aws_lambda_function.trigger.arn
    role_arn = aws_iam_role.scheduler.arn
  }
}
