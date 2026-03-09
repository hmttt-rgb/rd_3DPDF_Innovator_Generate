# Troubleshooting Log

Record problems encountered in production and the steps taken to resolve them.

---

## Template

```
## YYYY-MM-DD – [Short description of the issue]

**Reported by:** [Name / Team]
**Server(s):** [pkv0199 / pkv0198 / User PC]
**Severity:** [Critical / High / Medium / Low]

### Symptoms
[What the user/operator observed]

### Root Cause
[What was found]

### Resolution
[Steps taken to fix]

### Prevention
[Changes made to prevent recurrence]
```

---

## Common Issues

### Job stuck in "Processing 3DPDF"

**Symptoms:** A job remains in `Processing 3DPDF` status for more than 30 minutes.

**Likely Causes:**
- CATIA process hung or crashed
- GPU DDA device went offline

**Resolution:**
1. RDP to the server (pkv0199 or pkv0198).
2. Open Task Manager and check for a stalled `CATIA.exe` process.
3. If found, terminate it.
4. Set the job status to `Error` in the Job DB and notify the requester.
5. Verify the GPU is visible in Device Manager. If not, see `env-setup/gpu-dda/README.md`.

---

### Job stuck in "Waiting for file upload"

**Symptoms:** A job remains in `Waiting for file upload` status for more than 10 minutes.

**Likely Causes:**
- Innovator server unreachable from pkv0199
- Service account credentials expired

**Resolution:**
1. Test connectivity: `ping innovator-server` from pkv0199.
2. Check service account password expiry in Active Directory.
3. Update credentials in `config.json` if needed and restart the Job Manager service.

---

### API server not responding

**Symptoms:** Auto-generator on User PCs receives connection timeout errors.

**Likely Causes:**
- Task Scheduler task did not start after a server reboot
- Port 8080 blocked by Windows Firewall

**Resolution:**
1. Check Task Scheduler on pkv0199: `\3DPDF\ApiServerStartup` should be in *Running* or *Ready* state.
2. Start the task manually if needed.
3. Verify firewall rule: `netsh advfirewall firewall show rule name="3DPDF API"`.
