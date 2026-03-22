variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "enable_scheduler" {
  description = "Set to false to disable EventBridge scheduling (stops hourly Glue runs in dev to save cost)"
  type        = bool
  default     = true
}
