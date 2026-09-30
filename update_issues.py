import json
import subprocess
import os

def run_command(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
    if result.returncode != 0:
        # Don't print for label-already-exists errors
        if "already exists" not in result.stderr:
            print(f"  Warning: {result.stderr.strip()}")
    return result.stdout.strip()

# Label definitions: name -> (color, description)
LABEL_DEFINITIONS = {
    "user-story": ("0075ca", "User story issue"),
    "google-adk": ("4285F4", "Built with Google Agent Development Kit"),
    "agent:auditor": ("fbbc04", "Auditor Agent (detection & proposals)"),
    "agent:architect": ("ea4335", "Architect Agent (semantic validation)"),
    "agent:integrator": ("34a853", "Integrator Agent (dependency scanning)"),
    "agent:orchestrator": ("9334e6", "Root Orchestrator Agent"),
    "layer:DB": ("d4c5f9", "Database layer"),
    "layer:Service": ("c5def5", "Service layer"),
    "layer:API": ("bfdadc", "API layer"),
    "layer:UI": ("fbca04", "UI layer"),
}

def ensure_labels_exist():
    """Create all labels in the repo if they don't already exist."""
    print("Ensuring all labels exist in the repository...")
    for label_name, (color, description) in LABEL_DEFINITIONS.items():
        run_command(
            f'gh label create "{label_name}" --color "{color}" '
            f'--description "{description}" --force'
        )
    print("Labels ready.\n")

def main():
    print("Loading local JSON...")
    with open("github-issues-import.json", "r", encoding="utf-8") as f:
        local_issues = json.load(f)
    
    # Step 1: Create labels
    ensure_labels_exist()
    
    # Step 2: Fetch existing issues
    print("Fetching existing issues from GitHub...")
    gh_list_output = run_command("gh issue list --limit 100 --json number,title")
    
    if not gh_list_output:
        print("No issues found or you are not authenticated with gh CLI.")
        return
        
    remote_issues = json.loads(gh_list_output)
    title_to_number = {issue["title"]: issue["number"] for issue in remote_issues}
    
    updated = 0
    skipped = 0
    
    for local in local_issues:
        title = local["title"]
        if title in title_to_number:
            issue_num = title_to_number[title]
            print(f"Updating Issue #{issue_num}: {title}...")
            
            # Update body
            with open("temp_body.md", "w", encoding="utf-8") as temp_file:
                temp_file.write(local["body"])
            run_command(f'gh issue edit {issue_num} --body-file temp_body.md')
            
            # Update labels
            if "labels" in local and local["labels"]:
                labels_str = ",".join(local["labels"])
                run_command(f'gh issue edit {issue_num} --add-label "{labels_str}"')
            
            updated += 1
        else:
            print(f"Skipping '{title}': Not found on GitHub.")
            skipped += 1
            
    # Cleanup
    if os.path.exists("temp_body.md"):
        os.remove("temp_body.md")
        
    print(f"\nBulk update complete! Updated: {updated}, Skipped: {skipped}")

if __name__ == "__main__":
    main()
