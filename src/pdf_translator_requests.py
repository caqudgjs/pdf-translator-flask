# -*- coding: utf-8 -*-
"""
requests를 사용한 간단한 PDF 번역 모듈
배포 환경에서 호환성 문제를 해결하기 위해 단순화
"""

import os, io, re, json, time
from typing import List, Dict
import PyPDF2
import requests
import csv

class RequestsPDFTranslator:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.max_input_chars = 16000
        self.max_output_tokens = 16384
        self.custom_glossary = {} # Initialize custom glossary
        self.load_glossary_from_csv() # Load glossary on initialization

    def load_glossary_from_csv(self, file_path: str = "dict.csv"):
        """dict.csv 파일에서 사용자 정의 용어집을 로드합니다."""
        script_dir = os.path.dirname(__file__)
        full_file_path = os.path.join(script_dir, file_path)
        
        if not os.path.exists(full_file_path):
            self.log(f"경고: 용어집 파일 '{full_file_path}'을(를) 찾을 수 없습니다. 사용자 정의 용어집을 로드하지 않습니다.")
            return

        self.log(f"용어집 파일 '{full_file_path}' 로드 중...")
        try:
            with open(full_file_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for i, row in enumerate(reader):
                    if len(row) == 2:
                        english_term = row[0].strip()
                        korean_formatted_term = row[1].strip()
                        self.custom_glossary[english_term] = korean_formatted_term
                    else:
                        self.log(f"경고: 용어집 파일 '{file_path}'의 {i+1}번째 줄 형식이 올바르지 않습니다: {row}")
            self.log(f"용어집 로드 완료: {len(self.custom_glossary)}개 항목")
        except Exception as e:
            self.log(f"용어집 로드 중 오류 발생: {e}")
            self.custom_glossary = {} # Clear glossary on error

    def validate_api_key(self) -> bool:
        """OpenAI API 키 유효성 검사"""
        self.log("OpenAI API 키 유효성 검사 시작")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        try:
            # 모델 목록을 가져오는 간단한 API 호출로 키 유효성 검사
            response = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=10)
            if response.status_code == 200:
                self.log("OpenAI API 키 유효성 검사 성공")
                return True
            else:
                self.log(f"OpenAI API 키 유효성 검사 실패: {response.status_code} - {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            self.log(f"OpenAI API 키 유효성 검사 중 네트워크 오류: {e}")
            return False

    SYS_RULES = """You are an expert academic paper translator. Your task is to translate the provided text into Korean. You must follow the rules given by the user precisely."""

    def log(self, msg: str):
        """로그 메시지 출력"""
        t = time.strftime("%H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    def extract_text_from_pdf(self, pdf_file) -> str:
        """PDF 파일에서 텍스트 추출 (PyPDF2 사용)"""
        self.log("PDF 텍스트 추출 시작 (PyPDF2)")
        
        # 파일 객체를 BytesIO로 변환
        if hasattr(pdf_file, 'read'):
            bio = io.BytesIO(pdf_file.read())
        else:
            bio = io.BytesIO(pdf_file)
        
        try:
            reader = PyPDF2.PdfReader(bio)
            text_parts = []
            
            for page_num, page in enumerate(reader.pages, 1):
                page_text = page.extract_text()
                if page_text:
                    cleaned_text = page_text.encode('utf-8', 'ignore').decode('utf-8')
                    text_parts.append(f"\n[Page {page_num}]\n{cleaned_text}\n")
                self.log(f"  - 페이지 {page_num} 처리 완료")
            
            full_text = "".join(text_parts)
            self.log(f"PDF 텍스트 추출 완료: 총 {len(reader.pages)} 페이지")
            return full_text.strip()
            
        except Exception as e:
            raise RuntimeError(f"PDF 텍스트 추출 실패: {str(e)}")

    def split_text_into_chunks(self, text: str) -> List[str]:
        """텍스트를 페이지별로 청크로 분할"""
        if not text:
            return []

        # extract_text_from_pdf에서 추가된 첫 '\n' 제거
        if text.startswith('\n'):
            text = text[1:]

        pages = text.split('\n[Page ')
        
        chunks = []
        if pages:
            # 첫 페이지 처리
            chunks.append(pages[0].strip())

            # 나머지 페이지 처리
            for i in range(1, len(pages)):
                # '[Page ' 부분을 다시 붙여줌
                page_content = f"[Page {pages[i]}".strip()
                chunks.append(page_content)

        # 빈 청크 제거
        chunks = [c for c in chunks if c]

        # 페이지가 너무 긴 경우에 대한 처리
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > self.max_input_chars:
                self.log(f"경고: 페이지 청크가 최대 입력 길이({self.max_input_chars})를 초과하여 분할합니다.")
                # 문장 단위로 분할
                sub_chunks = []
                current_sub_chunk = ""
                sentences = re.split(r'(?<=[.!?])\s+', chunk)
                for sentence in sentences:
                    if len(current_sub_chunk) + len(sentence) > self.max_input_chars and current_sub_chunk:
                        sub_chunks.append(current_sub_chunk.strip())
                        current_sub_chunk = sentence
                    else:
                        current_sub_chunk += " " + sentence if current_sub_chunk else sentence
                if current_sub_chunk:
                    sub_chunks.append(current_sub_chunk.strip())
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)
        
        return final_chunks

    def call_openai_api(self, messages: List[Dict]) -> str:
        """OpenAI API 호출"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.max_output_tokens
        }
        response = requests.post(self.api_url, headers=headers, json=data, timeout=300)
        self.log(f"OpenAI API 응답 상태 코드: {response.status_code}")
        if response.status_code != 200:
            self.log(f"OpenAI API 오류 상세: {response.text}")
            raise RuntimeError(f"OpenAI API 오류: {response.status_code} - {response.text[:200]}...")
        try:
            result = response.json()
        except json.JSONDecodeError:
            raise RuntimeError(f"OpenAI API 응답 JSON 파싱 실패: {response.text}")
        if 'choices' not in result or not result['choices']:
            raise RuntimeError("OpenAI API 응답에 choices가 없습니다.")
        return result['choices'][0]['message']['content'].strip()

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

        messages = [
            {"role": "system", "content": self.SYS_RULES},
            {"role": "user", "content": user_content}
        ]
        
        for attempt in range(3):
            try:
                result = self.call_openai_api(messages)
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
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            response_text = self.call_openai_api(messages)
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

    def translate_pdf(self, pdf_file):
        """PDF 번역 메인 함수"""
        try:
            # API 키 유효성 검사
            if not self.validate_api_key():
                raise RuntimeError("유효하지 않은 OpenAI API 키입니다. 키를 확인해주세요.")

            # PDF에서 텍스트 추출
            text = self.extract_text_from_pdf(pdf_file)
            if not text.strip():
                raise RuntimeError("PDF에서 텍스트를 추출하지 못했습니다. (스캔본이면 OCR 선행 필요)")

            # 텍스트를 청크로 분할
            chunks = self.split_text_into_chunks(text)
            self.log(f"번역 시작: 청크 {len(chunks)}개")

            # 각 청크 번역
            translated_chunks = []
            for i, chunk in enumerate(chunks, 1):
                translated_chunk = self.translate_chunk(chunk, i, len(chunks))
                translated_chunks.append(translated_chunk)

            # 결과 합치기
            translated_text = "\n\n".join(translated_chunks)

            # 번역된 텍스트에서 용어집 추출
            extracted_glossary = self.extract_glossary_from_text(translated_text)

            return {
                'success': True,
                'translated_text': translated_text,
                'glossary': self.custom_glossary,
                'extracted_glossary': extracted_glossary,
                'message': '번역이 완료되었습니다.'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'번역 중 오류가 발생했습니다: {str(e)}'
            }

