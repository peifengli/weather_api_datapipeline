#!/usr/bin/env bash
# aws_teardown.sh ENV
# Deletes every AWS resource deployed by this pipeline for the given environment.
# Works even when Terraform state is empty or out of sync.
# Usage: ./scripts/aws_teardown.sh dev
#        ./scripts/aws_teardown.sh prod
set -euo pipefail

ENV="${1:-}"
if [[ -z "$ENV" || ( "$ENV" != "dev" && "$ENV" != "prod" ) ]]; then
  echo "Usage: $0 <dev|prod>"
  exit 1
fi

P="weatherdata"   # project prefix
REGION="${AWS_DEFAULT_REGION:-us-east-1}"

ok()   { echo "  ✓ $*"; }
skip() { echo "  - $* (not found or already gone)"; }
run()  { "$@" 2>/dev/null && ok "$*" || skip "$*"; }

echo ""
echo "========================================================"
echo " Tearing down ALL AWS resources for environment: $ENV"
echo "========================================================"

# ── 1. EventBridge schedule ───────────────────────────────────────────────────
echo ""
echo "[ EventBridge Scheduler ]"
run aws scheduler delete-schedule \
  --name "weather-pipeline-hourly-${ENV}" \
  --group-name default \
  --no-cli-pager

# ── 2. Lambda ─────────────────────────────────────────────────────────────────
echo ""
echo "[ Lambda ]"
run aws lambda delete-function \
  --function-name "${P}-pipeline-trigger-${ENV}" \
  --no-cli-pager

# ── 3. Glue triggers, workflow, jobs, crawler, catalog database ───────────────
echo ""
echo "[ Glue ]"
# Triggers must be deleted before workflow
for trigger in "weather-start-${ENV}" "weather-process-${ENV}"; do
  run aws glue delete-trigger --name "$trigger" --no-cli-pager
done
run aws glue delete-workflow --name "weather-pipeline-${ENV}" --no-cli-pager
run aws glue delete-job      --job-name "fetch_weather_${ENV}"   --no-cli-pager
run aws glue delete-job      --job-name "process_weather_${ENV}" --no-cli-pager
run aws glue delete-crawler  --name "${P}-crawler-${ENV}" --no-cli-pager
run aws glue delete-database --name "${P}_${ENV}" --catalog-id "$(aws sts get-caller-identity --query Account --output text)" --no-cli-pager

# ── 4. Athena workgroup ───────────────────────────────────────────────────────
echo ""
echo "[ Athena ]"
run aws athena delete-work-group \
  --work-group "${P}-${ENV}" \
  --recursive-delete-option \
  --no-cli-pager

# ── 5. S3 buckets (force-delete including all object versions) ────────────────
echo ""
echo "[ S3 ]"
for bucket in "${P}-raw-${ENV}" "${P}-processed-${ENV}" "${P}-athena-results-${ENV}"; do
  if aws s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    echo "  Emptying s3://$bucket ..."
    # Delete all object versions (needed when versioning is enabled)
    aws s3api delete-objects \
      --bucket "$bucket" \
      --delete "$(aws s3api list-object-versions \
        --bucket "$bucket" \
        --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
        --output json 2>/dev/null)" \
      --no-cli-pager 2>/dev/null || true
    # Delete any remaining delete markers
    aws s3api delete-objects \
      --bucket "$bucket" \
      --delete "$(aws s3api list-object-versions \
        --bucket "$bucket" \
        --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
        --output json 2>/dev/null)" \
      --no-cli-pager 2>/dev/null || true
    aws s3 rb "s3://$bucket" --force 2>/dev/null && ok "Deleted $bucket" || skip "$bucket"
  else
    skip "$bucket"
  fi
done

