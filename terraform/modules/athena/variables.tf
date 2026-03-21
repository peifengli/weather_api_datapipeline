variable "project" {
  type = string
}

variable "environment" {
  type = string
}

variable "athena_results_bucket" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}
