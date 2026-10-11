# Application Service

Team 16 - Job Portal & Recruitment System

Application Service owns job applications and application status.

## Port

8003

## Responsibilities

- Create job applications
- Maintain application status
- Run Apply-for-Job Saga
- Candidate eligibility check
- Job slot reservation
- Recruitment screening
- Saga compensation
- Saga step logging
- Best-effort notifications
- Pending notification retry

## Run

From application-service:

```bash
python run.py