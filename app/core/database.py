from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# Cấu trúc chuỗi kết nối: mysql+pymysql://<username>:<password>@<host>:<port>/<db_name>
SQLALCHEMY_DATABASE_URL = "mysql+pymysql://root:31102005@localhost:3306/shopping-research"

# Khởi tạo Engine
engine = create_engine(SQLALCHEMY_DATABASE_URL)

# Khởi tạo Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class cho tất cả các Entities
Base = declarative_base()