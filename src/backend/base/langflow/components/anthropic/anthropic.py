from typing import Any, cast

import requests
from loguru import logger
from pydantic import ValidationError

from langflow.base.models.anthropic_constants import (
    ANTHROPIC_MODELS,
    DEFAULT_ANTHROPIC_API_URL,
    TOOL_CALLING_SUPPORTED_ANTHROPIC_MODELS,
    TOOL_CALLING_UNSUPPORTED_ANTHROPIC_MODELS,
)
from langflow.base.models.model import LCModelComponent
from langflow.field_typing import LanguageModel
from langflow.field_typing.range_spec import RangeSpec
from langflow.io import BoolInput, DropdownInput, IntInput, MessageTextInput, SecretStrInput, SliderInput
from langflow.schema.dotdict import dotdict


class AnthropicModelComponent(LCModelComponent):
    display_name = "Anthropic"
    description = "Generate text using Anthropic's Messages API and models."
    icon = "Anthropic"
    name = "AnthropicModel"

    inputs = [
        *LCModelComponent._base_inputs,
        IntInput(
            name="max_tokens",
            display_name="Max Tokens",
            advanced=True,
            value=4096,
            info="The maximum number of tokens to generate. Set to 0 for unlimited tokens.",
        ),
        DropdownInput(
            name="model_name",
            display_name="Model Name",
            options=ANTHROPIC_MODELS,
            refresh_button=True,
            value=ANTHROPIC_MODELS[0],
            combobox=True,
        ),
        SecretStrInput(
            name="api_key",
            display_name="Anthropic API Key",
            info="Your Anthropic API key.",
            value=None,
            required=True,
            real_time_refresh=True,
        ),
        SliderInput(
            name="temperature",
            display_name="Temperature",
            value=0.1,
            info="Run inference with this temperature. Must by in the closed interval [0.0, 1.0].",
            range_spec=RangeSpec(min=0, max=1, step=0.01),
            advanced=True,
        ),
        MessageTextInput(
            name="base_url",
            display_name="Anthropic API URL",
            info="Endpoint of the Anthropic API. Defaults to 'https://api.anthropic.com' if not specified.",
            value=DEFAULT_ANTHROPIC_API_URL,
            real_time_refresh=True,
            advanced=True,
        ),
        BoolInput(
            name="tool_model_enabled",
            display_name="Enable Tool Models",
            info=(
                "Select if you want to use models that can work with tools. If yes, only those models will be shown."
            ),
            advanced=False,
            value=False,
            real_time_refresh=True,
        ),
    ]

    def build_model(self) -> LanguageModel:  # type: ignore[type-var]
        try:
            from langchain_anthropic.chat_models import ChatAnthropic
        except ImportError as e:
            msg = "langchain_anthropic is not installed. Please install it with `pip install langchain_anthropic`."
            raise ImportError(msg) from e
        try:
            max_tokens_value = getattr(self, "max_tokens", "")
            max_tokens_value = 4096 if max_tokens_value == "" else int(max_tokens_value)
            output = ChatAnthropic(
                model=self.model_name,
                anthropic_api_key=self.api_key,
                max_tokens=max_tokens_value,
                temperature=self.temperature,
                anthropic_api_url=self.base_url or DEFAULT_ANTHROPIC_API_URL,
                streaming=self.stream,
            )
        except ValidationError:
            raise
        except Exception as e:
            msg = "Could not connect to Anthropic API."
            raise ValueError(msg) from e

        return output

    def get_models(self, tool_model_enabled: bool | None = None) -> list[str]:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=self.api_key)
            models = client.models.list(limit=20).data
            model_ids = ANTHROPIC_MODELS + [model.id for model in models]
        except (ImportError, ValueError, requests.exceptions.RequestException) as e:
            logger.exception(f"Error getting model names: {e}")
            model_ids = ANTHROPIC_MODELS

        if tool_model_enabled:
            try:
                from langchain_anthropic.chat_models import ChatAnthropic
            except ImportError as e:
                msg = "langchain_anthropic is not installed. Please install it with `pip install langchain_anthropic`."
                raise ImportError(msg) from e

            # Create a new list instead of modifying while iterating
            filtered_models = []
            for model in model_ids:
                if model in TOOL_CALLING_SUPPORTED_ANTHROPIC_MODELS:
                    filtered_models.append(model)
                    continue

                model_with_tool = ChatAnthropic(
                    model=model,  # Use the current model being checked
                    anthropic_api_key=self.api_key,
                    anthropic_api_url=cast(str, self.base_url) or DEFAULT_ANTHROPIC_API_URL,
                )

                if (
                    not self.supports_tool_calling(model_with_tool)
                    or model in TOOL_CALLING_UNSUPPORTED_ANTHROPIC_MODELS
                ):
                    continue

                filtered_models.append(model)

            return filtered_models

        return model_ids

    def _get_exception_message(self, exception: Exception) -> str | None:
        """Get a message from an Anthropic exception.

        Args:
            exception (Exception): The exception to get the message from.

        Returns:
            str: The message from the exception.
        """
        try:
            from anthropic import BadRequestError
        except ImportError:
            return None
        if isinstance(exception, BadRequestError):
            message = exception.body.get("error", {}).get("message")
            if message:
                return message
        return None

    def update_build_config(self, build_config: dotdict, field_value: Any, field_name: str | None = None):
        if "base_url" in build_config and build_config["base_url"]["value"] is None:
            build_config["base_url"]["value"] = DEFAULT_ANTHROPIC_API_URL
            self.base_url = DEFAULT_ANTHROPIC_API_URL
        if field_name in {"base_url", "model_name", "tool_model_enabled", "api_key"} and field_value:
            try:
                if len(self.api_key) == 0:
                    ids = ANTHROPIC_MODELS
                else:
                    try:
                        ids = self.get_models(tool_model_enabled=self.tool_model_enabled)
                    except (ImportError, ValueError, requests.exceptions.RequestException) as e:
                        logger.exception(f"Error getting model names: {e}")
                        ids = ANTHROPIC_MODELS
                build_config["model_name"]["options"] = ids
                build_config["model_name"]["value"] = ids[0]
                build_config["model_name"]["combobox"] = True
            except Exception as e:
                msg = f"Error getting model names: {e}"
                raise ValueError(msg) from e
        return build_config
