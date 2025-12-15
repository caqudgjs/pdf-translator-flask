# -*- coding: utf-8 -*-
"""
Translator Factory - 모델 이름에 따라 적절한 번역기 인스턴스를 생성
"""

from src.base_translator import BaseTranslator
from src.pdf_translator_requests import OpenAITranslator
from src.claude_translator import ClaudeTranslator


class TranslatorFactory:
    """번역기 인스턴스를 생성하는 Factory 클래스"""

    # 지원되는 모델 목록
    OPENAI_MODELS = ['gpt-4o-mini', 'gpt-4o', 'gpt-4', 'gpt-3.5-turbo']
    CLAUDE_MODELS = [
        'claude-3-5-sonnet-20241022',
        'claude-3-5-haiku-20241022',
        'claude-opus-4-5-20251101'
    ]

    @classmethod
    def create_translator(cls, api_key: str, model_name: str) -> BaseTranslator:
        """
        모델 이름에 따라 적절한 번역기 인스턴스를 생성합니다.

        Args:
            api_key: API 키 (OpenAI 또는 Claude)
            model_name: 모델 이름

        Returns:
            BaseTranslator: OpenAITranslator 또는 ClaudeTranslator 인스턴스

        Raises:
            ValueError: 지원하지 않는 모델 이름인 경우
        """
        # OpenAI 모델 감지
        if model_name.startswith('gpt-') or model_name.startswith('o1-'):
            return OpenAITranslator(api_key=api_key, model_name=model_name)

        # Claude 모델 감지
        elif model_name.startswith('claude-'):
            return ClaudeTranslator(api_key=api_key, model_name=model_name)

        # 지원하지 않는 모델
        else:
            supported_models = {
                'openai': cls.OPENAI_MODELS,
                'claude': cls.CLAUDE_MODELS
            }
            raise ValueError(
                f"지원하지 않는 모델 '{model_name}'입니다. "
                f"OpenAI 모델(gpt-*) 또는 Claude 모델(claude-*)을 선택해주세요. "
                f"지원 모델: OpenAI={supported_models['openai']}, Claude={supported_models['claude']}"
            )

    @classmethod
    def get_supported_models(cls) -> dict:
        """
        지원되는 모델 목록을 반환합니다.

        Returns:
            dict: {'openai': [...], 'claude': [...]}
        """
        return {
            'openai': cls.OPENAI_MODELS,
            'claude': cls.CLAUDE_MODELS
        }
