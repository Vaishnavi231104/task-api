from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, StrictBool, StrictStr

app = FastAPI(title="Task API")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    # Every error is {"error": "..."} as the assignment requires.
    return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    # Malformed JSON or wrong types -> 400 (FastAPI's default would be 422).
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})

# In-memory "database": gone when the server stops.
tasks = [
    {"id": 1, "title": "Learn FastAPI", "done": False},
    {"id": 2, "title": "Build a CRUD API", "done": False},
    {"id": 3, "title": "Push to GitHub", "done": False},
]


next_id = 4


class TaskIn(BaseModel):
    title: Optional[StrictStr] = None
    done: Optional[StrictBool] = None


def find_task(task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.get("/")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/tasks")
def list_tasks():
    return tasks


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    return find_task(task_id)


@app.post("/tasks", status_code=201)
def create_task(body: TaskIn):
    global next_id
    if body.title is None or not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required and must be a non-empty string")
    task = {"id": next_id, "title": body.title.strip(), "done": False}
    next_id += 1
    tasks.append(task)
    return task
