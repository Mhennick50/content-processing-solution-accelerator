from types import SimpleNamespace
from unittest.mock import patch

from app.routers.logics.contentprocessor import ContentProcessor


@patch("app.routers.logics.contentprocessor.StorageBlobHelper")
@patch("app.routers.logics.contentprocessor.StorageQueueHelper")
@patch("app.routers.logics.contentprocessor.get_app_config")
def test_content_processor_uses_map_queue_for_cliniq_mode(
    mock_get_app_config, mock_queue_helper, mock_blob_helper
):
    mock_get_app_config.return_value = SimpleNamespace(
        app_storage_blob_url="https://example.blob",
        app_cps_processes="cps-processes",
        app_storage_queue_url="https://example.queue",
        app_pipeline_mode="cliniq_singlepass",
        app_process_steps=["map", "evaluate", "save"],
    )

    ContentProcessor()

    mock_queue_helper.assert_called_once_with(
        "https://example.queue", "content-pipeline-map-queue"
    )


@patch("app.routers.logics.contentprocessor.StorageBlobHelper")
@patch("app.routers.logics.contentprocessor.StorageQueueHelper")
@patch("app.routers.logics.contentprocessor.get_app_config")
def test_content_processor_uses_first_step_queue_in_legacy_mode(
    mock_get_app_config, mock_queue_helper, mock_blob_helper
):
    mock_get_app_config.return_value = SimpleNamespace(
        app_storage_blob_url="https://example.blob",
        app_cps_processes="cps-processes",
        app_storage_queue_url="https://example.queue",
        app_pipeline_mode="legacy",
        app_process_steps=["extract", "map", "evaluate", "save"],
    )

    ContentProcessor()

    mock_queue_helper.assert_called_once_with(
        "https://example.queue", "content-pipeline-extract-queue"
    )
