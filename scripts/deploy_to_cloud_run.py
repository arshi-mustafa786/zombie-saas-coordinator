"""Deploy Zombie SaaS Consolidator to Google Cloud Run via Google Cloud Run v2 API."""

import argparse
import os
import sys
import time
from dotenv import load_dotenv
from google.oauth2 import service_account
from googleapiclient.discovery import build

load_dotenv()


def deploy_cloud_run(
    project_id: str = "zombie-saas-coordinator",
    region: str = "asia-south1",
    service_name: str = "zombie-saas-coordinator",
    image_uri: str = "asia-south1-docker.pkg.dev/zombie-saas-coordinator/zombie-saas/zombie-saas-coordinator:latest",
    credentials_path: str = "gcp-credentials.json",
    gemini_api_key: str | None = None,
    allow_unauthenticated: bool = True,
) -> str:
    print(f"[*] Authenticating with service account from: {credentials_path}")
    creds = service_account.Credentials.from_service_account_file(credentials_path)

    v2 = build("run", "v2", credentials=creds)
    parent = f"projects/{project_id}/locations/{region}"
    full_service_name = f"{parent}/services/{service_name}"

    gemini_key = gemini_api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    env_vars = [
        {"name": "GOOGLE_CLOUD_PROJECT", "value": project_id},
        {"name": "GOOGLE_CLOUD_REGION", "value": region},
        {"name": "FIRESTORE_DATABASE_ID", "value": "zombie-saas-coordinator"},
        {"name": "GEMINI_MODEL", "value": "gemini-3.1-flash-lite"},
        {"name": "DEPLOY_TIMESTAMP", "value": str(int(time.time()))},
        {"name": "ENVIRONMENT", "value": "production"},
    ]
    if gemini_key:
        env_vars.append({"name": "GEMINI_API_KEY", "value": gemini_key})

    service_body = {
        "ingress": "INGRESS_TRAFFIC_ALL",
        "template": {
            "maxInstanceRequestConcurrency": 80,
            "timeout": "300s",
            "scaling": {
                "minInstanceCount": 0,
                "maxInstanceCount": 5,
            },
            "containers": [
                {
                    "image": image_uri,
                    "ports": [{"containerPort": 8080}],
                    "resources": {
                        "limits": {
                            "memory": "1Gi",
                            "cpu": "1",
                        }
                    },
                    "env": env_vars,

                    "livenessProbe": {
                        "httpGet": {
                            "path": "/health",
                            "port": 8080,
                        },
                        "initialDelaySeconds": 5,
                        "periodSeconds": 15,
                    },
                    "startupProbe": {
                        "httpGet": {
                            "path": "/health",
                            "port": 8080,
                        },
                        "initialDelaySeconds": 0,
                        "periodSeconds": 5,
                        "failureThreshold": 10,
                    },
                }
            ],
        },
    }

    # Check if service already exists
    existing_service = None
    try:
        existing_service = v2.projects().locations().services().get(name=full_service_name).execute()
        print(f"[+] Found existing Cloud Run service: {service_name}")
    except Exception:
        print(f"[*] Service '{service_name}' does not exist yet. Creating new service...")

    if existing_service:
        print(f"[*] Updating service '{service_name}' with new container image: {image_uri}")
        op = v2.projects().locations().services().patch(
            name=full_service_name,
            updateMask="template",
            body=service_body
        ).execute()

    else:
        print(f"[*] Creating Cloud Run service '{service_name}' in '{region}'...")
        op = v2.projects().locations().services().create(
            parent=parent,
            serviceId=service_name,
            body=service_body
        ).execute()

    op_name = op.get("name")
    print(f"[*] Operation started: {op_name}")
    print("[*] Waiting for Cloud Run service deployment to become ready...")

    for attempt in range(30):
        time.sleep(5)
        operation = v2.projects().locations().operations().get(name=op_name).execute()
        if operation.get("done"):
            if "error" in operation:
                print(f"[!] Deployment operation failed with error: {operation['error']}")
                return ""
            print("[+] Deployment operation completed successfully!")
            break
        print(f"  Attempt {attempt + 1}/30: Still provisioning...")

    # Fetch service details to get URL
    svc = v2.projects().locations().services().get(name=full_service_name).execute()
    service_url = svc.get("uri", "")
    print(f"\n=======================================================")
    print(f"[SUCCESS] CLOUD RUN SERVICE IS LIVE!")
    print(f"Public Service URL: {service_url}")
    print(f"=======================================================\n")


    # Grant public unauthenticated access if requested
    if allow_unauthenticated:
        try:
            print("[*] Configuring public access policy (allUsers -> roles/run.invoker)...")
            policy_body = {
                "policy": {
                    "bindings": [
                        {
                            "role": "roles/run.invoker",
                            "members": ["allUsers"],
                        }
                    ]
                }
            }
            v2.projects().locations().services().setIamPolicy(
                resource=full_service_name,
                body=policy_body
            ).execute()
            print("[+] Public access policy applied successfully.")
        except Exception as exc:
            print(f"[!] Warning applying IAM policy: {exc}")

    return service_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy to Google Cloud Run v2")
    parser.add_argument("--project", default="zombie-saas-coordinator")
    parser.add_argument("--region", default="asia-south1")
    parser.add_argument("--service", default="zombie-saas-coordinator")
    parser.add_argument("--image", default="asia-south1-docker.pkg.dev/zombie-saas-coordinator/zombie-saas/zombie-saas-coordinator:latest")
    parser.add_argument("--credentials", default="gcp-credentials.json")
    parser.add_argument("--api-key", default=None, help="Gemini API Key (optional, defaults to GEMINI_API_KEY env var)")
    args = parser.parse_args()

    url = deploy_cloud_run(
        project_id=args.project,
        region=args.region,
        service_name=args.service,
        image_uri=args.image,
        credentials_path=args.credentials,
        gemini_api_key=args.api_key,
    )
    if not url:
        sys.exit(1)
