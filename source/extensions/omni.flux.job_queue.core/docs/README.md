# Overview

A lightweight job queue and workflow library that uses SQLite for persistence.

## Key Concepts

- **Job**: A unit of work that can be executed. Subclass `Job` or use `CallableJob` for simple functions.
- **JobGraph**: A collection of jobs with dependencies that are submitted together.
- **QueueInterface**: The SQLite-backed storage for jobs and their state.
- **JobExecutor**: Executes jobs using a thread/process pool.
- **JobScheduler**: Polls the queue and dispatches jobs to the executor.

## Quick Start

### Basic Example: Execute a Simple Function

```python
import concurrent.futures
from omni.flux.job_queue.core.execute import JobExecutor
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import CallableJob, JobGraph


def my_task():
    return 42


# Create a queue interface (uses SQLite)
interface = QueueInterface(db_path="jobs.db")

# Create a job graph and add a job
graph = JobGraph(interface=interface)
job = CallableJob(func=my_task)
graph.add_job(job)

# Submit the graph to the queue
queued_jobs = graph.submit()

# Execute the job
executor = JobExecutor(
    interface=interface,
    executor=concurrent.futures.ThreadPoolExecutor()
)
future = executor.execute(job.job_id)

# Get the result
result = future.result(timeout=10)
print(result)  # Output: 42
```

### Using the Scheduler

The `JobScheduler` automatically polls the queue and executes pending jobs:

```python
import concurrent.futures
from omni.flux.job_queue.core.execute import JobExecutor, JobScheduler
from omni.flux.job_queue.core.interface import QueueInterface
from omni.flux.job_queue.core.job import CallableJob, JobGraph


def process_data(x):
    return x * 2


interface = QueueInterface(db_path="jobs.db")

# Submit a job
graph = JobGraph(interface=interface)
job = CallableJob(func=process_data, args=(21,))
graph.add_job(job)
queued_jobs = graph.submit()

# Create executor and scheduler
executor = JobExecutor(
    interface=interface,
    executor=concurrent.futures.ThreadPoolExecutor()
)
scheduler = JobScheduler(interface=interface, executor=executor)

# Run the scheduler (processes 1 job, waits up to 5 seconds)
scheduler.run(num_jobs=1, timeout=5.0, poll_interval=0.1)

# Get the result
result = queued_jobs[0].result()
print(result)  # Output: 42
```

### Jobs with Dependencies

Jobs can depend on other jobs. The scheduler executes them in the correct order:

```python
from omni.flux.job_queue.core.job import CallableJob, JobGraph

graph = JobGraph(interface=interface)

# First job
job_a = CallableJob(func=lambda: "step 1 complete")
graph.add_job(job_a)

# Second job depends on the first
job_b = CallableJob(func=lambda: "step 2 complete")
job_b.add_dependency(job_a)
graph.add_job(job_b)

# Submit - jobs will execute in order: job_a, then job_b
graph.submit()
```

### Custom Job Classes

For complex jobs, subclass `Job` directly:

```python
import dataclasses
from omni.flux.job_queue.core.job import Job


@dataclasses.dataclass
class MyCustomJob(Job[str]):
    input_path: str = ""
    output_path: str = ""

    def execute(self) -> str:
        # Your custom logic here
        with open(self.input_path) as f:
            data = f.read()
        with open(self.output_path, "w") as f:
            f.write(data.upper())
        return self.output_path
```

## Job Lifecycle Hooks

Jobs have hooks that run at different stages:

| Hook | Called By | Thread/Process |
|------|-----------|----------------|
| `pre_schedule()` | `JobScheduler` | Scheduler process (main thread) |
| `post_schedule()` | `JobScheduler` | Scheduler process (main thread) |
| `pre_execute()` | `JobExecutor` | Executor worker (thread/process pool) |
| `execute()` | `JobExecutor` | Executor worker (thread/process pool) |
| `post_execute()` | `JobExecutor` | Executor worker (thread/process pool) |

The `*_schedule` hooks run in the scheduler process before/after the job is dispatched.
The `*_execute` hooks and `execute()` run in the executor's worker pool (e.g., `ThreadPoolExecutor` or `ProcessPoolExecutor`).