# ── 6. Prod-only: ECS, ECR, ALB, security groups ─────────────────────────────
if [[ "$ENV" == "prod" ]]; then
  echo ""
  echo "[ ECS ]"
  # Scale to 0 and delete service
  aws ecs update-service \
    --cluster "${P}-${ENV}" \
    --service "${P}-streamlit-${ENV}" \
    --desired-count 0 \
    --no-cli-pager 2>/dev/null && ok "Scaled service to 0" || skip "ECS service"
  sleep 10
  run aws ecs delete-service \
    --cluster "${P}-${ENV}" \
    --service "${P}-streamlit-${ENV}" \
    --force \
    --no-cli-pager
  # Deregister all task definitions in the family
  TASK_DEFS=$(aws ecs list-task-definitions \
    --family-prefix "${P}-streamlit-${ENV}" \
    --query 'taskDefinitionArns[]' \
    --output text 2>/dev/null || true)
  for td in $TASK_DEFS; do
    run aws ecs deregister-task-definition --task-definition "$td" --no-cli-pager
  done
  run aws ecs delete-cluster --cluster "${P}-${ENV}" --no-cli-pager

  echo ""
  echo "[ ECR ]"
  if aws ecr describe-repositories --repository-names "${P}-streamlit-${ENV}" --no-cli-pager 2>/dev/null; then
    IMAGE_IDS=$(aws ecr list-images \
      --repository-name "${P}-streamlit-${ENV}" \
      --query 'imageIds[*]' --output json 2>/dev/null || echo "[]")
    if [[ "$IMAGE_IDS" != "[]" && "$IMAGE_IDS" != "" ]]; then
      aws ecr batch-delete-image \
        --repository-name "${P}-streamlit-${ENV}" \
        --image-ids "$IMAGE_IDS" \
        --no-cli-pager 2>/dev/null && ok "Deleted ECR images" || skip "ECR image delete"
    fi
    run aws ecr delete-repository \
      --repository-name "${P}-streamlit-${ENV}" \
      --force \
      --no-cli-pager
  else
    skip "ECR repo ${P}-streamlit-${ENV}"
  fi

  echo ""
  echo "[ ALB ]"
  ALB_ARN=$(aws elbv2 describe-load-balancers \
    --names "${P}-alb-${ENV}" \
    --query 'LoadBalancers[0].LoadBalancerArn' \
    --output text 2>/dev/null || echo "None")
  if [[ "$ALB_ARN" != "None" && -n "$ALB_ARN" ]]; then
    # Delete listeners first (auto-deleted with LB, but explicit is safer)
    LISTENER_ARNS=$(aws elbv2 describe-listeners \
      --load-balancer-arn "$ALB_ARN" \
      --query 'Listeners[].ListenerArn' \
      --output text 2>/dev/null || true)
    for l in $LISTENER_ARNS; do
      run aws elbv2 delete-listener --listener-arn "$l" --no-cli-pager
    done
    run aws elbv2 delete-load-balancer --load-balancer-arn "$ALB_ARN" --no-cli-pager
    echo "  Waiting for ALB to finish deleting..."
    sleep 30
  else
    skip "ALB ${P}-alb-${ENV}"
  fi
  TG_ARN=$(aws elbv2 describe-target-groups \
    --names "${P}-tg-${ENV}" \
    --query 'TargetGroups[0].TargetGroupArn' \
    --output text 2>/dev/null || echo "None")
  if [[ "$TG_ARN" != "None" && -n "$TG_ARN" ]]; then
    run aws elbv2 delete-target-group --target-group-arn "$TG_ARN" --no-cli-pager
  else
    skip "Target group ${P}-tg-${ENV}"
  fi

  echo ""
  echo "[ Security groups (prod) ]"
  for sg_name in "${P}-alb-${ENV}" "${P}-ecs-${ENV}"; do
    SG_ID=$(aws ec2 describe-security-groups \
      --filters "Name=group-name,Values=$sg_name" \
      --query 'SecurityGroups[0].GroupId' \
      --output text 2>/dev/null || echo "None")
    if [[ "$SG_ID" != "None" && -n "$SG_ID" ]]; then
      run aws ec2 delete-security-group --group-id "$SG_ID" --no-cli-pager
    else
      skip "Security group $sg_name"
    fi
  done

  echo ""
  echo "[ CloudWatch Logs (prod ECS) ]"
  run aws logs delete-log-group \
    --log-group-name "/ecs/${P}-streamlit-${ENV}" \
    --no-cli-pager

  echo ""
  echo "[ IAM (ECS roles) ]"
  for role in "${P}-ecs-execution-${ENV}" "${P}-ecs-task-${ENV}"; do
    if aws iam get-role --role-name "$role" --no-cli-pager 2>/dev/null; then
      # Detach managed policies
      ATTACHED=$(aws iam list-attached-role-policies \
        --role-name "$role" \
        --query 'AttachedPolicies[].PolicyArn' \
        --output text 2>/dev/null || true)
      for arn in $ATTACHED; do
        run aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" --no-cli-pager
      done
      # Delete inline policies
      INLINE=$(aws iam list-role-policies \
        --role-name "$role" \
        --query 'PolicyNames[]' \
        --output text 2>/dev/null || true)
      for pname in $INLINE; do
        run aws iam delete-role-policy --role-name "$role" --policy-name "$pname" --no-cli-pager
      done
      run aws iam delete-role --role-name "$role" --no-cli-pager
    else
      skip "IAM role $role"
    fi
  done
