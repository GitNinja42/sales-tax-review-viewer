# Deployment Guide

## Server Details

- **VM**: review-server (Google Cloud, us-central1-a, e2-small)
- **External IP**: 34.71.141.39
- **URL**: http://34.71.141.39:8790/
- **GCP Project**: project-30e8d102-d40c-4a2e-8b4
- **OS**: Debian 12
- **Claude CLI**: authenticated as cyan.personal@gmail.com (OAuth)
- **Cost**: ~$14.56/month (covered by free credits)

## Access the Review Viewer

Open http://34.71.141.39:8790/ in any browser.

## Deploy Code Changes

### Option 1: Direct to VM (skip GitHub)

Copy files and restart:

```bash
gcloud compute scp --recurse \
  "/Users/chris/Documents/review-pack-template - claude version/"* \
  review-server:~/review-app/ \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4

gcloud compute ssh review-server \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4 \
  --command="sudo systemctl restart review-server"
```

### Option 2: Via GitHub

```bash
# 1. Push locally
git add -A && git commit -m "update" && git push origin main

# 2. Pull on VM and restart
gcloud compute ssh review-server \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4 \
  --command="cd ~/review-app && git pull origin main && sudo systemctl restart review-server"
```

## SSH into the VM

```bash
gcloud compute ssh review-server \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4
```

## Server Management (run on VM)

```bash
# Check status
sudo systemctl status review-server

# Restart
sudo systemctl restart review-server

# View logs
sudo journalctl -u review-server -f

# Stop
sudo systemctl stop review-server
```

## Claude CLI (run on VM)

```bash
# Test auth
claude -p "Say hello" --max-turns 1

# Re-login if needed
claude login
```

## VM Management (run from anywhere with gcloud)

```bash
# Stop VM (saves money when not in use)
gcloud compute instances stop review-server \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4

# Start VM
gcloud compute instances start review-server \
  --zone=us-central1-a \
  --project=project-30e8d102-d40c-4a2e-8b4
```

Note: the external IP (34.71.141.39) is ephemeral. If you stop and start the VM, it may change. Check the GCP console for the new IP if that happens.
