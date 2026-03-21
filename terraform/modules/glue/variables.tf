variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "glue_role_arn" {
  type = string
}

variable "scripts_bucket" {
  type = string
}

variable "s3_raw_bucket" {
  type = string
}

variable "s3_processed_bucket" {
  type = string
}

variable "secret_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
