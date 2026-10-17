"""Production-grade Enterprise IdP Audit Log Generator.

Generates realistic SAML 2.0 / OIDC authentication and access telemetry
matching the schema of Okta System Log, Google Workspace Reports API, and Microsoft Entra ID.
"""

import argparse
import json
import random
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ENTERPRISE_APPS = [
    {
        "app_id": "app_trello_01",
        "app_name": "Trello",
        "vendor": "Atlassian",
        "category": "Project Management",
        "capabilities": ["kanban", "task-tracking", "collaboration"],
        "total_seats": 120,
        "inactive_ratio": 0.82,  # Zombie app
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 45.0,
        "dormancy_days": 104,
    },
    {
        "app_id": "app_asana_01",
        "app_name": "Asana",
        "vendor": "Asana Inc.",
        "category": "Project Management",
        "capabilities": ["kanban", "task-tracking", "scrum", "collaboration", "custom-fields", "rules"],
        "total_seats": 350,
        "inactive_ratio": 0.12,  # Highly active enterprise standard
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 38.0,
        "dormancy_days": 1,
    },
    {
        "app_id": "app_miro_01",
        "app_name": "Miro",
        "vendor": "RealtimeBoard Inc.",
        "category": "Whiteboard & Collaboration",
        "capabilities": ["whiteboard", "mindmapping", "brainstorming", "collaboration"],
        "total_seats": 85,
        "inactive_ratio": 0.76,  # Zombie app
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 30.0,
        "dormancy_days": 95,
    },
    {
        "app_id": "app_monday_01",
        "app_name": "Monday.com",
        "vendor": "Monday.com Ltd.",
        "category": "Project Management",
        "capabilities": ["kanban", "task-tracking", "collaboration"],
        "total_seats": 60,
        "inactive_ratio": 0.88,  # Zombie app
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 40.0,
        "dormancy_days": 88,
    },
    {
        "app_id": "app_jira_01",
        "app_name": "Jira Software",
        "vendor": "Atlassian",
        "category": "Project Management",
        "capabilities": ["kanban", "scrum", "issue-tracking", "task-tracking", "collaboration", "enterprise-agile"],
        "total_seats": 450,
        "inactive_ratio": 0.08,  # Highly active
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 42.0,
        "dormancy_days": 0,
    },
    {
        "app_id": "app_slack_01",
        "app_name": "Slack Enterprise Grid",
        "vendor": "Salesforce",
        "category": "Team Communication",
        "capabilities": ["chat", "channels", "team-messaging", "huddles"],
        "total_seats": 500,
        "inactive_ratio": 0.05,  # Daily core tool
        "sso_protocol": "OIDC",
        "monthly_seat_cost": 15.0,
        "dormancy_days": 0,
    },
    {
        "app_id": "app_lucid_01",
        "app_name": "Lucidchart",
        "vendor": "Lucid Software",
        "category": "Whiteboard & Collaboration",
        "capabilities": ["diagramming", "flowcharts", "whiteboard"],
        "total_seats": 75,
        "inactive_ratio": 0.72,  # Zombie app
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 28.0,
        "dormancy_days": 76,
    },
    {
        "app_id": "app_github_01",
        "app_name": "GitHub Enterprise",
        "vendor": "Microsoft",
        "category": "Developer Tools",
        "capabilities": ["git", "code-review", "ci-cd", "packages"],
        "total_seats": 220,
        "inactive_ratio": 0.04,  # Active
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 21.0,
        "dormancy_days": 0,
    },
    {
        "app_id": "app_figma_01",
        "app_name": "Figma Enterprise",
        "vendor": "Figma Inc.",
        "category": "Design & Prototyping",
        "capabilities": ["ui-design", "prototyping", "design-systems"],
        "total_seats": 90,
        "inactive_ratio": 0.15,  # Active
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 45.0,
        "dormancy_days": 2,
    },
    {
        "app_id": "app_aws_01",
        "app_name": "AWS IAM Identity Center",
        "vendor": "Amazon Web Services",
        "category": "Cloud Infrastructure",
        "capabilities": ["cloud-console", "iam", "cloud-compute"],
        "total_seats": 180,
        "inactive_ratio": 0.06,  # Active
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 0.0,
        "dormancy_days": 0,
    },
    {
        "app_id": "app_salesforce_01",
        "app_name": "Salesforce Sales Cloud",
        "vendor": "Salesforce",
        "category": "CRM & Sales",
        "capabilities": ["crm", "pipeline-tracking", "account-management"],
        "total_seats": 140,
        "inactive_ratio": 0.10,  # Active
        "sso_protocol": "SAML_2_0",
        "monthly_seat_cost": 150.0,
        "dormancy_days": 1,
    },
    {
        "app_id": "app_zoom_01",
        "app_name": "Zoom Workplace",
        "vendor": "Zoom Video Communications",
        "category": "Video Conferencing",
        "capabilities": ["video-meetings", "webinars", "phone"],
        "total_seats": 400,
        "inactive_ratio": 0.09,  # Active
        "sso_protocol": "OIDC",
        "monthly_seat_cost": 20.0,
        "dormancy_days": 0,
    },
]

