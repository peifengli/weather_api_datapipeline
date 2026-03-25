variable "project" {
  description = "Project name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, prod)"
  type        = string
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "desired_count" {
  description = "Number of ECS task replicas. Set to 0 to scale to zero (stops Fargate billing while preserving infra state)."
  type        = number
  default     = 1
}
