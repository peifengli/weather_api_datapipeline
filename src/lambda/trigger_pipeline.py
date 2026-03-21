"""
Lambda function: trigger_pipeline
Invoked by EventBridge Scheduler every hour.
Starts the Glue Workflow which chains fetch → process jobs.
"""

from __future__ import annotations

import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: dict, context: object) -> dict:
    environment = os.environ["ENVIRONMENT"]
    workflow_name = f"weather-pipeline-{environment}"

    glue = boto3.client("glue", region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))

    response = glue.start_workflow_run(Name=workflow_name)
    run_id = response["RunId"]

    logger.info("Started workflow=%s run_id=%s", workflow_name, run_id)
    return {"statusCode": 200, "workflow": workflow_name, "run_id": run_id}
