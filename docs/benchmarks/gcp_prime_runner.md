# Run Prime Intellect benchmarks on Google Cloud (Compute Engine)

This runbook uses a **Linux VM on Compute Engine** so long `run_all_methods_prime_live_full.py` jobs keep running when your laptop is off. LabTrust Gym needs **Python 3.11+**. **Ubuntu 24.04** ships Python 3.12; **Debian 12 (bookworm)** ships Python 3.11 and works as-is.

**Billing:** GCP is not indefinitely free. New accounts often get **$300 trial credit**; after that you pay for vCPU, RAM, disk, and egress. Stop or delete the VM when idle to avoid charges.

## 1. One-time: gcloud and project

1. Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install).
2. Authenticate and pick a project:

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable compute.googleapis.com
```

Enable billing on the project in the Cloud Console if prompted.

## 2. Create a VM (example)

Pick a **zone** near you (e.g. `us-central1-a`). For medium_stress coordination runs, **at least 4 vCPU / 8 GB RAM** is reasonable; adjust for cost.

```bash
export ZONE=us-central1-a
export VM=labtrust-prime-runner

gcloud compute instances create "${VM}" \
  --zone="${ZONE}" \
  --machine-type=e2-standard-4 \
  --boot-disk-size=80GB \
  --image-family=ubuntu-2404-lts-amd64 \
  --image-project=ubuntu-os-cloud \
  --scopes=https://www.googleapis.com/auth/cloud-platform
```

**SSH access:** Either use your Google account (OS Login) or add `--metadata=ssh-keys=...`. Simplest path:

```bash
gcloud compute ssh "${VM}" --zone="${ZONE}"
```

**Firewall:** Default VPC usually allows SSH on port 22 from the internet when using `gcloud compute ssh` with IAP or your IP. Tighten rules in production (IAP-only SSH, no `0.0.0.0/0`).

## 3. Install LabTrust Gym on the VM

From an SSH session on the VM, either clone your fork/branch or upload a tarball. Example **public clone** (use your fork URL if you have local changes):

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip build-essential

# If you use a private repo: use a deploy key or `gcloud compute scp` from your laptop.
git clone https://github.com/YOUR_ORG/LabTrust-Gym.git
cd LabTrust-Gym
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,env,plots,llm_prime_intellect]"
```

Or run the helper (after copying the script to the VM or cloning the repo):

```bash
chmod +x scripts/gcp_vm_bootstrap.sh
./scripts/gcp_vm_bootstrap.sh https://github.com/YOUR_ORG/LabTrust-Gym.git main
cd LabTrust-Gym && source .venv/bin/activate
```

## 4. Prime API key on the VM

**Do not** commit secrets. On the VM:

```bash
install -m 600 /dev/null ~/prime.env
nano ~/prime.env
```

Add:

```bash
export PRIME_INTELLECT_API_KEY="your-key"
```

Before each session:

```bash
source ~/prime.env
```

Optional: [Secret Manager](https://cloud.google.com/secret-manager) + a small wrapper that exports the secret at login (more setup, better for teams).

## 5. Run benchmarks in the background

From the repo root with venv activated and `prime.env` sourced:

```bash
source ~/LabTrust-Gym/.venv/bin/activate
source ~/prime.env
cd ~/LabTrust-Gym

chmod +x scripts/run_prime_live_nohup.sh
./scripts/run_prime_live_nohup.sh \
  --scale-id medium_stress_signed_bus \
  --episodes 3 \
  --model anthropic/claude-3.5-haiku \
  --max-llm-error-rate 0.05 \
  --out-dir runs/gcp_prime_full
```

Tail logs:

```bash
tail -f runs/background_logs/prime_live_*.log
```

The orchestrator writes per-method results under `runs/gcp_prime_full/` (same crash-safe behavior as locally).

**tmux** (optional): start `tmux new -s labtrust`, run commands in the foreground, detach with `Ctrl-b` then `d`; reattach with `tmux attach -t labtrust`.

## 6. Copy results back to your laptop

From your **local** machine (paths are examples):

```bash
gcloud compute scp --recurse \
  "${VM}:~/LabTrust-Gym/runs/gcp_prime_full" \
  ./runs/gcp_prime_full_downloaded \
  --zone="${ZONE}"
```

Or sync to Cloud Storage and download later:

```bash
# On VM (once): create a bucket in Console or gsutil mb
gsutil -m rsync -r ~/LabTrust-Gym/runs/gcp_prime_full gs://YOUR_BUCKET/pi_runs/$(date -u +%Y%m%d)/
```

## 7. Stop or delete the VM when finished

```bash
gcloud compute instances stop "${VM}" --zone="${ZONE}"
# Or delete:
# gcloud compute instances delete "${VM}" --zone="${ZONE}"
```

Stopped VMs still incur **disk** charges unless you delete the disk.

## Existing VM checklist (Debian 12, small disk, e2-medium)

If you already have a VM (e.g. Debian 12 bookworm, `e2-medium`, 10 GB disk):

1. **Disk (10 GB is usually too small)** for a venv, full `pip install`, and `runs/` with many `episodes.jsonl` / `METHOD_TRACE.jsonl` files. Grow the boot disk, then extend the filesystem.

   From your laptop (VM stopped or running — GCP allows online resize for many configs):

   ```bash
   gcloud compute disks resize DISK_NAME --zone=ZONE --size=40
   ```

   On the VM (device name may be `sda`; check with `lsblk`):

   ```bash
   sudo apt-get install -y cloud-guest-utils
   sudo growpart /dev/sda 1
   sudo resize2fs /dev/sda1
   df -h /
   ```

2. **`e2-medium` (2 vCPU, 4 GiB RAM)** can run `medium_stress_signed_bus` but full Prime-live sweeps are slower and may OOM on the heaviest methods. If you see kills or heavy swap, stop the VM and change machine type to `e2-standard-4` (or larger) in the console or via `gcloud compute instances set-machine-type`.

3. **SSH** (replace project, zone, name):

   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud compute ssh labtrustgym --zone=us-central1-c
   ```

4. **Install** uses the same `apt` / `venv` / `pip install -e ".[dev,env,plots,llm_prime_intellect]"` steps as above; on Debian use `apt-get` instead of `apt` if you prefer.

5. **GCS uploads:** If the instance service account only has `devstorage.read_only`, `gsutil rsync` to your bucket may fail with permission errors. Either grant the VM’s default compute SA **Storage Object Admin** on the target bucket, or recreate the VM with `--scopes=https://www.googleapis.com/auth/cloud-platform` (broader; use least privilege in production).

## Troubleshooting

- **Out of memory:** Use a larger machine type (e.g. `e2-standard-8`) or fewer parallel workloads.
- **SSH hangs:** Check firewall, IAP settings, and that the instance is `RUNNING`.
- **Prime timeouts:** Same tuning as local (retries, `coord_*` scale settings); VM egress must reach Prime’s API endpoint.

## Related

- `scripts/run_prime_live_nohup.sh` — detached process + logs.
- `scripts/run_all_methods_prime_live_full.py` — full orchestrator.
- [Prime Intellect Inference](prime_intellect_inference.md) — env vars and backends.
