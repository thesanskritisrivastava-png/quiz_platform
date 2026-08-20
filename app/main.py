from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Generator, Optional

import jwt
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import Boolean, DateTime, Enum as SqlEnum, Float, ForeignKey, Integer
from sqlalchemy import String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship


DATABASE_URL = "sqlite:///./quiz_platform.db"
JWT_SECRET = "change-this-secret-in-production"
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class Base(DeclarativeBase):
    pass


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    STUDENT = "STUDENT"


class QuizStatus(str, Enum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    UNPUBLISHED = "UNPUBLISHED"


class AttemptStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), default=UserRole.STUDENT)
    status: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    attempts: Mapped[list["Attempt"]] = relationship(back_populates="user")


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Quiz(Base):
    __tablename__ = "quizzes"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    difficulty: Mapped[str] = mapped_column(String(30))
    duration: Mapped[int] = mapped_column(Integer)
    passing_score: Mapped[float] = mapped_column(Float)
    max_attempts: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[QuizStatus] = mapped_column(SqlEnum(QuizStatus), default=QuizStatus.DRAFT)
    questions: Mapped[list["Question"]] = relationship(
        back_populates="quiz", cascade="all, delete-orphan"
    )


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    question_text: Mapped[str] = mapped_column(Text)
    marks: Mapped[float] = mapped_column(Float, default=1)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quiz: Mapped["Quiz"] = relationship(back_populates="questions")
    options: Mapped[list["Option"]] = relationship(
        back_populates="question", cascade="all, delete-orphan"
    )


