# -*- coding: utf-8 -*-
"""
추상 베이스 클래스 - 모든 번역기가 상속하는 공통 인터페이스
"""

import os, io, re, time
from typing import List, Dict
from abc import ABC, abstractmethod
import PyPDF2
import csv


class BaseTranslator(ABC):
    """번역기의 추상 베이스 클래스"""

    # 공통 시스템 규칙
    SYS_RULES = """You are an expert academic paper translator. Your task is to translate the provided text into Korean. You must follow the rules given by the user precisely."""

    def __init__(self, api_key: str, model_name: str):
        """
        Args:
            api_key: API 키 (OpenAI 또는 Claude)
            model_name: 모델 이름
        """
        self.api_key = api_key
        self.model_name = model_name
        self.max_input_chars = 16000
        self.max_output_tokens = 16384  # 기본값, 서브클래스에서 오버라이드 가능
        self.custom_glossary = {}
        self.load_glossary_from_csv()

    @abstractmethod
    def validate_api_key(self) -> bool:
        """API 키 유효성 검사 (서브클래스에서 구현)"""
        pass

    @abstractmethod
    def translate_chunk(self, chunk: str, chunk_num: int, total_chunks: int) -> str:
        """개별 청크 번역 (서브클래스에서 구현)"""
        pass

    def log(self, msg: str):
        """로그 메시지 출력"""
        t = time.strftime("%H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

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
            self.custom_glossary = {}

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

    def translate_pdf(self, pdf_file):
        """PDF 번역 메인 함수"""
        try:
            # API 키 유효성 검사
            if not self.validate_api_key():
                raise RuntimeError("유효하지 않은 API 키입니다. 키를 확인해주세요.")

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
                'glossary': self.custom_glossary,
                'message': '번역이 완료되었습니다.'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'번역 중 오류가 발생했습니다: {str(e)}'
            }
