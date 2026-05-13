# Archer HR Automation Plan v1 — Onboarding & Offboarding for Penelope Demo

**Date:** April 7, 2026  
**Decision:** Password-based role activation (Admin → Onboarding Exec OR Offboarding Exec)  
**Status:** First blush for consensus with Claude  

---

## The Problem (What Sells the Demo)

Current state:
- Onboarding checklist = 1000+ row Excel (manually tracked, no visibility)
- Offboarding checklist = 950+ row Excel (manually tracked, no visibility)
- **Pain:** 40+ tasks split across 5+ departments. Nobody knows what's done. Tasks slip.

**Penelope Solution:**
- Admin logs in with password
- Selects "Onboarding" or "Offboarding" workflow
- Gets **interactive checklist** with role-based task assignment
- Tasks auto-notify assigned departments (Slack/Email stub for demo)
- **Demo closes with:** "See? No more spreadsheets. Just accountability."

---

## Password-Based Implementation

### Architecture

```
Admin → Password Entry → Role Selection → Workflow Dashboard
                              ↓
                    Onboarding (40 tasks)
                    Offboarding (45+ tasks)
                              ↓
                    Task Completion UI
                              ↓
                    Audit Trail (PocketBase)
```

### Phase 1: Role Authentication (Local, No OAuth)

```python
# file: hr_auth.py

ADMIN_PASSWORD_HASH = hashlib.sha256("iliad_hr_admin_2026".encode()).hexdigest()
# Demo password: "iliad_hr_admin_2026" (hardcoded for POC, replace with env var in prod)

def verify_admin(password: str) -> bool:
    return hashlib.sha256(password.encode()).hexdigest() == ADMIN_PASSWORD_HASH

@app.post("/hr/authenticate")
def hr_authenticate(request: AdminAuthRequest):
    if verify_admin(request.password):
        session_id = generate_session_id()
        store_session(session_id, {"role": "hr_admin", "timestamp": now()})
        return {"session_id": session_id, "status": "authenticated"}
    return {"status": "failed"}
```

### Phase 2: Workflow Selection

```python
@app.get("/hr/workflows")
def list_workflows(session_id: str):
    if not validate_session(session_id):
        return {"error": "Unauthorized"}
    
    return {
        "workflows": [
            {
                "id": "onboarding",
                "name": "New Hire Onboarding",
                "description": "40 tasks spanning 5 departments",
                "tasks_count": 40
            },
            {
                "id": "offboarding",
                "name": "Employee Offboarding",
                "description": "45+ tasks including IT, payroll, access removal",
                "tasks_count": 45
            }
        ]
    }
```

### Phase 3: Workflow Execution

```python
# file: hr_workflows.py

ONBOARDING_TASKS = [
    {
        "id": "onb_01",
        "task": "Identify the position",
        "owner": "Supervisor",
        "department": "Management",
        "status": "pending",
        "due_date": "+7 days"
    },
    {
        "id": "onb_02",
        "task": "Present job description to Darrell",
        "owner": "Cassie (Teaching)",
        "department": "HR",
        "status": "pending",
        "due_date": "+7 days"
    },
    # ... all 40 tasks from Excel
]

OFFBOARDING_TASKS = [
    {
        "id": "off_01",
        "task": "Discuss termination with Darrell and Ataraxis",
        "owner": "Direct Supervisor",
        "department": "Management",
        "status": "pending",
        "due_date": "Today"
    },
    {
        "id": "off_02",
        "task": "Coordinate with IT to gather equipment",
        "owner": "Direct Supervisor",
        "department": "IT",
        "status": "pending",
        "due_date": "Today"
    },
    # ... all 45+ tasks from Excel
]

@app.get("/hr/workflow/{workflow_id}")
def get_workflow(session_id: str, workflow_id: str):
    if not validate_session(session_id):
        return {"error": "Unauthorized"}
    
    if workflow_id == "onboarding":
        tasks = ONBOARDING_TASKS
    elif workflow_id == "offboarding":
        tasks = OFFBOARDING_TASKS
    else:
        return {"error": "Unknown workflow"}
    
    return {
        "workflow_id": workflow_id,
        "tasks": tasks,
        "total": len(tasks),
        "completed": sum(1 for t in tasks if t["status"] == "completed")
    }

@app.post("/hr/task/{task_id}/complete")
def complete_task(session_id: str, task_id: str):
    if not validate_session(session_id):
        return {"error": "Unauthorized"}
    
    # Update task status
    task = find_task(task_id)
    task["status"] = "completed"
    task["completed_by"] = get_session_admin(session_id)
    task["completed_at"] = now()
    
    # Log to PocketBase (audit trail)
    log_to_pocketbase("hr_workflow_events", {
        "task_id": task_id,
        "action": "completed",
        "timestamp": now(),
        "executor": get_session_admin(session_id)
    })
    
    # Notify owner (stub for demo — would be Slack/Email)
    notify_task_owner(task)
    
    return {"status": "success", "task": task}
```