FIRST_NAMES = ["Sarah", "Alex", "David", "Priya", "Marcus", "Elena", "Wei", "Chloe", "James", "Fatima", "Liam", "Anya"]
LAST_NAMES = ["Chen", "Miller", "Kumar", "Patel", "Vance", "Kowalski", "Zhang", "Dubois", "O'Connor", "Al-Mansoor", "Smith", "Novak"]
LOCATIONS = [
    {"city": "San Francisco", "country": "United States", "ip": "198.51.100.24"},
    {"city": "New York", "country": "United States", "ip": "198.51.100.89"},
    {"city": "London", "country": "United Kingdom", "ip": "195.55.120.45"},
    {"city": "Bengaluru", "country": "India", "ip": "103.21.144.12"},
    {"city": "Tokyo", "country": "Japan", "ip": "133.242.18.5"},
]


def generate_enterprise_idp_telemetry(events_per_app: int = 15) -> list[dict]:
    """Generates a production-scale enterprise IdP application telemetry dataset."""
    now = datetime.now(UTC)
    dataset = []

    for app in ENTERPRISE_APPS:
        total = app["total_seats"]
        inactive = int(total * app["inactive_ratio"])
        active = total - inactive
        dormancy = app["dormancy_days"]
        last_login = (now - timedelta(days=dormancy)).isoformat()

        # Generate realistic Okta/Google Workspace SAML audit events for this app
        audit_events = []
        for _ in range(events_per_app):
            fn = random.choice(FIRST_NAMES)
            ln = random.choice(LAST_NAMES)
            email = f"{fn.lower()}.{ln.lower()}@enterprise.com"
            loc = random.choice(LOCATIONS)
            event_age = dormancy if inactive > active else random.randint(0, 14)
            event_time = (now - timedelta(days=event_age, hours=random.randint(1, 23))).isoformat()

            audit_events.append({
                "eventId": f"evt_{uuid.uuid4().hex[:12]}",
                "published": event_time,
                "eventType": "user.authentication.sso",
                "actor": {
                    "id": f"usr_{uuid.uuid4().hex[:8]}",
                    "type": "User",
                    "displayName": f"{fn} {ln}",
                    "email": email,
                },
                "client": {
                    "ipAddress": loc["ip"],
                    "geographicalContext": {"city": loc["city"], "country": loc["country"]},
                    "userAgent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0",
                },
                "securityContext": {
                    "mfa": "DUO_PUSH_VERIFIED",
                    "sso_protocol": app["sso_protocol"],
                },
                "outcome": {
                    "result": "SUCCESS" if event_age < 60 else "DORMANT_INACTIVE",
                    "days_inactive": event_age,
                },
            })

        app_record = {
            "app_id": app["app_id"],
            "app_name": app["app_name"],
            "vendor": app["vendor"],
            "category": app["category"],
            "capabilities": app["capabilities"],
            "total_seats": total,
            "active_seats": active,
            "inactive_seats": inactive,
            "inactive_ratio": round(inactive / total, 2),
            "last_login_date": last_login,
            "sso_protocol": app["sso_protocol"],
            "monthly_seat_cost": app["monthly_seat_cost"],
            "idp_provider": "Okta Universal Directory / Google Workspace SSO",
            "is_flagged_zombie": bool(inactive / total >= 0.60 and dormancy >= 60),
            "sample_audit_events": audit_events,
        }
        dataset.append(app_record)

    return dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate enterprise production-sized IdP audit logs")
    parser.add_argument("--output", default="dashboard/enterprise_production_idp_logs.json", help="Output path")
    parser.add_argument("--events-per-app", type=int, default=10, help="Number of audit events per app")
    args = parser.parse_args()

    telemetry = generate_enterprise_idp_telemetry(events_per_app=args.events_per_app)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(telemetry, f, indent=2)

    total_seats = sum(a["total_seats"] for a in telemetry)
    inactive_seats = sum(a["inactive_seats"] for a in telemetry)
    flagged = sum(1 for a in telemetry if a["is_flagged_zombie"])

    print(f"[+] Successfully generated production IdP dataset: {out_path}")
    print(f"    Total Enterprise Apps: {len(telemetry)}")
    print(f"    Total User Seats Monitored: {total_seats:,}")
    print(f"    Inactive / Zombie Seats: {inactive_seats:,}")
    print(f"    Zombie Apps Flagged (>60% idle, >60d): {flagged}")
