"""
Centralized Configuration Management

This module provides a single source of truth for all server configuration.
Uses Pydantic BaseSettings for type validation, environment variable binding,
and computed properties.

Usage:
    from app.core.settings import settings

    # Access settings
    url = settings.database.elasticsearch_url
    top_k = settings.retriever.top_k

    # Check Ollama mode
    if settings.ollama.use_cloud:
        # Use cloud client

    # Get collection config
    collection = settings.get_collection("btp")
"""

import json
import os
import warnings
import configparser
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

# Base directory is the server folder (parent of app/core)
BASE_DIR = Path(__file__).parent.parent.parent

# Load .env file from server directory
ENV_FILE = BASE_DIR / ".env"


# =============================================================================
# NESTED SETTINGS MODELS
# =============================================================================

class DatabaseSettings(BaseModel):
    """Database connection settings (Elasticsearch, Qdrant)"""
    elasticsearch_url: str = Field(default="http://localhost:9200")
    qdrant_url: str = Field(default="http://localhost:6333")


class OllamaSettings(BaseModel):
    """Ollama/LLM configuration"""
    base_url: str = Field(default="http://localhost:11434")
    api_key: Optional[str] = Field(default=None)
    cloud_host: str = Field(default="https://ollama.com")

    @computed_field
    @property
    def use_cloud(self) -> bool:
        """True if OLLAMA_API_KEY is set, meaning we should use cloud Ollama"""
        return self.api_key is not None and len(self.api_key) > 0


class FileServerSettings(BaseModel):
    """File server configuration for PDF/document serving"""
    base_url: str = Field(default="http://localhost:7700")
    public_url: Optional[str] = Field(default=None)

    @computed_field
    @property
    def public_base_url(self) -> str:
        """Public URL for browser-accessible links (defaults to base_url)"""
        return self.public_url or self.base_url


class RetrieverSettings(BaseModel):
    """Hybrid retriever configuration (BM25 + Vector)"""
    top_k: int = Field(default=15, description="Number of results from each retrieval method")
    final_k: int = Field(default=5, description="Final number of results after fusion")
    bm25_weight: float = Field(default=0.5, description="Weight for BM25 in RRF fusion")
    vector_weight: float = Field(default=0.5, description="Weight for vector search in RRF fusion")
    rrf_k: int = Field(default=60, description="RRF smoothing constant (Cormack et al., 2009)")


class QCMSettings(BaseModel):
    """QCM (Multiple Choice Question) generation settings"""
    retriever_top_k: int = Field(default=15, description="Chunks to retrieve for question generation")
    answer_top_k: int = Field(default=5, description="Chunks to retrieve per answer")
    max_questions: int = Field(default=20, description="Maximum questions per QCM")


class CourseSettings(BaseModel):
    """Course generation settings"""
    retriever_top_k: int = Field(default=5, description="Sources per query in retrieval")
    enhancer_iterations: int = Field(default=3, description="Max iterations for knowledge enhancement")
    enhancer_top_k: int = Field(default=5, description="Sources per gap-filling query")
    output_base_dir: str = Field(default="./course_outputs", description="Directory for course outputs")
    enable_logging: bool = Field(default=True, description="Enable course generation logging")
    heartbeat_interval: int = Field(default=10, description="Seconds between heartbeats")


class StreamingSettings(BaseModel):
    """Streaming/async configuration"""
    queue_timeout: float = Field(default=0.1, description="Queue poll timeout in seconds")
    sleep_interval: float = Field(default=0.01, description="Event loop sleep interval in seconds")
    heartbeat_interval: int = Field(default=10, description="Heartbeat interval in seconds")


class ServerSettings(BaseModel):
    """Server configuration"""
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8080)
    base_url: Optional[str] = Field(default=None)
    log_level: str = Field(default="info")

    @computed_field
    @property
    def computed_base_url(self) -> str:
        """Server base URL (computed from host/port if not set)"""
        return self.base_url or f"http://localhost:{self.port}"


class CORSSettings(BaseModel):
    """CORS configuration"""
    allow_origins: str = Field(default="*")
    allow_credentials: bool = Field(default=True)
    allow_methods: str = Field(default="*")
    allow_headers: str = Field(default="*")

    @computed_field
    @property
    def origins_list(self) -> list:
        """Parse comma-separated origins into list"""
        return [o.strip() for o in self.allow_origins.split(",")]

    @computed_field
    @property
    def methods_list(self) -> list:
        """Parse comma-separated methods into list"""
        return [m.strip() for m in self.allow_methods.split(",")]

    @computed_field
    @property
    def headers_list(self) -> list:
        """Parse comma-separated headers into list"""
        return [h.strip() for h in self.allow_headers.split(",")]


