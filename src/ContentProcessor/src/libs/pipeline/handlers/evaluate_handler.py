# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import json
import logging

from libs.application.application_context import AppContext
from libs.azure_helper.model.content_understanding import AnalyzedResult
from libs.pipeline.entities.pipeline_file import ArtifactType, PipelineLogEntry
from libs.pipeline.entities.pipeline_message_context import MessageContext
from libs.pipeline.entities.pipeline_step_result import StepResult
from libs.pipeline.handlers.logics.evaluate_handler.comparison import (
    get_extraction_comparison_data,
)
from libs.pipeline.handlers.logics.evaluate_handler.confidence import (
    merge_confidence_values,
)
from libs.pipeline.handlers.logics.evaluate_handler.content_understanding_confidence_evaluator import (
    evaluate_confidence as content_understanding_confidence,
)
from libs.pipeline.handlers.logics.evaluate_handler.model import DataExtractionResult
from libs.pipeline.handlers.logics.evaluate_handler.openai_confidence_evaluator import (
    evaluate_confidence as gpt_confidence,
)
from libs.pipeline.queue_handler_base import HandlerBase


class EvaluateHandler(HandlerBase):
    def __init__(self, appContext: AppContext, step_name: str, **data):
        super().__init__(appContext, step_name, **data)

    async def execute(self, context: MessageContext) -> StepResult:
        print(context.data_pipeline.get_previous_step_result(self.handler_name))

        # Get the result from Map step handler - Azure AI Foundry
        output_file_json_string_from_map = self.download_output_file_to_json_string(
            processed_by="map",
            artifact_type=ArtifactType.SchemaMappedData,
        )

        # Deserialize the result from Azure AI Foundry SDK response
        gpt_result = json.loads(output_file_json_string_from_map)

        # Mapped Result from Azure AI Foundry
        parsed_message_from_gpt = gpt_result["choices"][0]["message"]["parsed"]

        # Convert the parsed message to a dictionary
        gpt_evaluate_confidence_dict = parsed_message_from_gpt

        cliniq_mode = (
            self.application_context.configuration.app_pipeline_mode
            == "cliniq_singlepass"
        )

        # Evaluate Confidence Score - GPT
        gpt_confidence_score = gpt_confidence(
            gpt_evaluate_confidence_dict, gpt_result["choices"][0]
        )

        validation_issues = gpt_result.get("validation_issues", [])
        section_completeness = gpt_result.get("section_completeness", {})
        schema_version = gpt_result.get("schema_version", "v1")

        if cliniq_mode:
            deterministic_confidence = self._deterministic_confidence(
                gpt_evaluate_confidence_dict
            )
            merged_confidence_score = merge_confidence_values(
                deterministic_confidence, gpt_confidence_score
            )
        else:
            # Legacy mode still merges with Content Understanding confidence.
            output_file_json_string_from_extract = self.download_output_file_to_json_string(
                processed_by="extract",
                artifact_type=ArtifactType.ExtractedContent,
            )
            content_understanding_result = AnalyzedResult(
                **json.loads(output_file_json_string_from_extract)
            )
            content_understanding_confidence_score = content_understanding_confidence(
                gpt_evaluate_confidence_dict,
                content_understanding_result.result.contents[0],
            )
            merged_confidence_score = merge_confidence_values(
                content_understanding_confidence_score, gpt_confidence_score
            )

        # Flatten extracted data and confidence score
        result_data = get_extraction_comparison_data(
            actual=gpt_evaluate_confidence_dict,
            confidence=merged_confidence_score,
            threads_hold=0.8,  # TODO: Get this from config
        )

        # Put all results in a single object
        all_results = DataExtractionResult(
            extracted_result=gpt_evaluate_confidence_dict,
            confidence=merged_confidence_score,
            comparison_result=result_data,
            prompt_tokens=gpt_result["usage"]["prompt_tokens"],
            completion_tokens=gpt_result["usage"]["completion_tokens"],
            execution_time=0,
            field_confidence=merged_confidence_score,
            validation_issues=validation_issues,
            section_completeness=section_completeness,
            schema_version=schema_version,
        )
        logging.info(
            "evaluate_handler completed",
            extra={
                "process_id": context.data_pipeline.pipeline_status.process_id,
                "pipeline_mode": self.application_context.configuration.app_pipeline_mode,
                "validation_issue_count": len(validation_issues),
            },
        )

        # Save Result as a file
        result_file = context.data_pipeline.add_file(
            file_name="evaluate_output.json",
            artifact_type=ArtifactType.ScoreMergedData,
        )
        result_file.log_entries.append(
            PipelineLogEntry(
                **{
                    "source": self.handler_name,
                    "message": "Evaluation Result has been added",
                }
            )
        )
        result_file.upload_json_text(
            account_url=self.application_context.configuration.app_storage_blob_url,
            container_name=self.application_context.configuration.app_cps_processes,
            text=all_results.model_dump_json(),
        )

        return StepResult(
            process_id=context.data_pipeline.pipeline_status.process_id,
            step_name=self.handler_name,
            result={"result": "success", "file_name": result_file.name},
        )

    def _deterministic_confidence(self, payload: dict):
        def build(value):
            if isinstance(value, dict):
                return {k: build(v) for k, v in value.items()}
            if isinstance(value, list):
                return [build(item) for item in value]
            is_present = value not in (None, "", "ND")
            return {
                "confidence": 1.0 if is_present else 0.0,
                "value": value,
            }

        return build(payload)
