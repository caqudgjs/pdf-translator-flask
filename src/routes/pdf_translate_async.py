# -*- coding: utf-8 -*-
"""
비동기 PDF 번역 API 라우트
"""

import base64
import uuid
from flask import Blueprint, request, jsonify
from src.tasks.pdf_tasks import translate_pdf_task
from src.celery_app import celery_app

pdf_translate_async_bp = Blueprint('pdf_translate_async', __name__)

@pdf_translate_async_bp.route('/translate', methods=['POST'])
def translate_pdf():
    """PDF 번역 요청 (비동기)"""
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
        
        # PDF 파일을 base64로 인코딩
        pdf_data = base64.b64encode(file.read()).decode('utf-8')
        
        # 비동기 작업 시작
        task = translate_pdf_task.delay(pdf_data, api_key, model_name)
        
        return jsonify({
            'success': True,
            'task_id': task.id,
            'message': '번역 작업이 시작되었습니다.'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'message': f'요청 처리 중 오류가 발생했습니다: {str(e)}'
        }), 500

@pdf_translate_async_bp.route('/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """작업 상태 확인"""
    try:
        task = celery_app.AsyncResult(task_id)
        
        if task.state == 'PENDING':
            # 작업이 아직 시작되지 않음
            response = {
                'state': task.state,
                'current': 0,
                'total': 100,
                'status': '작업 대기 중...'
            }
        elif task.state == 'PROGRESS':
            # 작업 진행 중
            response = {
                'state': task.state,
                'current': task.info.get('current', 0),
                'total': task.info.get('total', 100),
                'status': task.info.get('status', '작업 진행 중...')
            }
        elif task.state == 'SUCCESS':
            # 작업 완료
            response = {
                'state': task.state,
                'current': 100,
                'total': 100,
                'status': '번역 완료',
                'result': task.result
            }
        else:
            # 작업 실패
            response = {
                'state': task.state,
                'current': 100,
                'total': 100,
                'status': '작업 실패',
                'error': str(task.info)
            }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({
            'state': 'FAILURE',
            'current': 100,
            'total': 100,
            'status': '상태 확인 실패',
            'error': str(e)
        }), 500

@pdf_translate_async_bp.route('/health', methods=['GET'])
def health_check():
    """헬스 체크"""
    return jsonify({'status': 'ok', 'message': 'PDF 번역 서비스가 정상 작동 중입니다.'})

