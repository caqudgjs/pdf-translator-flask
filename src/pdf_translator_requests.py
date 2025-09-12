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
        
        self.SYS_RULES = """당신은 '논문 전문 번역기'입니다.
반드시 문서의 모든 문장을 빠짐없이 한국어로 **완전 번역**하되,
다음 표기 규칙을 지키세요(요약/생략 금지, 누락 금지).

[핵심 규칙]
1) 영문 기술/전문 용어는 **원문 + 괄호 안 한국어 음독**으로 표기합니다.
   - 형식: term(한글음독).  예) application → application(어플리케이션)
   - 약어(예: AI, API)도 같은 형식: AI(에이아이), API(에이피아이)

2) 전체 문장은 자연스러운 한국어로 번역합니다.
   - 지정된 용어만 원문을 보존하고, 나머지는 자연스럽게 번역합니다.

3) 일관성:
   - 동일한 영어 단어는 문서 전반에 걸쳐 같은 한글 음독을 사용합니다.
"""

    def log(self, msg: str):
        """로그 메시지 출력"""
        t = time.strftime("%H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    def extract_text_from_pdf(self, pdf_file) -> str:
        """PDF 파일에서 텍스트 추출 (PyPDF2 사용)"""
        self.log("PDF 텍스트 추출 시작")
        
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
                if page_text.strip():
                    text_parts.append(f"\n[Page {page_num}]\n{page_text}\n")
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
        
        # 페이지별로 분할
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
        
        response = requests.post(self.api_url, headers=headers, json=data, timeout=120)
        
        if response.status_code != 200:
            raise RuntimeError(f"OpenAI API 오류: {response.status_code} - {response.text}")
        
        result = response.json()
        
        if 'choices' not in result or not result['choices']:
            raise RuntimeError("OpenAI API 응답에 choices가 없습니다.")
        
        return result['choices'][0]['message']['content'].strip()

    def translate_chunk(self, chunk: str, chunk_num: int, total_chunks: int) -> str:
        """개별 청크 번역"""
        self.log(f"청크 {chunk_num}/{total_chunks} 번역 중... (chars={len(chunk)})")
        
        messages = [
            {"role": "system", "content": self.SYS_RULES},
            {
                "role": "user",
                "content": (
                    f"아래 원문을 규칙에 맞춰 **완전 번역**하세요. 요약/생략/누락 금지.\n"
                    f"영문 기술용어는 '원문(한국어 음독)'으로 표기하세요. 예: application → application(어플리케이션)\n\n"
                    f"{chunk}"
                )
            }
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

    def translate_pdf(self, pdf_file):
        """PDF 번역 메인 함수"""
        try:
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

            return {
                'success': True,
                'translated_text': translated_text,
                'glossary': [],  # 간단한 버전에서는 용어집 생략
                'message': '번역이 완료되었습니다.'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'번역 중 오류가 발생했습니다: {str(e)}'
            }

