variable "project" {
  description = "Project name prefix for all resources"
  type        = string
}

variable "environment" {
  description = "Deployment environment (dev, prod)"
  type        = string
}

variable "region" {
  description = "AWS region"
  type        = string
}

variable "fetch_job_name" {
  description = "Name of the Glue fetch job"
  type        = string
}

variable "process_job_name" {
  description = "Name of the Glue process job"
  type        = string
}

variable "tags" {
  description = "Tags to apply to all resources"
  type        = map(string)
  default     = {}
}

variable "enabled" {
  description = "Set to false to disable the EventBridge schedule (pauses hourly Glue runs to save cost)"
  type        = bool
  default     = true
}

variable "schedule_expression" {
  description = "EventBridge schedule rate expression, e.g. 'rate(15 minutes)' or 'rate(30 minutes)'"
  type        = string
  default     = "rate(15 minutes)"
}