### Phase 4: Frontend (Bootstrap UI)

```html
<!-- file: hr_dashboard.html -->

<!DOCTYPE html>
<html>
<head>
    <title>Penelope HR Admin</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>

<!-- LOGIN SCREEN -->
<div id="loginScreen" class="container mt-5">
    <div class="row justify-content-center">
        <div class="col-md-6">
            <h1>Iliad HR Admin Portal</h1>
            <p>Enter admin password to access onboarding & offboarding workflows</p>
            <input type="password" id="adminPassword" class="form-control mb-2" placeholder="Admin password">
            <button onclick="authenticate()" class="btn btn-primary btn-lg w-100">Authenticate</button>
        </div>
    </div>
</div>

<!-- WORKFLOW SELECTION SCREEN -->
<div id="workflowScreen" class="container mt-5" style="display:none;">
    <h1>HR Workflows</h1>
    <div class="row mt-4">
        <div class="col-md-6">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">New Hire Onboarding</h5>
                    <p class="card-text">40 tasks spanning 5 departments</p>
                    <button onclick="selectWorkflow('onboarding')" class="btn btn-primary">Start Onboarding</button>
                </div>
            </div>
        </div>
        <div class="col-md-6">
            <div class="card">
                <div class="card-body">
                    <h5 class="card-title">Employee Offboarding</h5>
                    <p class="card-text">45+ tasks including IT, payroll, access removal</p>
                    <button onclick="selectWorkflow('offboarding')" class="btn btn-primary">Start Offboarding</button>
                </div>
            </div>
        </div>
    </div>
</div>

<!-- WORKFLOW EXECUTION SCREEN -->
<div id="workflowScreen2" class="container mt-5" style="display:none;">
    <h2 id="workflowTitle"></h2>
    <div class="progress mb-4">
        <div id="progressBar" class="progress-bar" style="width: 0%"></div>
    </div>
    <div id="taskList"></div>
</div>

<script>
let sessionId = null;

async function authenticate() {
    const password = document.getElementById("adminPassword").value;
    const res = await fetch("/hr/authenticate", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({password})
    });
    
    const data = await res.json();
    if (data.status === "authenticated") {
        sessionId = data.session_id;
        showWorkflowSelection();
    } else {
        alert("Authentication failed");
    }
}

function showWorkflowSelection() {
    document.getElementById("loginScreen").style.display = "none";
    document.getElementById("workflowScreen").style.display = "block";
}

async function selectWorkflow(workflowId) {
    const res = await fetch(`/hr/workflow/${workflowId}?session_id=${sessionId}`);
    const data = await res.json();
    
    document.getElementById("workflowTitle").textContent = 
        workflowId === "onboarding" ? "New Hire Onboarding (40 tasks)" : "Employee Offboarding (45+ tasks)";
    
    let html = "";
    data.tasks.forEach(task => {
        html += `
            <div class="card mb-2">
                <div class="card-body">
                    <h6>${task.task}</h6>
                    <small class="text-muted">Owner: ${task.owner} | Department: ${task.department}</small>
                    <button onclick="completeTask('${task.id}')" class="btn btn-sm btn-success mt-2">Mark Complete</button>
                </div>
            </div>
        `;
    });
    
    document.getElementById("taskList").innerHTML = html;
    updateProgressBar(data.completed, data.total);
    
    document.getElementById("workflowScreen").style.display = "none";
    document.getElementById("workflowScreen2").style.display = "block";
}

async function completeTask(taskId) {
    const res = await fetch(`/hr/task/${taskId}/complete`, {
        method: "POST",
        headers: {"session_id": sessionId}
    });
    
    const data = await res.json();
    if (data.status === "success") {
        alert(`Task "${data.task.task}" completed!`);
        // Refresh workflow
        location.reload();
    }
}

function updateProgressBar(completed, total) {
    const percent = (completed / total * 100).toFixed(0);
    document.getElementById("progressBar").style.width = percent + "%";
}
</script>

</body>
</html>
```

