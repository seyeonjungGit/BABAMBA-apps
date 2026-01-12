from typing import List, Optional
from sqlmodel import SQLModel, create_engine, Session, select
from sqlalchemy.pool import QueuePool
from common import config
from common.models import Employee, User

# Database URL
DATABASE_URL = (
    f"mysql+mysqlconnector://{config.DATABASE_USER}:{config.DATABASE_PASSWORD}@"
    f"{config.DATABASE_HOST}:{config.DATABASE_PORT}/"
    f"{config.DATABASE_DB_NAME}"
)

# Create the engine with connection pooling
# pool_size: The number of connections to keep open in the pool.
# max_overflow: The number of connections that can be opened beyond the pool_size.
# pool_recycle: Recycle connections after this many seconds. Prevents stale connections.
engine = create_engine(
    DATABASE_URL,
    echo=False, # Set to True to see SQL statements
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600 # Recycle connections after 1 hour
)

def create_db_and_tables():
    """
    Create database tables if they do not exist.
    Safe to call multiple times.
    """
    try:
        SQLModel.metadata.create_all(engine)
        print("✅ Database tables created or already exist")
    except Exception as e:
        print("❌ Failed to create database tables")
        print(e)
        raise

def get_session():
    """Dependency to get a database session."""
    with Session(engine) as session:
        yield session

def list_employees(owner_id: int) -> List[Employee]:
    """[수정] 특정 유저(owner_id)가 등록한 직원 목록만 가져옵니다."""
    with Session(engine) as session:
        # WHERE 절을 추가하여 본인 데이터만 필터링합니다.
        statement = select(Employee).where(Employee.owner_id == owner_id).order_by(Employee.full_name.desc())
        employees = session.exec(statement).all()
        return employees

def load_employee(employee_id: int) -> Optional[Employee]:
    """직원 단건 조회"""
    with Session(engine) as session:
        employee = session.get(Employee, employee_id)
        return employee

def add_employee(employee_data: Employee) -> Employee:
    """[확인] employee_data에 이미 owner_id가 채워진 상태로 들어옵니다."""
    with Session(engine) as session:
        session.add(employee_data)
        session.commit()
        session.refresh(employee_data)
        return employee_data

def update_employee(employee_id: int, employee_data: Employee) -> Optional[Employee]:
    """[수정] 직원을 업데이트합니다."""
    with Session(engine) as session:
        existing_employee = session.get(Employee, employee_id)
        if not existing_employee:
            return None
        
        # 클라이언트에서 넘어온 데이터로 업데이트
        # owner_id는 보안을 위해 보통 업데이트하지 않지만, 
        # employee_data에 이미 들어있으므로 exclude_unset으로 안전하게 처리합니다.
        update_data = employee_data.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(existing_employee, key, value)
        
        session.add(existing_employee)
        session.commit()
        session.refresh(existing_employee)
        return existing_employee

def delete_employee(employee_id: int):
    """Delete an employee."""
    with Session(engine) as session:
        employee = session.get(Employee, employee_id)
        if employee:
            session.delete(employee)
            session.commit()

# 1. 유저 정보 가져오기 (로그인 시 ID/비번 대조용)
def get_user_by_username(username: str) -> Optional[User]:
    with Session(engine) as session:
        # SQL: SELECT * FROM user WHERE username = :username
        statement = select(User).where(User.username == username)
        return session.exec(statement).first()

# 2. 유저 추가하기 (회원가입용)
def add_user(user_data: User) -> User:
    with Session(engine) as session:
        session.add(user_data)
        session.commit()      # DB에 실제 저장 (이때 ID 자동 생성됨)
        session.refresh(user_data) # 생성된 ID 정보를 객체에 반영
        return user_data