variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "s3_bucket_arns" {
  type = list(string)
}

variable "secret_arn" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
