output "service_url" {
  description = "Public HTTPS URL for the Streamlit dashboard"
  value       = "https://${aws_apprunner_service.streamlit.service_url}"
}

output "ecr_repository_url" {
  description = "ECR repository URL — push images here to trigger auto-deploy"
  value       = aws_ecr_repository.streamlit.repository_url
}

output "service_arn" {
  value = aws_apprunner_service.streamlit.arn
}