class RAGSettings(BaseModel):
    """RAG model configuration"""
    model: str = Field(default="gpt-oss:20b")
    default_top_k: int = Field(default=30)
    chunk_size: int = Field(default=5)
    chunk_delay: float = Field(default=0.01)
    temperature: float = Field(default=0.7)


class PathSettings(BaseModel):
    """Path configuration"""
    spacy_model: str = Field(default="fr_core_news_sm")


class DownloadSettings(BaseModel):
    """Download configuration"""
    allowed_base_path: str = Field(default="course_outputs")


# =============================================================================
# MAIN SETTINGS CLASS
# =============================================================================

class Settings(BaseSettings):
    """
    Centralized settings with environment variable binding.

    All settings can be overridden via environment variables with the prefix
    matching the field name (e.g., ELASTICSEARCH_URL, OLLAMA_API_KEY).

    Nested settings are loaded from config.ini for backwards compatibility,
    then overridden by environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ==========================================================================
    # Environment variable bindings (flat for Pydantic compatibility)
    # ==========================================================================

    # Database
    elasticsearch_url: str = Field(default="http://localhost:9200", alias="ELASTICSEARCH_URL")
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_api_key: Optional[str] = Field(default=None, alias="OLLAMA_API_KEY")

    # File Server
    fileserver_base: str = Field(default="http://localhost:7700", alias="FILESERVER_BASE")
    fileserver_public_url: Optional[str] = Field(default=None, alias="FILESERVER_PUBLIC_URL")

    # Server
    server_base_url: Optional[str] = Field(default=None, alias="SERVER_BASE_URL")

    # Retriever
    retriever_top_k: int = Field(default=15, alias="RETRIEVER_TOP_K")
    bm25_weight: float = Field(default=0.5, alias="BM25_WEIGHT")
    vector_weight: float = Field(default=0.5, alias="VECTOR_WEIGHT")
    rrf_k: int = Field(default=60, alias="RRF_K")
    retriever_final_k: int = Field(default=5, alias="RETRIEVER_FINAL_K")

    # QCM
    qcm_retriever_top_k: int = Field(default=15, alias="QCM_RETRIEVER_TOP_K")
    qcm_answer_top_k: int = Field(default=5, alias="QCM_ANSWER_TOP_K")
    qcm_max_questions: int = Field(default=20, alias="QCM_MAX_QUESTIONS")

    # Course
    course_retriever_top_k: int = Field(default=5, alias="COURSE_RETRIEVER_TOP_K")
    course_enhancer_iterations: int = Field(default=3, alias="COURSE_ENHANCER_ITERATIONS")
    course_enhancer_top_k: int = Field(default=5, alias="COURSE_ENHANCER_TOP_K")

    # Streaming
    stream_queue_timeout: float = Field(default=0.1, alias="STREAM_QUEUE_TIMEOUT")
    stream_sleep_interval: float = Field(default=0.01, alias="STREAM_SLEEP_INTERVAL")
    heartbeat_interval: int = Field(default=10, alias="HEARTBEAT_INTERVAL")

    # Authentication
    auth_tokens: Optional[str] = Field(default=None, alias="AUTH_TOKENS")

    # ==========================================================================
    # Computed nested settings (for organized access)
    # ==========================================================================

    @computed_field
    @property
    def database(self) -> DatabaseSettings:
        """Database connection settings"""
        return DatabaseSettings(
            elasticsearch_url=self.elasticsearch_url,
            qdrant_url=self.qdrant_url,
        )

    @computed_field
    @property
    def ollama(self) -> OllamaSettings:
        """Ollama/LLM settings"""
        return OllamaSettings(
            base_url=self.ollama_base_url,
            api_key=self.ollama_api_key,
        )

    @computed_field
    @property
    def fileserver(self) -> FileServerSettings:
        """File server settings"""
        return FileServerSettings(
            base_url=self.fileserver_base,
            public_url=self.fileserver_public_url,
        )

    @computed_field
    @property
    def retriever(self) -> RetrieverSettings:
        """Retriever settings"""
        return RetrieverSettings(
            top_k=self.retriever_top_k,
            final_k=self.retriever_final_k,
            bm25_weight=self.bm25_weight,
            vector_weight=self.vector_weight,
            rrf_k=self.rrf_k,
        )

    @computed_field
    @property
    def qcm(self) -> QCMSettings:
        """QCM settings"""
        return QCMSettings(
            retriever_top_k=self.qcm_retriever_top_k,
            answer_top_k=self.qcm_answer_top_k,
            max_questions=self.qcm_max_questions,
        )

    @computed_field
    @property
    def course(self) -> CourseSettings:
        """Course generation settings"""
        return CourseSettings(
            retriever_top_k=self.course_retriever_top_k,
            enhancer_iterations=self.course_enhancer_iterations,
            enhancer_top_k=self.course_enhancer_top_k,
        )

    @computed_field
    @property
    def streaming(self) -> StreamingSettings:
        """Streaming settings"""
        return StreamingSettings(
            queue_timeout=self.stream_queue_timeout,
            sleep_interval=self.stream_sleep_interval,
            heartbeat_interval=self.heartbeat_interval,
        )

    # ==========================================================================
    # Backwards compatibility: Load from config.ini
    # ==========================================================================

    _config_ini: Optional[configparser.ConfigParser] = None
    _collections: Optional[Dict[str, Dict[str, str]]] = None

    def __init__(self, **data):
        super().__init__(**data)
        self._load_config_ini()
        self._load_collections()
        self._warn_if_no_auth()

    def _load_config_ini(self):
        """Load config.ini for backwards compatibility"""
        config_path = BASE_DIR / "config.ini"
        if config_path.exists():
            self._config_ini = configparser.ConfigParser()
            self._config_ini.read(config_path)

    def _load_collections(self):
        """Load collections from collections.json"""
        collections_path = BASE_DIR / "collections.json"
        if collections_path.exists():
            with open(collections_path, "r") as f:
                self._collections = json.load(f)
            print(f"[settings] Loaded {len(self._collections)} collection(s): {list(self._collections.keys())}")
        else:
            self._collections = {}
            print("[settings] Warning: collections.json not found")

    def _warn_if_no_auth(self):
        """Warn if AUTH_TOKENS is not set"""
        if not self.auth_tokens:
            warnings.warn(
                "AUTH_TOKENS environment variable not set! "
                "Using insecure development token. "
                "Set AUTH_TOKENS in production.",
                RuntimeWarning
            )

    # ==========================================================================
    # Public API
    # ==========================================================================

    @property
    def COLLECTIONS(self) -> Dict[str, Dict[str, str]]:
        """Collection registry (backwards compatibility)"""
        return self._collections or {}

    def get_collection(self, name: str) -> Dict[str, str]:
        """Return the qdrant_collection/es_index pair for a collection name."""
        if not self._collections or name not in self._collections:
            available = list(self._collections.keys()) if self._collections else []
            raise ValueError(f"Unknown collection '{name}'. Available: {available}")
        return self._collections[name]

    def get_auth_tokens(self) -> Dict[str, Dict[str, str]]:
        """
        Parse AUTH_TOKENS from environment variable.
        Format: token1:user_id1:name1,token2:user_id2:name2
        """
        tokens_str = self.auth_tokens

        if not tokens_str:
            # Use insecure default for development
            tokens_str = "dev-token-123:user_1:Developer"

        tokens = {}
        for token_entry in tokens_str.split(","):
            parts = token_entry.strip().split(":")
            if len(parts) == 3:
                token, user_id, name = parts
                tokens[token] = {"user_id": user_id, "name": name}

        return tokens

    # ==========================================================================
    # Backwards compatibility aliases (from old Config class)
    # ==========================================================================

    @property
    def ELASTICSEARCH_URL(self) -> str:
        return self.elasticsearch_url

    @property
    def QDRANT_URL(self) -> str:
        return self.qdrant_url

    @property
    def OLLAMA_BASE_URL(self) -> str:
        return self.ollama_base_url

    @property
    def SERVER_BASE_URL(self) -> str:
        return self.server_base_url or f"http://localhost:8080"

    @property
    def BM25_WEIGHT(self) -> float:
        return self.bm25_weight

    @property
    def VECTOR_WEIGHT(self) -> float:
        return self.vector_weight

    @property
    def RETRIEVER_TOP_K(self) -> int:
        return self.retriever_top_k

    @property
    def RETRIEVER_FINAL_K(self) -> int:
        return self.retriever_final_k

    @property
    def QCM_RETRIEVER_TOP_K(self) -> int:
        return self.qcm_retriever_top_k

    @property
    def QCM_ANSWER_TOP_K(self) -> int:
        return self.qcm_answer_top_k

    @property
    def COURSE_RETRIEVER_TOP_K(self) -> int:
        return self.course_retriever_top_k

    @property
    def COURSE_ENHANCER_ITERATIONS(self) -> int:
        return self.course_enhancer_iterations

    @property
    def COURSE_ENHANCER_TOP_K(self) -> int:
        return self.course_enhancer_top_k

    # Config.ini based settings (for full backwards compatibility)
    @property
    def SERVER_HOST(self) -> str:
        if self._config_ini:
            return self._config_ini.get("server", "host", fallback="0.0.0.0")
        return "0.0.0.0"

    @property
    def SERVER_PORT(self) -> int:
        if self._config_ini:
            return self._config_ini.getint("server", "port", fallback=8080)
        return 8080

    @property
    def LOG_LEVEL(self) -> str:
        if self._config_ini:
            return self._config_ini.get("server", "log_level", fallback="info")
        return "info"

    @property
    def CORS_ALLOW_ORIGINS(self) -> list:
        if self._config_ini:
            return self._config_ini.get("cors", "allow_origins", fallback="*").split(",")
        return ["*"]

    @property
    def CORS_ALLOW_CREDENTIALS(self) -> bool:
        if self._config_ini:
            return self._config_ini.getboolean("cors", "allow_credentials", fallback=True)
        return True

    @property
    def CORS_ALLOW_METHODS(self) -> list:
        if self._config_ini:
            return self._config_ini.get("cors", "allow_methods", fallback="*").split(",")
        return ["*"]

    @property
    def CORS_ALLOW_HEADERS(self) -> list:
        if self._config_ini:
            return self._config_ini.get("cors", "allow_headers", fallback="*").split(",")
        return ["*"]

    @property
    def RAG_MODEL(self) -> str:
        if self._config_ini:
            return self._config_ini.get("rag", "model", fallback="gpt-oss:20b")
        return "gpt-oss:20b"

    @property
    def RAG_DEFAULT_TOP_K(self) -> int:
        if self._config_ini:
            return self._config_ini.getint("rag", "default_top_k", fallback=30)
        return 30

    @property
    def RAG_CHUNK_SIZE(self) -> int:
        if self._config_ini:
            return self._config_ini.getint("rag", "chunk_size", fallback=5)
        return 5

    @property
    def RAG_CHUNK_DELAY(self) -> float:
        if self._config_ini:
            return self._config_ini.getfloat("rag", "chunk_delay", fallback=0.01)
        return 0.01

    @property
    def RAG_TEMPERATURE(self) -> float:
        if self._config_ini:
            return self._config_ini.getfloat("rag", "temperature", fallback=0.7)
        return 0.7

    @property
    def EMBED_MODEL(self) -> str:
        if self._config_ini:
            return self._config_ini.get("hybrid_retriever", "embed_model", fallback="embeddinggemma")
        return "embeddinggemma"

    @property
    def SPACY_MODEL(self) -> str:
        if self._config_ini:
            return self._config_ini.get("paths", "spacy_model", fallback="fr_core_news_sm")
        return "fr_core_news_sm"

    @property
    def DOWNLOAD_ALLOWED_BASE_PATH(self) -> str:
        if self._config_ini:
            return self._config_ini.get("download", "allowed_base_path", fallback="course_outputs")
        return "course_outputs"

    @property
    def COURSE_OUTPUT_BASE_DIR(self) -> str:
        if self._config_ini:
            return self._config_ini.get("course_generation", "output_base_dir", fallback="./course_outputs")
        return "./course_outputs"

    @property
    def COURSE_ENABLE_LOGGING(self) -> bool:
        if self._config_ini:
            return self._config_ini.getboolean("course_generation", "enable_logging", fallback=True)
        return True

    @property
    def COURSE_HEARTBEAT_INTERVAL(self) -> int:
        if self._config_ini:
            return self._config_ini.getint("course_generation", "heartbeat_interval", fallback=10)
        return 10


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

settings = Settings()
