output "workflow_name" {
  description = "Name of the Glue Workflow"
  value       = aws_glue_workflow.pipeline.name
}

output "lambda_function_name" {
  description = "Name of the trigger Lambda function"
  value       = aws_lambda_function.trigger.function_name
}

output "lambda_function_arn" {
  description = "ARN of the trigger Lambda function"
  value       = aws_lambda_function.trigger.arn
}

output "schedule_name" {
  description = "Name of the EventBridge schedule (empty string when scheduler is disabled)"
  value       = var.enabled ? aws_scheduler_schedule.hourly[0].name : ""
}
