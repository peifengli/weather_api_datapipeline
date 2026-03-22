output "streamlit_url" {
  description = "Public HTTPS URL of the Streamlit dashboard"
  value       = module.apprunner.service_url
}

output "streamlit_ecr_url" {
  description = "ECR repository URL for the Streamlit Docker image"
  value       = module.apprunner.ecr_repository_url
}
