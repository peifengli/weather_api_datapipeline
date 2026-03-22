output "service_url" {
  description = "ALB DNS URL for the Streamlit dashboard (HTTP)"
  value       = "http://${aws_lb.main.dns_name}"
}

output "ecr_repository_url" {
  description = "ECR repository URL for pushing the Streamlit Docker image"
  value       = aws_ecr_repository.streamlit.repository_url
}

output "cluster_name" {
  description = "ECS cluster name (used for force-new-deployment in CD)"
  value       = aws_ecs_cluster.main.name
}

output "service_name" {
  description = "ECS service name (used for force-new-deployment in CD)"
  value       = aws_ecs_service.streamlit.name
}