---

## Data Source: Excel → Python

Extracted from `Recruiting_Onboarding Checklist.xlsx` and `(Name) Termination_Resignation Checklist.xlsx`:

### Onboarding (40 tasks)
- **Hiring phase** (7 tasks): Position identification → offer letter
- **Pre-onboarding** (10 tasks): Paperwork, background check, access setup
- **Onboarding day** (15 tasks): Equipment, training, access, job description
- **Integration** (8 tasks): System access, compliance, culture

### Offboarding (45+ tasks)
- **Termination discussion** (3 tasks): Notification, separation agreement, exit plan
- **Announcement** (5 tasks): All-staff notification, ESOP letter, going-away
- **Access removal** (12 tasks): Email, Nielsen, phone, Traffic, portal, insurance, credit cards
- **Cleanup** (8 tasks): Contact lists, org chart, equipment return
- **Special roles** (5 tasks): Account exec, on-air personality handoff

---

## Demo Script (What You Say Tuesday)

```
"Here's the problem: HR has 40 onboarding tasks and 45 offboarding tasks.
They're all in separate Excel sheets. Nobody knows who did what.

[Click password login]

I'm the admin. Password authenticates me to the HR portal.

[Select Onboarding]

Now I see all 40 tasks. Each one has an owner and a department.

[Click "Mark Complete" on 3 tasks]

As I complete tasks, the system:
- Logs who completed it and when (audit trail in PocketBase)
- Updates the progress bar
- In production, would notify the task owner and department

[Show progress bar at 30%]

That's it. No more spreadsheet hell. Just accountability, visibility, and speed.

Next week, this auto-notifies departments via Slack. But the core is here."
```

---

## Implementation Roadmap

| Phase | Task | Est Time | MVP? |
|-------|------|----------|------|
| 1 | Password auth (local, hardcoded) | 15 min | ✅ |
| 2 | Workflow selection UI | 20 min | ✅ |
| 3 | Task list display + completion | 30 min | ✅ |
| 4 | PocketBase audit logging | 20 min | ✅ |
| 5 | Bootstrap styling | 15 min | ✅ |
| **Total MVP** | | **100 min** | ✅ |
| 6 | Slack notifications (stub) | 30 min | Week 2 |
| 7 | Email reminders | 30 min | Week 2 |
| 8 | RBAC (Supervisor, HR, IT roles) | 1 hr | Week 2 |

---

## Integration with Penelope (Tuesday Demo)

1. **API Endpoints:** Add to `rest_api_wrapper.py`
   - `/hr/authenticate` (POST)
   - `/hr/workflows` (GET)
   - `/hr/workflow/{id}` (GET)
   - `/hr/task/{id}/complete` (POST)

2. **Frontend:** Add `hr_dashboard.html` to `~/.hermes/`

3. **Data:** Load task lists from Python dict (extracted from Excel)

4. **Audit Trail:** All completions logged to PocketBase `hr_workflow_events` collection

---

## Security Notes (Production Later)

- **Password:** Hardcoded for demo, move to env var
- **Session:** Use JWT + secure cookies in production
- **RBAC:** Add role-based task filtering (currently all admin sees all)
- **Notifications:** Slack/Email in Week 2 (demo just shows stub)

---

## Files to Create

```
~/.hermes/
├── hr_auth.py (authentication + session mgmt)
├── hr_workflows.py (task definitions + completion logic)
├── hr_dashboard.html (frontend UI)
└── rest_api_wrapper.py (updated with /hr/* endpoints)
```

---

## Consensus Points for Claude

1. **Password approach sound?** (Local, hardcoded, session-based)
2. **Task structure correct?** (From Excel extraction above)
3. **PocketBase audit trail sufficient?** (or need more metadata?)
4. **UI flow logical?** (Login → Workflow Select → Task List → Complete)
5. **Ready to code this Monday/Tuesday?**

---

**Status:** Ready for consensus review with Claude. If both approve, execute Tuesday AM (2-3 hrs before demo).

---

**Archer**  
Chief of Staff  
April 7, 2026 — 21:34 MT