class Option(Base):
    __tablename__ = "options"

    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"))
    option_text: Mapped[str] = mapped_column(Text)
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    question: Mapped["Question"] = relationship(back_populates="options")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[int] = mapped_column(primary_key=True)
    quiz_id: Mapped[int] = mapped_column(ForeignKey("quizzes.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[float] = mapped_column(Float, default=0)
    percentage: Mapped[float] = mapped_column(Float, default=0)
    correct_answers: Mapped[int] = mapped_column(Integer, default=0)
    incorrect_answers: Mapped[int] = mapped_column(Integer, default=0)
    unanswered: Mapped[int] = mapped_column(Integer, default=0)
    time_taken: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[Optional[AttemptStatus]] = mapped_column(SqlEnum(AttemptStatus), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    user: Mapped["User"] = relationship(back_populates="attempts")


class UserCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: Optional[str] = None


class QuizCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category_id: int
    difficulty: str
    duration: int = Field(gt=0)
    passing_score: float = Field(ge=0, le=100)
    max_attempts: int = Field(default=0, ge=0)
    status: QuizStatus = QuizStatus.DRAFT


class OptionCreate(BaseModel):
    option_text: str
    is_correct: bool = False


class QuestionCreate(BaseModel):
    question_text: str
    marks: float = Field(default=1, gt=0)
    explanation: Optional[str] = None
    options: list[OptionCreate] = Field(min_length=2)


class AnswerInput(BaseModel):
    question_id: int
    selected_option_id: Optional[int] = None


class QuizSubmit(BaseModel):
    answers: list[AnswerInput]


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: EmailStr
    role: UserRole
    status: bool


class QuizOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    description: Optional[str]
    category_id: int
    difficulty: str
    duration: int
    passing_score: float
    max_attempts: int
    status: QuizStatus


Base.metadata.create_all(engine)

app = FastAPI(
    title="Quiz Management API",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db() -> Generator[Session, None, None]:
    with Session(engine) as db:
        yield db


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_token(user: User) -> str:
    expiry = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES)
    return jwt.encode(
        {"sub": str(user.id), "role": user.role.value, "exp": expiry},
        JWT_SECRET,
        algorithm=JWT_ALGORITHM,
    )


def current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, TypeError, ValueError):
        raise credentials_error
    user = db.get(User, user_id)
    if user is None or not user.status:
        raise credentials_error
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    if db.scalar(select(User).where(User.email == payload.email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(
    name=payload.name,
    email=payload.email,
    password_hash=hash_password(payload.password),
    role=UserRole.ADMIN if payload.email == "admin@quiz.com" else UserRole.STUDENT,
)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.post("/api/auth/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
) -> Token:
    user = db.scalar(select(User).where(User.email == form_data.username))
    if user is None or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect email or password")
    return Token(access_token=create_token(user))


@app.get("/api/users/me", response_model=UserOut)
def me(user: User = Depends(current_user)) -> User:
    return user


@app.post("/api/categories", status_code=201)
def create_category(
    payload: CategoryCreate, db: Session = Depends(get_db), _: User = Depends(admin_user)
):
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@app.get("/api/categories")
def list_categories(db: Session = Depends(get_db)):
    return list(db.scalars(select(Category).order_by(Category.name)))


@app.post("/api/quizzes", response_model=QuizOut, status_code=201)
def create_quiz(
    payload: QuizCreate, db: Session = Depends(get_db), _: User = Depends(admin_user)
) -> Quiz:
    if db.get(Category, payload.category_id) is None:
        raise HTTPException(status_code=404, detail="Category not found")
    quiz = Quiz(**payload.model_dump())
    db.add(quiz)
    db.commit()
    db.refresh(quiz)
    return quiz


@app.get("/api/quizzes", response_model=list[QuizOut])
def list_quizzes(
    category_id: Optional[int] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = Query(default=None, min_length=1),
    db: Session = Depends(get_db),
) -> list[Quiz]:
    query = select(Quiz).where(Quiz.status == QuizStatus.PUBLISHED)
    if category_id is not None:
        query = query.where(Quiz.category_id == category_id)
    if difficulty:
        query = query.where(Quiz.difficulty == difficulty)
    if search:
        query = query.where(Quiz.title.ilike(f"%{search}%"))
    return list(db.scalars(query.order_by(Quiz.id.desc())))


@app.post("/api/quizzes/{quiz_id}/questions", status_code=201)
def add_question(
    quiz_id: int,
    payload: QuestionCreate,
    db: Session = Depends(get_db),
    _: User = Depends(admin_user),
):
    quiz = db.get(Quiz, quiz_id)
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found")
    if sum(option.is_correct for option in payload.options) != 1:
        raise HTTPException(status_code=400, detail="Exactly one option must be correct")
    question = Question(
        quiz_id=quiz_id,
        question_text=payload.question_text,
        marks=payload.marks,
        explanation=payload.explanation,
        options=[Option(**option.model_dump()) for option in payload.options],
    )
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@app.post("/api/quizzes/{quiz_id}/start")
def start_quiz(
    quiz_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)
) -> dict[str, int | str]:
    quiz = db.get(Quiz, quiz_id)
    if quiz is None or quiz.status != QuizStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Published quiz not found")
    attempts = db.scalar(
        select(Attempt).where(Attempt.quiz_id == quiz_id, Attempt.user_id == user.id)
    )
    if quiz.max_attempts and attempts is not None:
        count = len(
            list(
                db.scalars(
                    select(Attempt).where(
                        Attempt.quiz_id == quiz_id, Attempt.user_id == user.id
                    )
                )
            )
        )
        if count >= quiz.max_attempts:
            raise HTTPException(status_code=400, detail="Maximum attempts reached")
    attempt = Attempt(quiz_id=quiz_id, user_id=user.id)
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return {"attempt_id": attempt.id, "duration_minutes": quiz.duration}


@app.post("/api/attempts/{attempt_id}/submit")
def submit_quiz(
    attempt_id: int,
    payload: QuizSubmit,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict[str, int | float | str]:
    attempt = db.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != user.id:
        raise HTTPException(status_code=404, detail="Attempt not found")
    if attempt.completed_at is not None:
        raise HTTPException(status_code=400, detail="Attempt already submitted")

    quiz = db.get(Quiz, attempt.quiz_id)
    questions = list(db.scalars(select(Question).where(Question.quiz_id == quiz.id)))
    submitted = {answer.question_id: answer.selected_option_id for answer in payload.answers}
    total_marks = sum(question.marks for question in questions)
    obtained_marks = 0.0
    correct = 0
    unanswered = 0

    for question in questions:
        selected_id = submitted.get(question.id)
        if selected_id is None:
            unanswered += 1
            continue
        correct_option = next((option for option in question.options if option.is_correct), None)
        if correct_option and selected_id == correct_option.id:
            correct += 1
            obtained_marks += question.marks

    incorrect = len(questions) - correct - unanswered
    percentage = round((obtained_marks / total_marks) * 100, 2) if total_marks else 0
    attempt.score = obtained_marks
    attempt.percentage = percentage
    attempt.correct_answers = correct
    attempt.incorrect_answers = incorrect
    attempt.unanswered = unanswered
    attempt.time_taken = int((datetime.now(timezone.utc) - attempt.started_at).total_seconds())
    attempt.status = (
        AttemptStatus.PASSED if percentage >= quiz.passing_score else AttemptStatus.FAILED
    )
    attempt.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "attempt_id": attempt.id,
        "score": attempt.score,
        "percentage": attempt.percentage,
        "correct_answers": correct,
        "incorrect_answers": incorrect,
        "unanswered": unanswered,
        "status": attempt.status.value,
    }


@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)) -> list[dict[str, int | str | float]]:
    users = list(db.scalars(select(User).where(User.role == UserRole.STUDENT)))
    rows = []
    for user in users:
        attempts = list(
            db.scalars(
                select(Attempt).where(
                    Attempt.user_id == user.id, Attempt.completed_at.is_not(None)
                )
            )
        )
        if attempts:
            rows.append(
                {
                    "student": user.name,
                    "average_score": round(
                        sum(attempt.percentage for attempt in attempts) / len(attempts), 2
                    ),
                    "quizzes_completed": len(attempts),
                }
            )
    rows.sort(key=lambda row: row["average_score"], reverse=True)
    for rank, row in enumerate(rows, start=1):
        row["rank"] = rank
    return rows
