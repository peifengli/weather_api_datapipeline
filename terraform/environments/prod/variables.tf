variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "enable_scheduler" {
  description = "Set to false to disable EventBridge scheduling (stops Glue runs to save cost)"
  type        = bool
  default     = true
}

variable "ecs_desired_count" {
  description = "Number of ECS task replicas. Set to 0 to soft-stop the Streamlit dashboard."
  type        = number
  default     = 1
}
