"""
Generate docs/architecture.png and docs/architecture.svg using the `diagrams` library.

Requirements:
    pip install diagrams
    brew install graphviz   # macOS
    # or: apt-get install graphviz  (Linux)

Run:
    python docs/generate_diagram.py
"""

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.integration import Eventbridge
from diagrams.aws.compute import Lambda, ECS, ECR
from diagrams.aws.analytics import Glue, Athena
from diagrams.aws.storage import S3
from diagrams.aws.network import ALB
from diagrams.aws.security import SecretsManager
from diagrams.aws.management import Cloudwatch
from diagrams.onprem.vcs import Github
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.workflow import Airflow
from diagrams.onprem.network import Internet

graph_attr = {
    "fontsize": "13",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "ortho",
    "nodesep": "0.6",
    "ranksep": "0.8",
    "fontname": "Helvetica",
}

node_attr = {
    "fontsize": "11",
    "fontname": "Helvetica",
}

edge_attr = {
    "fontsize": "10",
    "fontname": "Helvetica",
}


def build(outformat: str, filename: str) -> None:
    with Diagram(
        "Tri-State Weather Pipeline",
        show=False,
        filename=filename,
        outformat=outformat,
        direction="LR",
        graph_attr=graph_attr,
        node_attr=node_attr,
        edge_attr=edge_attr,
        curvestyle="ortho",
    ):
        owm = Internet("OpenWeatherMap\nAPI")
        github = GithubActions("GitHub Actions\nCI/CD")

        with Cluster("AWS Cloud  (us-east-1)"):

            with Cluster("Security"):
                secrets = SecretsManager("Secrets Manager\n(API Key)")

            with Cluster("Orchestration"):
                eb = Eventbridge("EventBridge\nScheduler\n(30 min)")
                lam = Lambda("Trigger\nLambda")

            with Cluster("Ingestion  ·  Glue Workflow"):
                fetch = Glue("fetch_weather\n(PySpark)")

            with Cluster("Storage"):
                raw = S3("Raw S3\nJSON")
                proc = S3("Processed S3\nParquet (hive)")

            with Cluster("Processing"):
                process = Glue("process_weather\n(PySpark)")
                catalog = Athena("Glue Catalog\n+ Athena")

            with Cluster("Container Registry"):
                ecr = ECR("ECR")

            with Cluster("Serving  ·  ECS Fargate"):
                alb = ALB("ALB  :80")
                ecs = ECS("ECS Fargate\nStreamlit  :8501")

            with Cluster("Observability"):
                cw = Cloudwatch("CloudWatch\nLogs  (7d)")

        with Cluster("Local Dev  (Docker)"):
            airflow = Airflow("Airflow +\nLocalStack")

        # ── Data flow ──────────────────────────────────────────────────────
        owm >> Edge(label="REST /weather") >> fetch
        secrets >> Edge(style="dashed") >> fetch

        eb >> lam >> Edge(label="StartWorkflowRun") >> fetch
        fetch >> raw >> process >> proc

        proc >> catalog
        proc >> Edge(label="DuckDB httpfs") >> ecs

        # ── Serving ────────────────────────────────────────────────────────
        alb >> ecs
        ecs >> cw

        # ── CI/CD ──────────────────────────────────────────────────────────
        github >> Edge(label="docker push") >> ecr
        ecr >> Edge(label="pull on deploy") >> ecs

        # ── Local ──────────────────────────────────────────────────────────
        airflow >> Edge(style="dashed", label="local only") >> raw


if __name__ == "__main__":
    build(outformat="png", filename="docs/architecture")
    build(outformat="svg", filename="docs/architecture_flow")
    print("Generated: docs/architecture.png  docs/architecture_flow.svg")
