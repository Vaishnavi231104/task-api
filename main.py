from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StrictBool, StrictStr
from starlette.exceptions import HTTPException as StarletteHTTPException

import auth
import db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()  # create tasks.db, the table and the seed rows if needed
    auth.startup_check()  # logs whether Supabase is reachable; never blocks startup
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Task API",
    version="1.0",
    description="A small to-do list API with full CRUD (tasks stored in SQLite) plus "
    "Supabase-backed authentication: sign up, log in, log out and token-protected routes. "
    "To call a locked route here: log in via POST /auth/login, click **Authorize** and paste the access_token.",
)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    # Every error is {"error": "..."} as the assignment requires.
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail},
        headers=getattr(exc, "headers", None),  # e.g. WWW-Authenticate on 401
    )


@app.exception_handler(RequestValidationError)
async def bad_request(request: Request, exc: RequestValidationError):
    # Malformed JSON or wrong types -> 400 (FastAPI's default would be 422).
    return JSONResponse(status_code=400, content={"error": "Invalid request body"})


app.include_router(auth.router)


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


def get_or_404(task_id: int):
    task = db.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


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
    description="Returns every task stored in the database.",
)
def list_tasks():
    return db.list_tasks()


@app.get(
    "/tasks/{task_id}",
    response_model=Task,
    responses=NOT_FOUND,
    tags=["tasks"],
    summary="Get one task",
    description="Returns the task with the given id, or 404 if it does not exist.",
)
def get_task(task_id: int):
    return get_or_404(task_id)


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
    if body.title is None or not body.title.strip():
        raise HTTPException(status_code=400, detail="title is required and must be a non-empty string")
    return db.create_task(body.title.strip())


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
    task = get_or_404(task_id)  # 404 if unknown
    if body.title is None and body.done is None:
        raise HTTPException(status_code=400, detail="Provide a title and/or done")
    title, done = task["title"], task["done"]
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(status_code=400, detail="title must be a non-empty string")
        title = body.title.strip()
    if body.done is not None:
        done = body.done
    return db.update_task(task_id, title, done)


@app.delete(
    "/tasks/{task_id}",
    status_code=204,
    responses=NOT_FOUND,
    tags=["tasks"],
    summary="Delete a task",
    description="Removes the task. Returns 204 with an empty body, or 404 if the id is unknown.",
)
def delete_task(task_id: int):
    if not db.delete_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
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


if __name__ == "__main__":
    import uvicorn

    import config

    uvicorn.run("main:app", port=config.PORT)
