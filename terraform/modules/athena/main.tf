resource "aws_athena_workgroup" "weather" {
  name = "${var.project}-${var.environment}"
  configuration {
    result_configuration {
      output_location = "s3://${var.athena_results_bucket}/athena-results/"
      encryption_configuration {
        encryption_option = "SSE_S3"
      }
    }
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true
    bytes_scanned_cutoff_per_query     = 1073741824 # 1 GB safety limit
  }
  tags = var.tags
}

resource "aws_athena_database" "weather" {
  name          = "${var.project}_${var.environment}"
  bucket        = var.athena_results_bucket
  force_destroy = true
}
