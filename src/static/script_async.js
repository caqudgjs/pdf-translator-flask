// 비동기 PDF 번역기 JavaScript

class AsyncPDFTranslator {
    constructor() {
        this.currentTaskId = null;
        this.statusCheckInterval = null;
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        // DOM 요소들
        this.fileUploadArea = document.getElementById('fileUploadArea');
        this.fileInput = document.getElementById('pdfFile');
        this.fileInfo = document.getElementById('fileInfo');
        this.fileName = document.getElementById('fileName');
        this.fileSize = document.getElementById('fileSize');
        this.removeFileBtn = document.getElementById('removeFile');
        this.translateForm = document.getElementById('translateForm');
        this.submitBtn = document.getElementById('submitBtn');
        this.loadingOverlay = document.getElementById('loadingOverlay');
        this.loadingMessage = document.getElementById('loadingMessage');
        this.progressFill = document.getElementById('progressFill');
        this.resultSection = document.getElementById('resultSection');
        this.translationText = document.getElementById('translationText');
        this.glossaryContent = document.getElementById('glossaryContent');
        this.downloadBtn = document.getElementById('downloadBtn');
        this.copyBtn = document.getElementById('copyBtn');
    }

    bindEvents() {
        // 파일 업로드 이벤트
        this.fileUploadArea.addEventListener('click', () => this.fileInput.click());
        this.fileUploadArea.addEventListener('dragover', (e) => this.handleDragOver(e));
        this.fileUploadArea.addEventListener('drop', (e) => this.handleDrop(e));
        this.fileInput.addEventListener('change', (e) => this.handleFileSelect(e));
        this.removeFileBtn.addEventListener('click', () => this.removeFile());

        // 폼 제출 이벤트
        this.translateForm.addEventListener('submit', (e) => this.handleSubmit(e));

        // 결과 액션 이벤트
        this.downloadBtn.addEventListener('click', () => this.downloadResult());
        this.copyBtn.addEventListener('click', () => this.copyResult());

        // 탭 이벤트
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', (e) => this.switchTab(e));
        });
    }

    handleDragOver(e) {
        e.preventDefault();
        this.fileUploadArea.classList.add('drag-over');
    }

    handleDrop(e) {
        e.preventDefault();
        this.fileUploadArea.classList.remove('drag-over');
        
        const files = e.dataTransfer.files;
        if (files.length > 0) {
            this.processFile(files[0]);
        }
    }

    handleFileSelect(e) {
        const file = e.target.files[0];
        if (file) {
            this.processFile(file);
        }
    }

    processFile(file) {
        if (!file.type.includes('pdf')) {
            this.showError('PDF 파일만 업로드 가능합니다.');
            return;
        }

        if (file.size > 50 * 1024 * 1024) {
            this.showError('파일 크기는 50MB를 초과할 수 없습니다.');
            return;
        }

        this.fileName.textContent = file.name;
        this.fileSize.textContent = this.formatFileSize(file.size);
        this.fileInfo.style.display = 'flex';
        this.fileUploadArea.style.display = 'none';
    }

    removeFile() {
        this.fileInput.value = '';
        this.fileInfo.style.display = 'none';
        this.fileUploadArea.style.display = 'flex';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    async handleSubmit(e) {
        e.preventDefault();

        const formData = new FormData(this.translateForm);
        
        if (!this.fileInput.files[0]) {
            this.showError('PDF 파일을 선택해주세요.');
            return;
        }

        if (!formData.get('api_key')) {
            this.showError('OpenAI API 키를 입력해주세요.');
            return;
        }

        this.showLoading();
        
        try {
            // 비동기 번역 요청
            const response = await fetch('/api/pdf/async/translate', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                this.currentTaskId = result.task_id;
                this.startStatusCheck();
            } else {
                this.hideLoading();
                this.showError(result.message || '번역 요청 실패');
            }
        } catch (error) {
            this.hideLoading();
            this.showError('네트워크 오류가 발생했습니다: ' + error.message);
        }
    }

    startStatusCheck() {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
        }

        this.statusCheckInterval = setInterval(() => {
            this.checkTaskStatus();
        }, 2000); // 2초마다 상태 확인
    }

    async checkTaskStatus() {
        if (!this.currentTaskId) return;

        try {
            const response = await fetch(`/api/pdf/async/status/${this.currentTaskId}`);
            const status = await response.json();

            this.updateProgress(status);

            if (status.state === 'SUCCESS') {
                this.handleSuccess(status.result);
            } else if (status.state === 'FAILURE') {
                this.handleFailure(status.error);
            }
        } catch (error) {
            console.error('상태 확인 오류:', error);
        }
    }

    updateProgress(status) {
        const progress = status.current || 0;
        const statusText = status.status || '작업 진행 중...';

        this.progressFill.style.width = `${progress}%`;
        this.loadingMessage.textContent = statusText;
    }

    handleSuccess(result) {
        this.stopStatusCheck();
        this.hideLoading();

        if (result.success) {
            this.showResult(result);
        } else {
            this.showError(result.message || '번역 실패');
        }
    }

    handleFailure(error) {
        this.stopStatusCheck();
        this.hideLoading();
        this.showError('번역 실패: ' + error);
    }

    stopStatusCheck() {
        if (this.statusCheckInterval) {
            clearInterval(this.statusCheckInterval);
            this.statusCheckInterval = null;
        }
        this.currentTaskId = null;
    }

    showResult(result) {
        this.translationText.textContent = result.translated_text || '';
        
        if (result.glossary && result.glossary.length > 0) {
            this.glossaryContent.innerHTML = result.glossary.map(term => 
                `<div class="glossary-item">
                    <strong>${term.original}</strong>: ${term.translation}
                </div>`
            ).join('');
        } else {
            this.glossaryContent.innerHTML = '<p>용어집이 생성되지 않았습니다.</p>';
        }

        this.resultSection.style.display = 'block';
        this.resultSection.scrollIntoView({ behavior: 'smooth' });
    }

    showLoading() {
        this.loadingOverlay.style.display = 'flex';
        this.submitBtn.disabled = true;
        this.progressFill.style.width = '0%';
        this.loadingMessage.textContent = 'PDF를 분석하고 있습니다...';
    }

    hideLoading() {
        this.loadingOverlay.style.display = 'none';
        this.submitBtn.disabled = false;
    }

    showError(message) {
        alert('오류: ' + message);
    }

    switchTab(e) {
        const tabName = e.target.dataset.tab;
        
        // 탭 버튼 활성화 상태 변경
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
        e.target.classList.add('active');
        
        // 탭 콘텐츠 표시 상태 변경
        document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
        document.getElementById(tabName + 'Tab').classList.add('active');
    }

    downloadResult() {
        const text = this.translationText.textContent;
        if (!text) {
            this.showError('다운로드할 번역 결과가 없습니다.');
            return;
        }

        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'translation_result.txt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    async copyResult() {
        const text = this.translationText.textContent;
        if (!text) {
            this.showError('복사할 번역 결과가 없습니다.');
            return;
        }

        try {
            await navigator.clipboard.writeText(text);
            this.copyBtn.innerHTML = '<i class="fas fa-check"></i> 복사됨';
            setTimeout(() => {
                this.copyBtn.innerHTML = '<i class="fas fa-copy"></i> 복사';
            }, 2000);
        } catch (error) {
            this.showError('클립보드 복사에 실패했습니다.');
        }
    }
}

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    new AsyncPDFTranslator();
});

