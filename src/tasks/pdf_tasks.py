# -*- coding: utf-8 -*-
"""
PDF 번역 비동기 작업
"""

import os
import sys
import io
import time
from celery import current_task
from src.celery_app import celery_app
from src.pdf_translator_requests import RequestsPDFTranslator

@celery_app.task(bind=True)
def translate_pdf_task(self, pdf_data, api_key, model_name="gpt-4o-mini"):
    """
    PDF 번역 비동기 작업
    
    Args:
        pdf_data: PDF 파일 데이터 (base64 인코딩된 바이트)
        api_key: OpenAI API 키
        model_name: 사용할 모델명
    
    Returns:
        dict: 번역 결과
    """
    try:
        # 작업 상태 업데이트
        self.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'PDF 파일 처리 중...'}
        )
        
        # PDF 데이터를 BytesIO로 변환
        import base64
        pdf_bytes = base64.b64decode(pdf_data)
        pdf_file = io.BytesIO(pdf_bytes)
        
        # 번역기 인스턴스 생성
        translator = RequestsPDFTranslator(api_key, model_name)
        
        # 작업 상태 업데이트
        self.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': 'API 키 유효성 검사 중...'}
        )
        
        # API 키 유효성 검사
        if not translator.validate_api_key():
            return {
                'success': False,
                'error': '유효하지 않은 OpenAI API 키입니다.',
                'message': 'API 키를 확인해주세요.'
            }
        
        # 작업 상태 업데이트
        self.update_state(
            state='PROGRESS',
            meta={'current': 20, 'total': 100, 'status': 'PDF 텍스트 추출 중...'}
        )
        
        # PDF에서 텍스트 추출
        text = translator.extract_text_from_pdf(pdf_file)
        if not text.strip():
            return {
                'success': False,
                'error': 'PDF에서 텍스트를 추출하지 못했습니다.',
                'message': '스캔본이면 OCR이 필요합니다.'
            }
        
        # 작업 상태 업데이트
        self.update_state(
            state='PROGRESS',
            meta={'current': 30, 'total': 100, 'status': '텍스트를 청크로 분할 중...'}
        )
        
        # 텍스트를 청크로 분할
        chunks = translator.split_text_into_chunks(text)
        total_chunks = len(chunks)
        
        # 각 청크 번역
        translated_chunks = []
        for i, chunk in enumerate(chunks, 1):
            # 작업 상태 업데이트
            progress = 30 + int((i / total_chunks) * 60)  # 30%에서 90%까지
            self.update_state(
                state='PROGRESS',
                meta={
                    'current': progress,
                    'total': 100,
                    'status': f'청크 {i}/{total_chunks} 번역 중...'
                }
            )
            
            translated_chunk = translator.translate_chunk(chunk, i, total_chunks)
            translated_chunks.append(translated_chunk)
        
        # 작업 상태 업데이트
        self.update_state(
            state='PROGRESS',
            meta={'current': 95, 'total': 100, 'status': '번역 결과 정리 중...'}
        )
        
        # 결과 합치기
        translated_text = "\n\n".join(translated_chunks)
        
        # 작업 완료
        return {
            'success': True,
            'translated_text': translated_text,
            'glossary': [],  # 간단한 버전에서는 용어집 생략
            'message': '번역이 완료되었습니다.'
        }
        
    except Exception as e:
        # 오류 발생 시
        return {
            'success': False,
            'error': str(e),
            'message': f'번역 중 오류가 발생했습니다: {str(e)}'
        }

