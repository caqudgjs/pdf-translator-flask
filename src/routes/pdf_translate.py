from flask import Blueprint, request, jsonify, current_app
from werkzeug.utils import secure_filename
import os
import uuid
import json
from src.pdf_translator_requests import RequestsPDFTranslator

pdf_translate_bp = Blueprint('pdf_translate', __name__)

ALLOWED_EXTENSIONS = {'pdf'}
TEMP_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'temp_translations')
os.makedirs(TEMP_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@pdf_translate_bp.route('/upload', methods=['POST'])
def upload_pdf():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'PDF 파일이 필요합니다.'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'message': '파일이 선택되지 않았습니다.'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'PDF 파일만 업로드 가능합니다.'}), 400
    
    api_key = request.form.get('api_key')
    model_name = request.form.get('model_name', 'gpt-4o-mini')
    
    if not api_key:
        return jsonify({'success': False, 'message': 'OpenAI API 키가 필요합니다.'}), 400

    try:
        translator = RequestsPDFTranslator(api_key=api_key, model_name=model_name)
        if not translator.validate_api_key():
            return jsonify({'success': False, 'message': '유효하지 않은 OpenAI API 키입니다.'}), 401

        task_id = str(uuid.uuid4())
        task_dir = os.path.join(TEMP_FOLDER, task_id)
        os.makedirs(task_dir)

        file_content = file.read()
        text = translator.extract_text_from_pdf(file_content)
        if not text.strip():
            return jsonify({'success': False, 'message': 'PDF에서 텍스트를 추출하지 못했습니다.'}), 400

        chunks = translator.split_text_into_chunks(text)
        
        task_info = {
            'api_key': api_key,
            'model_name': model_name,
            'total_chunks': len(chunks)
        }
        with open(os.path.join(task_dir, 'task_info.json'), 'w', encoding='utf-8') as f:
            json.dump(task_info, f)

        for i, chunk in enumerate(chunks):
            with open(os.path.join(task_dir, f'chunk_{i}_original.txt'), 'w', encoding='utf-8') as f:
                f.write(chunk)

        return jsonify({
            'success': True,
            'task_id': task_id,
            'total_chunks': len(chunks),
            'message': '파일 업로드 및 텍스트 추출이 완료되었습니다. 번역을 시작하세요.'
        })

    except Exception as e:
        current_app.logger.error(f"PDF 업로드 중 오류 발생: {str(e)}")
        return jsonify({'success': False, 'message': f'서버 오류: {str(e)}'}), 500

@pdf_translate_bp.route('/translate_chunk', methods=['POST'])
def translate_chunk_route():
    data = request.get_json()
    task_id = data.get('task_id')
    chunk_index = data.get('chunk_index')

    if not task_id or chunk_index is None:
        return jsonify({'success': False, 'message': 'task_id와 chunk_index가 필요합니다.'}), 400

    task_dir = os.path.join(TEMP_FOLDER, task_id)
    if not os.path.isdir(task_dir):
        return jsonify({'success': False, 'message': '잘못된 task_id입니다.'}), 404

    try:
        with open(os.path.join(task_dir, 'task_info.json'), 'r', encoding='utf-8') as f:
            task_info = json.load(f)
        
        api_key = task_info['api_key']
        model_name = task_info['model_name']
        total_chunks = task_info['total_chunks']

        original_chunk_path = os.path.join(task_dir, f'chunk_{chunk_index}_original.txt')
        with open(original_chunk_path, 'r', encoding='utf-8') as f:
            chunk_content = f.read()

        translator = RequestsPDFTranslator(api_key=api_key, model_name=model_name)
        translated_chunk = translator.translate_chunk(chunk_content, chunk_index + 1, total_chunks)

        translated_chunk_path = os.path.join(task_dir, f'chunk_{chunk_index}_translated.txt')
        with open(translated_chunk_path, 'w', encoding='utf-8') as f:
            f.write(translated_chunk)

        return jsonify({'success': True, 'message': f'청크 {chunk_index + 1}/{total_chunks} 번역 완료'})

    except Exception as e:
        current_app.logger.error(f"청크 번역 중 오류 발생: {str(e)}")
        return jsonify({'success': False, 'message': f'서버 오류: {str(e)}'}), 500

@pdf_translate_bp.route('/result/<task_id>', methods=['GET'])
def get_result(task_id):
    task_dir = os.path.join(TEMP_FOLDER, task_id)
    if not os.path.isdir(task_dir):
        return jsonify({'success': False, 'message': '잘못된 task_id입니다.'}), 404

    try:
        with open(os.path.join(task_dir, 'task_info.json'), 'r', encoding='utf-8') as f:
            task_info = json.load(f)
        
        total_chunks = task_info['total_chunks']
        translated_chunks = []
        for i in range(total_chunks):
            chunk_path = os.path.join(task_dir, f'chunk_{i}_translated.txt')
            if not os.path.exists(chunk_path):
                return jsonify({'success': False, 'message': f'청크 {i}의 번역이 아직 완료되지 않았습니다.'}), 400
            with open(chunk_path, 'r', encoding='utf-8') as f:
                translated_chunks.append(f.read())
        
        full_translated_text = "\n\n".join(translated_chunks)

        # Glossary extraction
        translator = RequestsPDFTranslator(api_key=task_info['api_key'], model_name=task_info['model_name'])
        extracted_glossary = translator.extract_glossary_from_text(full_translated_text)

        # Clean up temporary files
        for f in os.listdir(task_dir):
            os.remove(os.path.join(task_dir, f))
        os.rmdir(task_dir)

        return jsonify({
            'success': True,
            'translated_text': full_translated_text,
            'glossary': translator.custom_glossary,
            'extracted_glossary': extracted_glossary
        })

    except Exception as e:
        current_app.logger.error(f"결과 취합 중 오류 발생: {str(e)}")
        return jsonify({'success': False, 'message': f'서버 오류: {str(e)}'}), 500
