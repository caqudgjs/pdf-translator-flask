# -*- coding: utf-8 -*-
"""
requests를 사용한 간단한 PDF 번역 모듈
배포 환경에서 호환성 문제를 해결하기 위해 단순화
"""

import os, io, re, json, time
from typing import List, Dict
import PyPDF2
import requests

class RequestsPDFTranslator:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model_name
        self.api_url = "https://api.openai.com/v1/chat/completions"
        self.max_input_chars = 7000
        self.max_output_tokens = 3200

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
        """텍스트를 청크로 분할"""
        chunks = []
        current_chunk = ""
        pages = text.split('[Page ')
        
        for i, page in enumerate(pages):
            if not page.strip():
                continue
            page_text = f"[Page {page}" if i > 0 else page
            if len(current_chunk) + len(page_text) > self.max_input_chars and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = page_text
            else:
                current_chunk += "\n" + page_text if current_chunk else page_text
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        return chunks

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
        
        user_content = f"""Follow these rules strictly:
1. Translate the entire text into natural, fluent, and contextually-aware Korean, as if a professional human translator wrote it. Do not summarize or omit any part.
2. For all significant English technical terms, acronyms, or proper nouns, you MUST format them as: `KoreanTranslation(OriginalEnglish, KoreanTransliteration)`.
3. For the `KoreanTransliteration` part, you must provide a phonetic Hangul spelling of the **OriginalEnglish** term. This means writing the English pronunciation in Hangul characters. **Do not put the Korean translation here.**
4. For the `KoreanTranslation` part, you must provide the appropriate Korean translation of the term in the context of the sentence.

Examples of rule #2:
- Input: "This paper introduces an application of deep learning."
- Correct Output: "이 논문은 딥러닝(deep learning, 딥러닝)의 한 응용 프로그램(application, 어플리케이션)을 소개합니다."

- Input: "We used several inference engines."
- Correct Output: "우리는 여러 추론 엔진(inference engines, 인퍼런스 엔진스)을 사용했습니다."
- Incorrect Output: "우리는 여러 추론 엔진(inference engines, 추론 엔진)을 사용했습니다." (This is wrong because the transliteration part repeats the translation.)

Now, translate the following text:
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
        system_prompt = "You are a helpful assistant that extracts structured data from text."
        user_prompt = f"""The following Korean text contains specially formatted technical terms. The format is `KoreanTranslation(OriginalEnglish, KoreanTransliteration)`.
Find all occurrences of this format and extract them into a JSON list.
Each JSON object in the list should have three keys: "term" (for the OriginalEnglish), "translation" (for the KoreanTranslation), and "transliteration" (for the KoreanTransliteration).
If you don't find any, return an empty list [].
Only return the JSON list, with no other text.

Example Input Text: "이 논문은 딥러닝(deep learning, 딥러닝)의 한 응용 프로그램(application, 어플리케이션)을 소개합니다."
Example JSON Output:
[
  {{"term": "deep learning", "translation": "딥러닝", "transliteration": "딥러닝"}},
  {{"term": "application", "translation": "응용 프로그램", "transliteration": "어플리케이션"}}
]

Now, process the following text:
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
            match = re.search(r'[[].*[]]', response_text, re.DOTALL)
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
            glossary = self.extract_glossary_from_text(translated_text)

            return {
                'success': True,
                'translated_text': translated_text,
                'glossary': glossary,  # 간단한 버전에서는 용어집 생략
                'message': '번역이 완료되었습니다.'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'번역 중 오류가 발생했습니다: {str(e)}'
            }

