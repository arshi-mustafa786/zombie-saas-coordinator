# PowerShell Cloud Run Deployment Script for Zombie SaaS Consolidator
param (
    [string]$ProjectId = "zombie-saas-coordinator",
    [string]$Region = "asia-south1",
    [string]$ServiceName = "zombie-saas-coordinator",
    [string]$RepoName = "zombie-saas",
    [string]$CredentialsFile = "gcp-credentials.json",
    [switch]$Push,
    [switch]$Deploy
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "[*] Zombie SaaS Consolidator - Google Cloud Run Deployer" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  Project ID:      $ProjectId"
Write-Host "  Region:          $Region"
Write-Host "  Service Name:    $ServiceName"
Write-Host "  Repository:      $RepoName"
Write-Host "=========================================================="

# 1. Verify credentials file
if (-not (Test-Path $CredentialsFile)) {
    Write-Error "Credentials file '$CredentialsFile' not found in workspace root."
}
Write-Host "[OK] Service account credentials found: $CredentialsFile" -ForegroundColor Green

# 2. Check if gcloud is installed
$hasGcloud = (Get-Command gcloud -ErrorAction SilentlyContinue) -ne $null

if ($hasGcloud) {
    Write-Host "[OK] Google Cloud CLI (gcloud) is available." -ForegroundColor Green
    
    Write-Host "--> Authorizing gcloud with service account..." -ForegroundColor Yellow
    & gcloud auth activate-service-account --key-file=$CredentialsFile
    & gcloud config set project $ProjectId

    Write-Host "--> Submitting build to Google Cloud Build..." -ForegroundColor Yellow
    & gcloud builds submit --config=cloudbuild.yaml --substitutions="_REGION=$Region,_REPO_NAME=$RepoName,_SERVICE_NAME=$ServiceName" .

    Write-Host "`n[OK] Cloud Build submission triggered successfully!" -ForegroundColor Green

} else {
    Write-Host "[i] gcloud CLI not detected locally. Using Podman container workflow..." -ForegroundColor Yellow
    
    $registryHost = "$($Region)-docker.pkg.dev"
    $imageTag = "$registryHost/$ProjectId/$RepoName/${ServiceName}:latest"
    
    Write-Host "--> Building container with Podman: $imageTag" -ForegroundColor Yellow
    & podman build -t $imageTag .

    Write-Host "[OK] Image built successfully with Podman." -ForegroundColor Green

    if ($Push) {
        Write-Host "--> Authenticating Podman with Google Artifact Registry ($registryHost)..." -ForegroundColor Yellow
        Get-Content $CredentialsFile -Raw | & podman login -u _json_key --password-stdin "https://$registryHost"

        Write-Host "--> Pushing container image to Artifact Registry..." -ForegroundColor Yellow
        & podman push $imageTag
        Write-Host "[OK] Container image successfully pushed to Artifact Registry!" -ForegroundColor Green
    } else {
        Write-Host "`nTo push the built image to Google Artifact Registry:" -ForegroundColor Cyan
        Write-Host "  Get-Content $CredentialsFile -Raw | podman login -u _json_key --password-stdin https://$registryHost" -ForegroundColor White
        Write-Host "  podman push $imageTag" -ForegroundColor White
        Write-Host "`nOr rerun this script with -Push:" -ForegroundColor Cyan
        Write-Host "  .\scripts\deploy_cloud_run.ps1 -Push" -ForegroundColor White
    }
}

Write-Host "`n[OK] Pre-deployment preparation complete." -ForegroundColor Green
