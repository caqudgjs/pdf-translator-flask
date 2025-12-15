# -*- coding: utf-8 -*-
"""
Anthropic Claude API를 사용한 PDF 번역 모듈
"""

import re, json, time
from typing import List, Dict
import requests
from src.base_translator import BaseTranslator


class ClaudeTranslator(BaseTranslator):
    """Claude API를 사용하는 PDF 번역기"""

    def __init__(self, api_key: str, model_name: str = "claude-3-5-sonnet-20241022"):
        """
        Args:
            api_key: Claude API 키
            model_name: Claude 모델 이름 (예: claude-3-5-sonnet-20241022)
        """
        super().__init__(api_key, model_name)
        self.api_url = "https://api.anthropic.com/v1/messages"

        # 모델별 토큰 제한 설정
        if 'opus' in model_name.lower():
            self.max_output_tokens = 16384
        else:
            # Sonnet, Haiku
            self.max_output_tokens = 8192

    def validate_api_key(self) -> bool:
        """Claude API 키 유효성 검사 (최소 요청으로 테스트)"""
        self.log("Claude API 키 유효성 검사 시작")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # 최소 테스트 요청 (비용 최소화)
        data = {
            "model": self.model_name,
            "max_tokens": 10,
            "messages": [
                {"role": "user", "content": "Hi"}
            ]
        }

        try:
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=10
            )

            if response.status_code == 200:
                self.log("Claude API 키 유효성 검사 성공")
                return True
            else:
                self.log(f"Claude API 키 유효성 검사 실패: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            self.log(f"Claude API 키 유효성 검사 중 네트워크 오류: {e}")
            return False

    def call_claude_api(self, system_prompt: str, user_content: str) -> str:
        """Claude API 호출"""
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        # Claude API는 system 메시지를 별도 파라미터로 받음
        data = {
            "model": self.model_name,
            "max_tokens": self.max_output_tokens,  # Claude는 max_tokens 필수
            "temperature": 0.2,
            "system": system_prompt,  # messages 배열이 아닌 별도 파라미터
            "messages": [
                {"role": "user", "content": user_content}
            ]
        }

        response = requests.post(self.api_url, headers=headers, json=data, timeout=300)
        self.log(f"Claude API 응답 상태 코드: {response.status_code}")

        if response.status_code != 200:
            self.log(f"Claude API 오류 상세: {response.text}")

            # Claude 특정 에러 처리
            try:
                error_data = response.json()
                error_type = error_data.get('error', {}).get('type', '')

                if error_type == 'invalid_request_error':
                    raise RuntimeError(f"Claude API 요청 오류: 잘못된 요청 형식입니다.")
                elif error_type == 'authentication_error':
                    raise RuntimeError("Claude API 인증 실패: API 키를 확인해주세요.")
                elif error_type == 'permission_error':
                    raise RuntimeError("Claude API 권한 오류: 해당 모델에 대한 접근 권한이 없습니다.")
                elif error_type == 'rate_limit_error':
                    raise RuntimeError("Claude API 속도 제한 초과: 잠시 후 다시 시도해주세요.")
                else:
                    raise RuntimeError(f"Claude API 오류 ({response.status_code}): {response.text[:200]}...")
            except (json.JSONDecodeError, KeyError):
                raise RuntimeError(f"Claude API 오류 ({response.status_code}): {response.text[:200]}...")

        try:
            result = response.json()
        except json.JSONDecodeError:
            raise RuntimeError(f"Claude API 응답 JSON 파싱 실패: {response.text}")

        # Claude 응답 구조: result['content']는 리스트
        if 'content' not in result:
            raise RuntimeError(f"Claude API 응답에 content가 없습니다: {result}")

        if not isinstance(result['content'], list) or len(result['content']) == 0:
            raise RuntimeError(f"Claude API content가 비어있습니다: {result.get('content')}")

        if 'text' not in result['content'][0]:
            raise RuntimeError(f"Claude API content에 text 필드가 없습니다: {result['content'][0]}")

        return result['content'][0]['text'].strip()

    def translate_chunk(self, chunk: str, chunk_num: int, total_chunks: int) -> str:
        """개별 청크 번역"""
        self.log(f"청크 {chunk_num}/{total_chunks} 번역 중... (chars={len(chunk)})")

        glossary_guidance = ""
        if self.custom_glossary:
            found_terms = []
            for english_term, korean_formatted_term in self.custom_glossary.items():
                # Use regex to find whole words, case-insensitive
                if re.search(r'\b' + re.escape(english_term) + r'\b', chunk, re.IGNORECASE):
                    found_terms.append(f"- For the term '{english_term}', you must use the exact translation '{korean_formatted_term}'.")
            if found_terms:
                glossary_guidance = "### Specialized Terminology Guidelines\nYou must adhere to the following translation rules for specific terms found in the text:\n" + "\n".join(found_terms) + "\n\n"

        user_content = f"""{glossary_guidance}### Persona
You are a world-class expert translator specializing in academic papers. You have a Ph.D. in a relevant field and are a native Korean speaker with flawless English proficiency. Your translations are not just literal; they are deeply contextual, maintaining the original author's tone, nuance, and intent.

### Core Translation Rules
1.  **Translate Everything**: Translate the entire text from English to Korean. Do not summarize, omit, or add information. Preserve all original content, including footnotes, figure captions, and table data.
2.  **Professional & Academic Tone**: The translation must be formal, precise, and use standard academic Korean. Avoid colloquialisms or overly casual language.
3.  **Context is King**: Ensure the translation is contextually aware. The meaning of a term can change based on the surrounding text.

### Formatting Rule for Technical Terms
This is a critical rule. For all significant English technical terms, acronyms, or proper nouns, you MUST format them as follows: `KoreanTranslation(OriginalEnglish, KoreanTransliteration)`.

-   **`KoreanTranslation`**: The appropriate Korean translation of the term in the context of the sentence.
-   **`OriginalEnglish`**: The original English term.
-   **`KoreanTransliteration`**: A phonetic Hangul spelling of the **OriginalEnglish** term. This is how the English word is pronounced, written in Hangul. **Do not put the Korean translation here.**

#### Examples of the Formatting Rule:
-   **Input**: "This paper introduces an application of deep learning."
-   **Correct Output**: "이 논문은 딥러닝(deep learning, 딥러닝)의 한 응용 프로그램(application, 어플리케이션)을 소개합니다."

-   **Input**: "We used several inference engines."
-   **Correct Output**: "우리는 여러 추론 엔진(inference engines, 인퍼런스 엔진스)을 사용했습니다."
-   **Incorrect Output**: "우리는 여러 추론 엔진(inference engines, 추론 엔진)을 사용했습니다." (This is wrong because the transliteration part repeats the translation.)

### Handling Ambiguity
If a term is ambiguous, choose the most likely translation based on the academic context. If a direct translation is impossible or awkward, you may use a combination of translation and transliteration, but always follow the formatting rule.

### Final Instruction
Now, translate the following text, applying all rules and guidelines with the utmost precision.
---
{chunk}
"""

        for attempt in range(3):
            try:
                # Claude API는 system과 user_content를 별도로 전달
                result = self.call_claude_api(
                    system_prompt=self.SYS_RULES,
                    user_content=user_content
                )

                if not result:
                    raise RuntimeError("빈 응답")

                # Post-processing for glossary terms
                if self.custom_glossary:
                    for english_term, korean_formatted_term in self.custom_glossary.items():
                        # Ensure we replace whole words only and not parts of other words
                        # Also, avoid replacing if it's already in the desired format
                        result = re.sub(
                            r'\b' + re.escape(korean_formatted_term) + r'(?!\s*\()',
                            f'{korean_formatted_term}({english_term})',
                            result,
                            flags=re.IGNORECASE
                        )

                self.log(f"청크 {chunk_num}/{total_chunks} 완료 (out_chars={len(result)})")
                return result

            except Exception as e:
                self.log(f"청크 {chunk_num} 실패(시도 {attempt+1}/3): {e}")
                if attempt == 2:
                    raise
                time.sleep(1.2 * (attempt+1))

        return ""

    def extract_glossary_from_text(self, text: str) -> List[Dict]:
        """번역된 텍스트에서 용어집을 추출합니다."""
        self.log("번역된 텍스트에서 용어집 추출 시작...")
        system_prompt = "You are a helpful assistant that extracts structured data from text. Your output must be a valid JSON."
        user_prompt = f"""The following Korean text contains specially formatted technical terms. The format is `KoreanTranslation(OriginalEnglish, KoreanTransliteration)`.

Your task is to find all occurrences of this format and extract them into a valid JSON list.

Each JSON object in the list must have three keys:
1.  `"term"`: The OriginalEnglish string.
2.  `"translation"`: The KoreanTranslation string.
3.  `"transliteration"`: The KoreanTransliteration string.

**CRITICAL**:
- If you find no terms, you MUST return an empty JSON list `[]`.
- Your output MUST be only the JSON list, with no other text, explanations, or markdown formatting.
- Ensure the JSON is perfectly formatted.

**Example 1:**
- **Input Text**: "이 논문은 딥러닝(deep learning, 딥러닝)의 한 응용 프로그램(application, 어플리케이션)을 소개합니다."
- **Correct JSON Output**:
[
  {{"term": "deep learning", "translation": "딥러닝", "transliteration": "딥러닝"}},
  {{"term": "application", "translation": "응용 프로그램", "transliteration": "어플리케이션"}}
]

**Example 2:**
- **Input Text**: "이 텍스트에는 특별한 용어가 없습니다."
- **Correct JSON Output**:
[]

Now, process the following text and provide only the JSON output:
---
{text}
"""
        try:
            response_text = self.call_claude_api(system_prompt, user_prompt)
            # Find the JSON array in the response
            match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if not match:
                self.log(f"  - 용어집 추출 실패: 응답에서 JSON 배열을 찾지 못했습니다. 응답: {response_text}")
                return []
            glossary = json.loads(match.group(0))
            self.log(f"용어집 추출 완료: {len(glossary)}개 항목")
            return glossary
        except Exception as e:
            self.log(f"용어집 추출 중 오류 발생: {e}")
            return []
