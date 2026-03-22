# =============================================================================
# ECS Fargate + ALB — Streamlit dashboard
#
# ALB (port 80 HTTP) → ECS Fargate task (port 8501)
# ALB natively supports WebSocket upgrade forwarding (unlike App Runner).
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

# ── Default VPC + subnets ─────────────────────────────────────────────────────

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "defaultForAz"
    values = ["true"]
  }
}

# ── Security groups ───────────────────────────────────────────────────────────

resource "aws_security_group" "alb" {
  name   = "${var.project}-alb-${var.environment}"
  vpc_id = data.aws_vpc.default.id

  ingress {
    description = "HTTP from internet"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

resource "aws_security_group" "ecs" {
  name   = "${var.project}-ecs-${var.environment}"
  vpc_id = data.aws_vpc.default.id

  ingress {
    description     = "Streamlit port from ALB only"
    from_port       = 8501
    to_port         = 8501
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.tags
}

# ── ALB ───────────────────────────────────────────────────────────────────────

resource "aws_lb" "main" {
  name               = "${var.project}-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb.id]
  subnets            = data.aws_subnets.default.ids

  # Keep WebSocket connections alive for up to 1 hour of idle time
  idle_timeout = 3600

  tags = var.tags
}

resource "aws_lb_target_group" "streamlit" {
  name        = "${var.project}-tg-${var.environment}"
  port        = 8501
  protocol    = "HTTP"
  vpc_id      = data.aws_vpc.default.id
  target_type = "ip"

  health_check {
    path                = "/_stcore/health"
    protocol            = "HTTP"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    interval            = 30
    timeout             = 10
  }

  # Sticky sessions required: each browser's WebSocket must stay on the same task
  stickiness {
    type    = "lb_cookie"
    enabled = true
  }

  tags = var.tags
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.main.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.streamlit.arn
  }
}

# ── IAM ───────────────────────────────────────────────────────────────────────

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# Execution role: ECS agent uses this to pull ECR image + ship logs
resource "aws_iam_role" "execution" {
  name               = "${var.project}-ecs-execution-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Task role: permissions the running container has (S3 + Secrets Manager)
resource "aws_iam_role" "task" {
  name               = "${var.project}-ecs-task-${var.environment}"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "task_s3" {
  name = "s3-secrets-read"
  role = aws_iam_role.task.id
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

# ── CloudWatch Logs ───────────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "streamlit" {
  name              = "/ecs/${var.project}-streamlit-${var.environment}"
  retention_in_days = 7
  tags              = var.tags
}

# ── ECS cluster + service ─────────────────────────────────────────────────────

resource "aws_ecs_cluster" "main" {
  name = "${var.project}-${var.environment}"
  tags = var.tags
}

resource "aws_ecs_task_definition" "streamlit" {
  family                   = "${var.project}-streamlit-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name  = "streamlit"
    image = "${aws_ecr_repository.streamlit.repository_url}:latest"

    portMappings = [{
      containerPort = 8501
      protocol      = "tcp"
    }]

    environment = [
      { name = "ENVIRONMENT",         value = var.environment },
      { name = "S3_PROCESSED_BUCKET", value = "${var.project}-processed-${var.environment}" },
      { name = "AWS_DEFAULT_REGION",  value = var.aws_region },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.streamlit.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "streamlit"
      }
    }

    essential = true
  }])

  tags = var.tags
}

resource "aws_ecs_service" "streamlit" {
  name            = "${var.project}-streamlit-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.streamlit.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Allow time for Streamlit to start before ALB health checks kick in
  health_check_grace_period_seconds = 60

  network_configuration {
    subnets          = data.aws_subnets.default.ids
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.streamlit.arn
    container_name   = "streamlit"
    container_port   = 8501
  }

  depends_on = [aws_lb_listener.http]

  tags = var.tags
}
