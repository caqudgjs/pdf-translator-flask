# -*- coding: utf-8 -*-
"""
최적화된 PDF 번역 API 라우트
"""

from flask import Blueprint, request, jsonify
from src.pdf_translator_optimized import OptimizedPDFTranslator

pdf_translate_optimized_bp = Blueprint('pdf_translate_optimized', __name__)

@pdf_translate_optimized_bp.route('/translate', methods=['POST'])
def translate_pdf():
    """PDF 번역 (최적화된 버전)"""
    try:
        # 파일 확인
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': '파일이 업로드되지 않았습니다.'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': '파일이 선택되지 않았습니다.'}), 400
        
        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'success': False, 'error': 'PDF 파일만 업로드 가능합니다.'}), 400
        
        # API 키 확인
        api_key = request.form.get('api_key')
        if not api_key:
            return jsonify({'success': False, 'error': 'API 키가 필요합니다.'}), 400
        
        # 모델명 확인
        model_name = request.form.get('model_name', 'gpt-4o-mini')
        
        # 번역기 인스턴스 생성
        translator = OptimizedPDFTranslator(api_key, model_name)
        
        # PDF 번역 실행
        result = translator.translate_pdf(file)
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify(result), 500
            
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'요청 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500

@pdf_translate_optimized_bp.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({'status': 'ok', 'message': '최적화된 PDF 번역 서비스가 정상 작동 중입니다.'})

