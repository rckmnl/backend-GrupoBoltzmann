import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    PROJECT_NAME: str = "Grupo Boltzman API"
    # Esta clave debe ser secreta. En producción usa una cadena aleatoria larga.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "SUPER_SECRET_BOLTZMAN_2025_QUITE_LONG_KEY")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # El token durará 7 días

settings = Settings()