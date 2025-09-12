# -*- coding: utf-8 -*-
"""
Celery 앱 설정
"""

from celery import Celery
import os

# Celery 앱 생성
celery_app = Celery('pdf_translator')

# Redis를 브로커로 사용 (로컬 환경)
celery_app.conf.broker_url = 'redis://localhost:6379/0'
celery_app.conf.result_backend = 'redis://localhost:6379/0'

# 작업 설정
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Seoul',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30분 타임아웃
    task_soft_time_limit=25 * 60,  # 25분 소프트 타임아웃
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# 작업 자동 발견
celery_app.autodiscover_tasks(['src.tasks'])

