# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from pydantic import BaseModel, Field

from app.appsettings import AppConfiguration, get_app_config
from app.libs.storage_blob.helper import StorageBlobHelper
from app.libs.storage_queue.helper import StorageQueueHelper


class ContentProcessor(BaseModel):
    config: AppConfiguration = Field(default=None)
    blobHelper: StorageBlobHelper = Field(default=None)
    queueHelper: StorageQueueHelper = Field(default=None)

    def __init__(self):
        super().__init__()
        self.config = get_app_config()
        self.blobHelper = StorageBlobHelper(
            self.config.app_storage_blob_url, self.config.app_cps_processes
        )
        ingress_step = self._get_ingress_step()
        self.queueHelper = StorageQueueHelper(
            self.config.app_storage_queue_url,
            f"content-pipeline-{ingress_step}-queue",
        )

    def save_file_to_blob(self, process_id: str, file: bytes, file_name: str):
        self.blobHelper.upload_blob(file_name, file, process_id)

    def enqueue_message(self, message_object: BaseModel):
        self.queueHelper.drop_message(message_object)

    def _get_ingress_step(self) -> str:
        if self.config.app_pipeline_mode == "cliniq_singlepass":
            return "map"
        if self.config.app_process_steps and len(self.config.app_process_steps) > 0:
            return self.config.app_process_steps[0]
        return "extract"

    class Config:
        arbitrary_types_allowed = True


coontent_processor: ContentProcessor | None = None


def get_content_processor() -> ContentProcessor:
    global coontent_processor
    if coontent_processor is None:
        coontent_processor = ContentProcessor()
    return coontent_processor
