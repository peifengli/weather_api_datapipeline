output "streamlit_url" {
  description = "ALB URL of the Streamlit dashboard"
  value       = module.ecs.service_url
}

output "streamlit_ecr_url" {
  description = "ECR repository URL for the Streamlit Docker image"
  value       = module.ecs.ecr_repository_url
}
