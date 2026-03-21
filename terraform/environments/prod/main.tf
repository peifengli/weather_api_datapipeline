terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = { source = "hashicorp/aws"
    version = "~> 5.0" }
  }
  backend "s3" {
    bucket = "weatherdata-terraform-state"
    key    = "prod/terraform.tfstate"
    region = "us-east-1"
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  project     = "weatherdata"
  environment = "prod"
  tags = {
    Project     = local.project
    Environment = local.environment
    ManagedBy   = "terraform"
  }
}

module "s3" {
  source      = "../../modules/s3"
  project     = local.project
  environment = local.environment
  tags        = local.tags
}

module "iam" {
  source      = "../../modules/iam"
  project     = local.project
  environment = local.environment
  s3_bucket_arns = [
    module.s3.raw_bucket_arn,
    module.s3.processed_bucket_arn,
  ]
  secret_arn = aws_secretsmanager_secret.weather_api_key.arn
  tags       = local.tags
}

module "glue" {
  source              = "../../modules/glue"
  project             = local.project
  environment         = local.environment
  glue_role_arn       = module.iam.glue_role_arn
  scripts_bucket      = module.s3.raw_bucket_name
  s3_raw_bucket       = module.s3.raw_bucket_name
  s3_processed_bucket = module.s3.processed_bucket_name
  secret_name         = aws_secretsmanager_secret.weather_api_key.name
  tags                = local.tags
}

module "athena" {
  source                = "../../modules/athena"
  project               = local.project
  environment           = local.environment
  athena_results_bucket = module.s3.athena_results_bucket_name
  tags                  = local.tags
}

resource "aws_secretsmanager_secret" "weather_api_key" {
  name = "weather-api-key-${local.environment}"
  tags = local.tags
}

# Import blocks — bring pre-existing resources into state without recreating them
import {
  to = module.athena.aws_athena_database.weather
  id = "weatherdata_prod"
}