fi

# ── 7. IAM: Glue, Lambda, Scheduler roles and customer-managed policies ───────
echo ""
echo "[ IAM (pipeline roles) ]"

delete_role() {
  local role="$1"
  if aws iam get-role --role-name "$role" --no-cli-pager 2>/dev/null; then
    ATTACHED=$(aws iam list-attached-role-policies \
      --role-name "$role" \
      --query 'AttachedPolicies[].PolicyArn' \
      --output text 2>/dev/null || true)
    for arn in $ATTACHED; do
      run aws iam detach-role-policy --role-name "$role" --policy-arn "$arn" --no-cli-pager
    done
    INLINE=$(aws iam list-role-policies \
      --role-name "$role" \
      --query 'PolicyNames[]' \
      --output text 2>/dev/null || true)
    for pname in $INLINE; do
      run aws iam delete-role-policy --role-name "$role" --policy-name "$pname" --no-cli-pager
    done
    run aws iam delete-role --role-name "$role" --no-cli-pager
  else
    skip "IAM role $role"
  fi
}

delete_role "${P}-glue-role-${ENV}"
delete_role "${P}-pipeline-trigger-${ENV}"
delete_role "${P}-scheduler-${ENV}"

echo ""
echo "[ IAM (customer-managed policies) ]"
ACCOUNT=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
for policy in \
    "${P}-glue-s3-${ENV}" \
    "${P}-glue-secrets-${ENV}" \
    "${P}-lambda-glue-${ENV}" \
    "${P}-scheduler-invoke-${ENV}"; do
  POLICY_ARN="arn:aws:iam::${ACCOUNT}:policy/${policy}"
  if aws iam get-policy --policy-arn "$POLICY_ARN" --no-cli-pager 2>/dev/null; then
    # Delete non-default versions first
    VERSIONS=$(aws iam list-policy-versions \
      --policy-arn "$POLICY_ARN" \
      --query 'Versions[?!IsDefaultVersion].VersionId' \
      --output text 2>/dev/null || true)
    for v in $VERSIONS; do
      run aws iam delete-policy-version --policy-arn "$POLICY_ARN" --version-id "$v" --no-cli-pager
    done
    run aws iam delete-policy --policy-arn "$POLICY_ARN" --no-cli-pager
  else
    skip "IAM policy $policy"
  fi
done

# ── 8. Secrets Manager ────────────────────────────────────────────────────────
echo ""
echo "[ Secrets Manager ]"
run aws secretsmanager delete-secret \
  --secret-id "weather-api-key-${ENV}" \
  --force-delete-without-recovery \
  --no-cli-pager

# ── 9. CloudWatch log groups (Lambda / Glue — auto-created by AWS) ────────────
echo ""
echo "[ CloudWatch Logs (Lambda / Glue) ]"
run aws logs delete-log-group \
  --log-group-name "/aws/lambda/${P}-pipeline-trigger-${ENV}" \
  --no-cli-pager
for job in "fetch_weather_${ENV}" "process_weather_${ENV}"; do
  run aws logs delete-log-group \
    --log-group-name "/aws/glue/jobs/${job}" \
    --no-cli-pager
done

echo ""
echo "========================================================"
echo " Done: $ENV teardown complete."
echo "========================================================"
