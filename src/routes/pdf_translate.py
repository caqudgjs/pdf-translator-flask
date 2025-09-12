from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import tempfile
from src.pdf_translator import PDFTranslator

pdf_translate_bp = Blueprint('pdf_translate', __name__)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@pdf_translate_bp.route('/translate', methods=['POST'])
def translate_pdf():
    try:
        # 요청 데이터 검증
        if 'file' not in request.files:
            return jsonify({'success': False, 'message': 'PDF 파일이 필요합니다.'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'message': '파일이 선택되지 않았습니다.'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'message': 'PDF 파일만 업로드 가능합니다.'}), 400
        
        # API 키와 모델명 가져오기
        api_key = request.form.get('api_key')
        model_name = request.form.get('model_name', 'gpt-4o-mini')
        generate_ko = request.form.get('generate_ko', 'true').lower() == 'true'
        
        if not api_key:
            return jsonify({'success': False, 'message': 'OpenAI API 키가 필요합니다.'}), 400
        
        # PDF 번역기 초기화
        translator = PDFTranslator(api_key=api_key, model_name=model_name)
        
        # 파일 읽기
        file_content = file.read()
        
        # PDF 번역 수행
        result = translator.translate_pdf(file_content, generate_ko=generate_ko)
        
        return jsonify(result)
        
    except Exception as e:
        current_app.logger.error(f"PDF 번역 중 오류 발생: {str(e)}")
        return jsonify({
            'success': False, 
            'message': f'서버 오류가 발생했습니다: {str(e)}'
        }), 500

@pdf_translate_bp.route('/health', methods=['GET'])
def health_check():
    """서비스 상태 확인"""
    return jsonify({'status': 'healthy', 'message': 'PDF 번역 서비스가 정상 작동 중입니다.'})

