# Department collaboration

AIOS provides a persisted, business-scoped internal collaboration inbox and task delegation records.

## Internal messages
- Messages stay inside the AIOS database; they are not email, social, or customer messages.
- Each message records business, sender, recipient, subject, body, optional related task, read state, and timestamps.
- Successful workflow handoffs automatically create an inbox message for the next department, carrying the completed output and next task reference.
- Writes require the owner API key; reads require the normal API key.

## Task delegation
- An owner can record a department-to-department delegation.
- Delegation creates a queued task for the receiving department and an unread inbox message.
- Creating a delegation is an explicit owner action and now queues an internal agent run automatically. The dedicated worker processes it when running.
- A supplied parent task must belong to the sender department and the same business.

## API
- GET /company/collaboration/messages?business_id=...&department=...
- POST /company/collaboration/messages
- POST /company/collaboration/messages/{message_id}/read?business_id=...&department=...
- GET /company/collaboration/delegations?business_id=...&department=...
- POST /company/collaboration/delegations

## Limits
This is durable internal messaging and supervised task delegation, not unrestricted agent-to-agent chat. The worker polls the shared run queue and automatically executes only tasks explicitly authorized by an owner-started workflow or owner-created delegation. It does not independently invent work by reading every inbox. No external account, marketplace, social, email, publishing, payment, or customer system is connected by this change.
