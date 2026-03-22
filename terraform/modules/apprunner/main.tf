# =============================================================================
# App Runner — Streamlit dashboard
#
# Lightweight (~$2–5/month at low traffic). App Runner manages HTTPS,
# scaling, and health checks. Image is pulled from ECR; auto-deploys on push.
#
# IAM instance role gives the running container read access to:
#   - s3://weatherdata-processed-{env}/** (DuckDB httpfs queries)
#   - Secrets Manager (API key, if needed by dashboard)
# =============================================================================

# ── ECR repository ────────────────────────────────────────────────────────────

resource "aws_ecr_repository" "streamlit" {
  name                 = "${var.project}-streamlit-${var.environment}"
  image_tag_mutability = "MUTABLE"
  force_delete         = true
  tags                 = var.tags
}

resource "aws_ecr_lifecycle_policy" "streamlit" {
  repository = aws_ecr_repository.streamlit.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 5 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 5
      }
      action = { type = "expire" }
    }]
  })
}

# ── IAM: instance role (permissions the container has at runtime) ─────────────

resource "aws_iam_role" "instance" {
  name = "${var.project}-streamlit-instance-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "tasks.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy" "instance_s3" {
  name = "s3-read"
  role = aws_iam_role.instance.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["s3:GetObject", "s3:ListBucket"]
        Resource = [
          "arn:aws:s3:::${var.project}-processed-${var.environment}",
          "arn:aws:s3:::${var.project}-processed-${var.environment}/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "secretsmanager:GetSecretValue"
        Resource = "arn:aws:secretsmanager:${var.aws_region}:*:secret:weather-api-key-${var.environment}*"
      },
    ]
  })
}

# ── IAM: access role (used by App Runner to pull from ECR) ───────────────────

resource "aws_iam_role" "access" {
  name = "${var.project}-streamlit-access-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "build.apprunner.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "ecr_access" {
  role       = aws_iam_role.access.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSAppRunnerServicePolicyForECRAccess"
}

# ── App Runner service ─────────────────────────────────────────────────────────

resource "aws_apprunner_service" "streamlit" {
  service_name = "${var.project}-streamlit-${var.environment}"

  source_configuration {
    authentication_configuration {
      access_role_arn = aws_iam_role.access.arn
    }
    image_repository {
      image_identifier      = "${aws_ecr_repository.streamlit.repository_url}:latest"
      image_repository_type = "ECR"
      image_configuration {
        port = "8501"
        runtime_environment_variables = {
          ENVIRONMENT         = var.environment
          S3_PROCESSED_BUCKET = "${var.project}-processed-${var.environment}"
          AWS_DEFAULT_REGION  = var.aws_region
        }
      }
    }
    auto_deployments_enabled = true
  }

  instance_configuration {
    instance_role_arn = aws_iam_role.instance.arn
    cpu               = "0.25 vCPU"
    memory            = "0.5 GB"
  }

  health_check_configuration {
    protocol            = "HTTP"
    path                = "/_stcore/health"
    interval            = 10
    timeout             = 5
    healthy_threshold   = 1
    unhealthy_threshold = 5
  }

  tags = var.tags
}
