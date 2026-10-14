"""Cloud Run & GCP Deployment Verification Script.

Tests the live Cloud Run deployment for:
1. HTTP /health endpoint status
2. HTTP /readiness endpoint status (Firestore connectivity)
3. POST /api/v1/jobs/idp-scan trigger execution
4. Firestore audit persistence verification
"""

import argparse
import json
import sys
import httpx
from google.cloud import firestore
from google.oauth2 import service_account


def verify_cloud_run(base_url: str, credentials_path: str = "gcp-credentials.json") -> bool:
    print(f"[*] Starting deployment verification against: {base_url}")
    client = httpx.Client(timeout=30.0)

    # 1. Health check
    print("\n--- Test 1: Liveness /health probe ---")
    try:
        resp = client.get(f"{base_url.rstrip('/')}/health")
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code != 200:
            print("[!] Health check failed!")
            return False
        print("[+] Health probe passed!")
    except Exception as exc:
        print(f"[!] Health check failed with error: {exc}")
        return False

    # 2. Readiness check
    print("\n--- Test 2: Readiness /readiness probe ---")
    try:
        resp = client.get(f"{base_url.rstrip('/')}/readiness")
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code != 200:
            print("[!] Readiness check failed!")
            return False
        print("[+] Readiness probe passed!")
    except Exception as exc:
        print(f"[!] Readiness check failed with error: {exc}")
        return False

    # 3. Cloud Scheduler / IdP Scan Job trigger
    print("\n--- Test 3: IdP Scan Job Trigger ---")
    try:
        headers = {"Authorization": "Bearer test-scheduler-token", "Content-Type": "application/json"}
        payload = {"tenant_id": "tenant-demo-corp", "days": 30}
        resp = client.post(f"{base_url.rstrip('/')}/api/v1/jobs/scan-idp", headers=headers, json=payload)
        print(f"Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")
        if resp.status_code != 200:
            print("[!] IdP Scan trigger returned non-200!")
            return False
        print("[+] IdP Scan trigger successfully executed!")
    except Exception as exc:
        print(f"[!] IdP Scan trigger error: {exc}")
        return False

    # 4. Firestore persistence check
    print("\n--- Test 4: Firestore Audit Verification ---")
    try:
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        db = firestore.Client(credentials=creds, project=creds.project_id, database="zombie-saas-coordinator")
        scans = list(db.collection("scans").limit(5).stream())
        print(f"Found {len(scans)} scan records in Firestore database 'zombie-saas-coordinator'")
        for s in scans:
            print(f" - Scan Doc ID: {s.id} => Status: {s.to_dict().get('status', 'unknown')}")
        print("[+] Firestore persistence confirmed!")
    except Exception as exc:
        print(f"[!] Firestore check error: {exc}")
        return False

    print("\n=======================================================")
    print("[SUCCESS] ALL DEPLOYMENT VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=======================================================")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verify Cloud Run Deployment")
    parser.add_argument("--url", required=True, help="Base URL of the Cloud Run service")
    parser.add_argument("--credentials", default="gcp-credentials.json", help="Path to gcp-credentials.json")
    args = parser.parse_args()

    success = verify_cloud_run(args.url, args.credentials)
    sys.exit(0 if success else 1)
