from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool, StrictStr
from starlette.exceptions import HTTPException as StarletteHTTPException

import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # create tasks.db, the table and the seed rows if needed
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Task API",
    version="1.0",
    description="A small to-do list API with full CRUD. Data lives in memory only "
    "and is lost when the server restarts.",
)


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


class Task(BaseModel):
    id: int
    title: str
    done: bool


class TaskIn(BaseModel):
    title: Optional[StrictStr] = None
    done: Optional[StrictBool] = None


class Error(BaseModel):
    error: str


NOT_FOUND = {404: {"model": Error, "description": "No task with that id"}}
BAD_REQUEST = {400: {"model": Error, "description": "Missing, empty or invalid input"}}


def find_task(task_id: int):
    for task in tasks:
        if task["id"] == task_id:
            return task
    raise HTTPException(status_code=404, detail=f"Task {task_id} not found")


@app.get("/", summary="API info", description="Describes this API and lists its endpoints.")
def root():
    return {"name": "Task API", "version": "1.0", "endpoints": ["/tasks"]}


@app.get("/health", summary="Health check", description="Returns ok if the server is alive.")
def health():
    return {"status": "ok"}


@app.get(
    "/tasks",
    response_model=list[Task],
    tags=["tasks"],
    summary="List all tasks",
    description="Returns every task currently in memory.",
)
def list_tasks():
    return tasks


@app.get(
    "/tasks/{task_id}",
    response_model=Task,
    responses=NOT_FOUND,
    tags=["tasks"],
    summary="Get one task",
    description="Returns the task with the given id, or 404 if it does not exist.",
)
def get_task(task_id: int):
    return find_task(task_id)


@app.post(
    "/tasks",
    status_code=201,
    response_model=Task,
    responses=BAD_REQUEST,
    tags=["tasks"],
    summary="Create a task",
    description="Creates a task from a JSON body with a non-empty `title`. "
    "The server assigns the next free id and sets `done` to false.",
)
def create_task(body: TaskIn):
    global next_id
    if body.title is None or not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required and must be a non-empty string")
    task = {"id": next_id, "title": body.title.strip(), "done": False}
    next_id += 1
    tasks.append(task)
    return task


@app.put(
    "/tasks/{task_id}",
    response_model=Task,
    responses={**BAD_REQUEST, **NOT_FOUND},
    tags=["tasks"],
    summary="Update a task",
    description="Changes a task's `title` and/or `done`. Send at least one of them. "
    "Unknown id gives 404; an empty or invalid body gives 400.",
)
def update_task(task_id: int, body: TaskIn):
    task = find_task(task_id)  # 404 if unknown
    if body.title is None and body.done is None:
        raise HTTPException(status_code=400, detail="Provide a title and/or done")
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=400, detail="title must be a non-empty string")
        task["title"] = body.title.strip()
    if body.done is not None:
        task["done"] = body.done
    return task


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    responses=NOT_FOUND,
    tags=["tasks"],
    summary="Delete a task",
    description="Removes the task. Returns 204 with an empty body, or 404 if the id is unknown.",
)
def delete_task(task_id: int):
    tasks.remove(find_task(task_id))  # 404 if unknown
    return Response(status_code=204)


def custom_openapi():
    """Hide FastAPI's default 422 entry: this API reports invalid input as 400."""
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
    for path in schema["paths"].values():
        for operation in path.values():
            operation["responses"].pop("422", None)
    schema["components"]["schemas"].pop("HTTPValidationError", None)
    schema["components"]["schemas"].pop("ValidationError", None)
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
