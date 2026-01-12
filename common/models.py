from datetime import datetime
from typing import Optional, List # List is needed for EmployeesResponse
from sqlmodel import Field, SQLModel
from pydantic import BaseModel # Added for EmployeesResponse

class Employee(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    object_key: Optional[str] = Field(default=None, max_length=80)
    full_name: str = Field(max_length=200)
    location: str = Field(max_length=200)
    job_title: str = Field(max_length=200)
    badges: str = Field(max_length=200)
    created_datetime: datetime = Field(default_factory=datetime.now)
    owner_id: int = Field(foreign_key="user.id", nullable=False)

    class Config:
        json_encoders = {
            datetime: lambda dt: dt.isoformat()
        }

# Define a Pydantic model for the public representation of an Employee
class EmployeePublic(BaseModel):
    id: int
    object_key: Optional[str] = None
    full_name: str  
    location: str
    job_title: str
    badges: str
    photo_url: Optional[str] = None # Add photo_url as it's generated in the app
    owner_id: int
    class Config:
        from_attributes = True # Enable ORM mode for Pydantic to read from SQLModel instances (Pydantic V2)
# Define a type alias for the list response
EmployeesListResponse = List[EmployeePublic]


from sqlmodel import SQLModel, Field
from typing import Optional

class User(SQLModel, table=True):
    # 1. ID 번호 (사번)
    # primary_key=True: DB가 중복되지 않게 관리하며, 1씩 자동으로 증가시킵니다 (Auto Increment).
    id: Optional[int] = Field(default=None, primary_key=True)

    # 2. 아이디 (Login ID)
    # unique=True: 똑같은 아이디로 가입하는 것을 DB 레벨에서 막아줍니다.
    # index=True: 로그인 시 검색 속도를 빠르게 합니다 (C++의 Map처럼 인덱싱 처리).
    username: str = Field(unique=True, index=True, nullable=False)

    # 3. 비밀번호
    # 암호화(해시)된 문자열을 저장하므로 충분한 길이를 확보합니다.
    password: str = Field(nullable=False)

    # 4. 실명 (선택사항이지만 강력 추천)
    # 가입할 때 이름을 받아두면 UI에 활용하기 좋습니다.
    full_name: Optional[str] = None

    # 5. 이메일 (선택사항)
    email: Optional[str] = None
