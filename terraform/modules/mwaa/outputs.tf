output "mwaa_bucket_name" { value = aws_s3_bucket.mwaa.bucket }
output "mwaa_bucket_arn" { value = aws_s3_bucket.mwaa.arn }
output "webserver_url" { value = aws_mwaa_environment.this.webserver_url }
output "mwaa_role_arn" { value = aws_iam_role.mwaa.arn }
