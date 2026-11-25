"""Task state transitions are explicit; illegal jumps are rejected."""
from opencompany.domain import TaskStatus
_ALLOWED={
 TaskStatus.DISCOVERED:{TaskStatus.READY,TaskStatus.BLOCKED,TaskStatus.CANCELLED},
 TaskStatus.READY:{TaskStatus.RUNNING,TaskStatus.BLOCKED,TaskStatus.CANCELLED},
 TaskStatus.RUNNING:{TaskStatus.WAITING_APPROVAL,TaskStatus.COMPLETED,TaskStatus.FAILED,TaskStatus.BLOCKED,TaskStatus.CANCELLED},
 TaskStatus.WAITING_APPROVAL:{TaskStatus.READY,TaskStatus.CANCELLED,TaskStatus.BLOCKED},
 TaskStatus.COMPLETED:{TaskStatus.VERIFIED,TaskStatus.FAILED,TaskStatus.READY},
 TaskStatus.VERIFIED:set(),TaskStatus.FAILED:{TaskStatus.READY,TaskStatus.CANCELLED},
 TaskStatus.BLOCKED:{TaskStatus.READY,TaskStatus.CANCELLED},TaskStatus.CANCELLED:set()
}
def transition(current:TaskStatus,target:TaskStatus)->TaskStatus:
 if target not in _ALLOWED[current]: raise ValueError(f"Illegal task transition: {current.value} -> {target.value}")
 return target
