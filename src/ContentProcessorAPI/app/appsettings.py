# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import logging
import os

from dotenv import load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import NoDecode
from typing_extensions import Annotated

from app.libs.app_configuration.helper import AppConfigurationHelper


class ModelBaseSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)


class EnvConfiguration(ModelBaseSettings):
    app_config_endpoint: str = ""


class AppConfiguration(ModelBaseSettings):
    app_storage_blob_url: str = ""
    app_storage_queue_url: str = ""
    app_cosmos_connstr: str = ""
    app_cosmos_database: str = "ContentProcess"
    app_cosmos_container_schema: str = "Schemas"
    app_cosmos_container_process: str = "Processes"
    app_cps_configuration: str = "cps-configuration"
    app_cps_processes: str = "cps-processes"
    app_message_queue_extract: str = "content-pipeline-extract-queue"
    app_cps_max_filesize_mb: int = 20
    app_logging_level: str = "INFO"
    azure_package_logging_level: str = "WARNING"
    azure_logging_packages: str = "azure"
    app_pipeline_mode: str = "legacy"
    app_process_steps: Annotated[list[str], NoDecode] = ["extract", "map", "evaluate", "save"]

    @field_validator("app_process_steps", mode="before")
    @classmethod
    def split_processes(cls, v: str) -> list[str]:
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        return v


# Read .env file
# Get Current Path + .env file
env_file_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_file_path)

def _is_local_test_mode() -> bool:
    val = os.getenv("APP_LOCAL_TEST_MODE", "").strip().lower()
    return val in {"1", "true", "yes"} or "PYTEST_CURRENT_TEST" in os.environ


# Get App Configuration
env_config = EnvConfiguration()
if env_config.app_config_endpoint and not _is_local_test_mode():
    app_helper = AppConfigurationHelper(env_config.app_config_endpoint)
    app_helper.read_and_set_environmental_variables()

app_config = AppConfiguration()

# Configure logging
# Basic application logging (default: INFO level)
AZURE_BASIC_LOGGING_LEVEL = app_config.app_logging_level.upper()
# Azure package logging (default: WARNING level to suppress INFO)
AZURE_PACKAGE_LOGGING_LEVEL = app_config.azure_package_logging_level.upper()
AZURE_LOGGING_PACKAGES = (
    app_config.azure_logging_packages.split(",") if app_config.azure_logging_packages else []
)

# Basic config: logging.basicConfig with formatted output
logging.basicConfig(
    level=getattr(logging, AZURE_BASIC_LOGGING_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Package config: Azure loggers set to WARNING to suppress INFO
for logger_name in AZURE_LOGGING_PACKAGES:
    logging.getLogger(logger_name).setLevel(
        getattr(logging, AZURE_PACKAGE_LOGGING_LEVEL, logging.WARNING)
    )


# Dependency Function
def get_app_config() -> AppConfiguration:
    return app_config
