# Operations Log

Record significant operational events, configuration changes, and maintenance activities here.

---

## Template

```
## YYYY-MM-DD – [Short description]

**Operator:** [Name]
**Server(s):** [pkv0199 / pkv0198 / User PC]
**Impact:** [None / Low / Medium / High]

### What was done
[Description]

### Result
[Outcome]
```

---

## 2024-01-01 – Initial system deployment

**Operator:** System Administrator
**Server(s):** pkv0199, pkv0198
**Impact:** High

### What was done
- Configured Hyper-V GPU DDA on pkv0199 for CATIA rendering
- Deployed API server and Job Manager services
- Created Task Scheduler tasks for automatic startup
- Configured shared folders for PDF input/output

### Result
System operational. Auto-generator on Innovator client PCs can successfully submit and monitor 3DPDF generation jobs.
