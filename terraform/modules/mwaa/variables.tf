variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "region" {
  type    = string
  default = "us-east-1"
}

variable "environment_class" {
  type        = string
  default     = "mw1.small"
  description = "mw1.small (~$0.49/hr), mw1.medium, mw1.large"
}

variable "min_workers" {
  type    = number
  default = 1
}

variable "max_workers" {
  type    = number
  default = 3
}

variable "subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs (MWAA requires at least 2 in different AZs)"
}

variable "security_group_ids" {
  type = list(string)
}

variable "tags" {
  type    = map(string)
  default = {}
}
