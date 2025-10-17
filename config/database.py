import os
from dotenv import load_dotenv

load_dotenv()

class DatabaseConfig:
    """Database configuration class"""
    
    # Support multiple database types
    DB_TYPE = os.getenv('DB_TYPE', 'mysql')  # mysql, postgresql, sqlite, sqlserver
    
    # MySQL configuration
    MYSQL_CONFIG = {
        'host': os.getenv('MYSQL_HOST', 'localhost'),
        'port': int(os.getenv('MYSQL_PORT', 3306)),
        'user': os.getenv('MYSQL_USER', 'root'),
        'password': os.getenv('MYSQL_PASSWORD', ''),
        'database': os.getenv('MYSQL_DATABASE', 'hospital_db'),
        'charset': 'utf8mb4'
    }
    
    # PostgreSQL configuration
    POSTGRESQL_CONFIG = {
        'host': os.getenv('POSTGRES_HOST', 'localhost'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'user': os.getenv('POSTGRES_USER', 'postgres'),
        'password': os.getenv('POSTGRES_PASSWORD', ''),
        'database': os.getenv('POSTGRES_DATABASE', 'hospital_db')
    }
    
    # SQLite configuration
    SQLITE_PATH = os.getenv('SQLITE_PATH', './data/hospital.db')
    
    # LLM configuration
    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'openai')  # openai, claude, ollama, etc
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')
    MODEL_NAME = os.getenv('MODEL_NAME', 'gpt-4')
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    
    # Export configuration
    EXPORT_DIR = os.getenv('EXPORT_DIR', './data/exports/')
    
    @classmethod
    def get_connection_string(cls):
        """Get database connection string"""
        if cls.DB_TYPE == 'mysql':
            config = cls.MYSQL_CONFIG
            return f"mysql+pymysql://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}?charset={config['charset']}"
        
        elif cls.DB_TYPE == 'postgresql':
            config = cls.POSTGRESQL_CONFIG
            return f"postgresql+psycopg2://{config['user']}:{config['password']}@{config['host']}:{config['port']}/{config['database']}"
        
        elif cls.DB_TYPE == 'sqlite':
            return f"sqlite:///{cls.SQLITE_PATH}"
        
        else:
            raise ValueError(f"Unsupported database type: {cls.DB_TYPE}")