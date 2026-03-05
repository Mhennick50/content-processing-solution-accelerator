# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

import base64
import io
import json
import logging
import re

from pdf2image import convert_from_bytes

from libs.application.application_context import AppContext
from libs.azure_helper.azure_openai import get_foundry_client
from libs.azure_helper.model.content_understanding import AnalyzedResult
from libs.pipeline.entities.mime_types import MimeTypes
from libs.pipeline.entities.pipeline_file import ArtifactType, PipelineLogEntry
from libs.pipeline.entities.pipeline_message_context import MessageContext
from libs.pipeline.entities.pipeline_step_result import StepResult
from libs.pipeline.entities.schema import Schema
from libs.pipeline.queue_handler_base import HandlerBase
from libs.utils.remote_module_loader import load_schema_from_blob


class MapHandler(HandlerBase):
    def __init__(self, appContext: AppContext, step_name: str, **data):
        super().__init__(appContext, step_name, **data)

    async def execute(self, context: MessageContext) -> StepResult:
        print(context.data_pipeline.get_previous_step_result(self.handler_name))

        cliniq_mode = (
            self.application_context.configuration.app_pipeline_mode
            == "cliniq_singlepass"
        )
        markdown_string = ""
        if not cliniq_mode:
            # Legacy mode consumes markdown produced by extract step.
            output_file_json_string = self.download_output_file_to_json_string(
                processed_by="extract",
                artifact_type=ArtifactType.ExtractedContent,
            )
            previous_result = AnalyzedResult(**json.loads(output_file_json_string))
            markdown_string = previous_result.result.contents[0].markdown

        # Prepare the prompt
        user_content = self._prepare_prompt(markdown_string, cliniq_mode)

        # Check file type : PDF
        if context.data_pipeline.get_source_files()[0].mime_type == MimeTypes.Pdf:
            # Convert PDF to multiple images
            pdf_bytes = context.data_pipeline.get_source_files()[0].download_stream(
                self.application_context.configuration.app_storage_blob_url,
                self.application_context.configuration.app_cps_processes,
            )

            pdf_stream = io.BytesIO(pdf_bytes)
            # Set the position to the beginning of the stream
            for image in convert_from_bytes(pdf_stream.read()):
                byteIO = io.BytesIO()
                image.save(byteIO, format="PNG")
                user_content.append(
                    self._convert_image_bytes_to_prompt("image/png", byteIO.getvalue())
                )
        # Check file type : Image - JPEG, PNG
        elif context.data_pipeline.get_source_files()[0].mime_type in [
            MimeTypes.ImageJpeg,
            MimeTypes.ImagePng,
        ]:
            # Extract Images
            user_content.append(
                self._convert_image_bytes_to_prompt(
                    context.data_pipeline.get_source_files()[0].mime_type,
                    context.data_pipeline.get_source_files()[0].download_stream(
                        self.application_context.configuration.app_storage_blob_url,
                        self.application_context.configuration.app_cps_processes,
                    ),
                )
            )

        # Check Schema Information. In ClinIQ mode we can force a dedicated schema id.
        schema_id = context.data_pipeline.pipeline_status.schema_id
        if (
            cliniq_mode
            and self.application_context.configuration.app_cliniq_schema_id
        ):
            schema_id = self.application_context.configuration.app_cliniq_schema_id

        selected_schema = Schema.get_schema(
            connection_string=self.application_context.configuration.app_cosmos_connstr,
            database_name=self.application_context.configuration.app_cosmos_database,
            collection_name=self.application_context.configuration.app_cosmos_container_schema,
            schema_id=schema_id,
        )

        # Load the schema class for structured output
        schema_class = load_schema_from_blob(
            account_url=self.application_context.configuration.app_storage_blob_url,
            container_name=f"{self.application_context.configuration.app_cps_configuration}/Schemas/{schema_id}",
            blob_name=selected_schema.FileName,
            module_name=selected_schema.ClassName,
        )
        schema_json = self._get_schema_json(schema_class)

        # Invoke GPT with the prompt using Azure AI Inference SDK
        gpt_response = get_foundry_client(
            self.application_context.configuration.app_ai_project_endpoint
        ).complete(
            model=self.application_context.configuration.app_azure_openai_model,
            messages=[
                {
                    "role": "system",
                    "content": f"""You are an AI assistant that extracts structured clinical data from uploaded medical documents.
                    Prompt version: {self.application_context.configuration.app_prompt_version}.
                    Rules:
                    - Return ONLY JSON matching the schema exactly.
                    - Do not hallucinate values. If unknown, return null or "ND" according to field guidance.
                    - Preserve patient/encounter identifiers exactly as seen in source.
                    - Normalize dates to MM-DD-YYYY when possible.
                    - For partial documentation in clinical sections, keep section and set missing subfields to "ND".
                    - Never include explanatory text or markdown wrappers.
                    JSON schema:
                    {json.dumps(schema_json, indent=2)}""",
                },
                {"role": "user", "content": user_content},
            ],
            max_tokens=4096,
            temperature=0.1,
            top_p=0.1,
            model_extras={
                "logprobs": True,
                "top_logprobs": 5
            }
        )

        response_content = gpt_response.choices[0].message.content
        cleaned_content = response_content.replace("```json", "").replace("```", "").strip()
        runtime_validation_issues: list[str] = []
        try:
            parsed_response = self._parse_structured_response(schema_class, cleaned_content)
            parsed_payload = self._normalize_with_schema(schema_class, parsed_response)
            validation_issues = self._validate_with_schema(schema_class, parsed_payload)
        except Exception as ex:
            logging.warning("map_handler parsing fallback", extra={"error": str(ex)})
            parsed_payload = self._default_payload(schema_class)
            runtime_validation_issues.append(
                f"Model output was not valid JSON for schema parsing: {str(ex)}"
            )
            validation_issues = runtime_validation_issues + self._validate_with_schema(
                schema_class, parsed_payload
            )
        section_completeness = self._section_completeness(schema_class, parsed_payload)
        schema_version = parsed_payload.get("schema_version") or getattr(
            schema_class, "__schema_version__", "v1"
        )

        logging.info(
            "map_handler completed",
            extra={
                "process_id": context.data_pipeline.pipeline_status.process_id,
                "schema_id": schema_id,
                "pipeline_mode": self.application_context.configuration.app_pipeline_mode,
                "validation_issue_count": len(validation_issues),
            },
        )

        response_dict = {
            "choices": [{
                "message": {
                    "content": response_content,
                    "parsed": parsed_payload
                },
                "logprobs": {
                    "content": [{"token": t.token, "logprob": t.logprob} for t in gpt_response.choices[0].logprobs.content]
                } if hasattr(gpt_response.choices[0], 'logprobs') and gpt_response.choices[0].logprobs else None
            }],
            "usage": {
                "prompt_tokens": gpt_response.usage.prompt_tokens,
                "completion_tokens": gpt_response.usage.completion_tokens,
                "total_tokens": gpt_response.usage.total_tokens
            },
            "schema_version": schema_version,
            "validation_issues": validation_issues,
            "section_completeness": section_completeness,
            "pipeline_mode": self.application_context.configuration.app_pipeline_mode,
            "source_metadata": context.data_pipeline.pipeline_status.metadata or {},
        }

        # Save Result as a file
        result_file = context.data_pipeline.add_file(
            file_name="gpt_output.json",
            artifact_type=ArtifactType.SchemaMappedData,
        )
        result_file.log_entries.append(
            PipelineLogEntry(
                **{
                    "source": self.handler_name,
                    "message": "GPT Extraction Result has been added",
                }
            )
        )
        result_file.upload_json_text(
            account_url=self.application_context.configuration.app_storage_blob_url,
            container_name=self.application_context.configuration.app_cps_processes,
            text=json.dumps(response_dict),
        )

        return StepResult(
            process_id=context.data_pipeline.pipeline_status.process_id,
            step_name=self.handler_name,
            result={
                "result": "success",
                "file_name": result_file.name,
            },
        )

    def _convert_image_bytes_to_prompt(
        self, mime_string: str, image_stream: bytes
    ) -> list[dict]:
        """
        Add image to the prompt.
        """
        # Convert image to base64
        byteIO = io.BytesIO(image_stream)
        base64_encoded_data = base64.b64encode(byteIO.getvalue()).decode("utf-8")

        return {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_string};base64,{base64_encoded_data}"},
        }

    def _prepare_prompt(self, markdown_string: str, cliniq_mode: bool = False) -> list[dict]:
        """
        Prepare the prompt for the model.
        """
        user_content = []
        user_content.append(
            {
                "type": "text",
                "text": """Extract patient and encounter data from this document.
            - If a value is not present, provide null.
            - For partially documented clinical sections, use "ND" for missing sub-fields.
            - Do not invent identifiers.
            - Dates should be in the format MM-DD-YYYY.""",
            }
        )

        if markdown_string:
            user_content.append({"type": "text", "text": markdown_string})
        elif cliniq_mode:
            user_content.append(
                {
                    "type": "text",
                    "text": "Use the uploaded source document content directly to extract fields.",
                }
            )

        return user_content

    def _get_schema_json(self, schema_class) -> dict:
        if hasattr(schema_class, "model_json_schema"):
            return schema_class.model_json_schema()
        if hasattr(schema_class, "json_schema"):
            return schema_class.json_schema()
        raise ValueError("Schema must expose model_json_schema() or json_schema().")

    def _parse_structured_response(self, schema_class, cleaned_content: str) -> dict:
        cleaned_content = self._extract_json_payload(cleaned_content)
        if hasattr(schema_class, "model_validate_json"):
            return schema_class.model_validate_json(cleaned_content).model_dump()
        if hasattr(schema_class, "from_json"):
            parsed = schema_class.from_json(cleaned_content)
            if hasattr(parsed, "to_dict"):
                return parsed.to_dict()
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()
            if isinstance(parsed, dict):
                return parsed
        raise ValueError("Schema must expose model_validate_json() or from_json().")

    def _extract_json_payload(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            return stripped
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        return match.group(0) if match else stripped

    def _normalize_with_schema(self, schema_class, payload: dict) -> dict:
        if hasattr(schema_class, "normalize_payload"):
            return schema_class.normalize_payload(payload)
        return payload

    def _validate_with_schema(self, schema_class, payload: dict) -> list[str]:
        if hasattr(schema_class, "validate_payload"):
            return schema_class.validate_payload(payload)
        return []

    def _default_payload(self, schema_class) -> dict:
        if hasattr(schema_class, "example"):
            payload = schema_class.example()
            if isinstance(payload, dict):
                # Convert example output into a null-initialized shape.
                return self._nullify_payload(payload)
        if hasattr(schema_class, "model_json_schema"):
            schema = schema_class.model_json_schema()
            props = schema.get("properties", {})
            return {k: None for k in props.keys()}
        return {"schema_version": "v1"}

    def _nullify_payload(self, value):
        if isinstance(value, dict):
            return {k: self._nullify_payload(v) for k, v in value.items()}
        if isinstance(value, list):
            return []
        return None

    def _section_completeness(self, schema_class, payload: dict) -> dict:
        if hasattr(schema_class, "section_completeness"):
            return schema_class.section_completeness(payload)
        scored = {}
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                scored[key] = 1.0 if value else 0.0
        return scored
