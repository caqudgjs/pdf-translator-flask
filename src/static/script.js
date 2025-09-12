// DOM 요소들
const fileUploadArea = document.getElementById('fileUploadArea');
const pdfFileInput = document.getElementById('pdfFile');
const fileInfo = document.getElementById('fileInfo');
const fileName = document.getElementById('fileName');
const fileSize = document.getElementById('fileSize');
const removeFileBtn = document.getElementById('removeFile');
const translateForm = document.getElementById('translateForm');
const submitBtn = document.getElementById('submitBtn');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const progressFill = document.getElementById('progressFill');
const resultSection = document.getElementById('resultSection');
const translationText = document.getElementById('translationText');
const glossaryContent = document.getElementById('glossaryContent');
const downloadBtn = document.getElementById('downloadBtn');
const copyBtn = document.getElementById('copyBtn');
const tabBtns = document.querySelectorAll('.tab-btn');
const tabContents = document.querySelectorAll('.tab-content');

let selectedFile = null;
let translationResult = null;

// 파일 크기 포맷팅
function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 파일 업로드 영역 이벤트
fileUploadArea.addEventListener('click', () => {
    pdfFileInput.click();
});

fileUploadArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileUploadArea.classList.add('dragover');
});

fileUploadArea.addEventListener('dragleave', () => {
    fileUploadArea.classList.remove('dragover');
});

fileUploadArea.addEventListener('drop', (e) => {
    e.preventDefault();
    fileUploadArea.classList.remove('dragover');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        handleFileSelect(files[0]);
    }
});

// 파일 선택 이벤트
pdfFileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        handleFileSelect(e.target.files[0]);
    }
});

// 파일 선택 처리
function handleFileSelect(file) {
    selectedFile = file;

    if (file.type !== 'application/pdf') {
        alert('PDF 파일만 업로드 가능합니다.');
        return;
    }
    
    if (file.size > 50 * 1024 * 1024) { // 50MB
        alert('파일 크기는 50MB를 초과할 수 없습니다.');
        return;
    }
    
    selectedFile = file;
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileUploadArea.style.display = 'none';
    fileInfo.style.display = 'flex';
}

// 파일 제거
removeFileBtn.addEventListener('click', () => {
    selectedFile = null;
    pdfFileInput.value = '';
    fileUploadArea.style.display = 'block';
    fileInfo.style.display = 'none';
});

// 탭 전환
tabBtns.forEach(btn => {
    btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        
        // 모든 탭 버튼과 컨텐츠 비활성화
        tabBtns.forEach(b => b.classList.remove('active'));
        tabContents.forEach(c => c.classList.remove('active'));
        
        // 선택된 탭 활성화
        btn.classList.add('active');
        document.getElementById(targetTab + 'Tab').classList.add('active');
    });
});

// 폼 제출
translateForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    
    if (!selectedFile) {
        alert('PDF 파일을 선택해주세요.');
        return;
    }
    
    const apiKey = document.getElementById('apiKey').value.trim();
    if (!apiKey) {
        alert('OpenAI API 키를 입력해주세요.');
        return;
    }
    
    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('api_key', apiKey);
    formData.append('model_name', document.getElementById('modelName').value);
    formData.append('generate_ko', document.getElementById('generateKo').checked);
    
    // 로딩 시작
    showLoading();
    submitBtn.disabled = true;
    
    try {
        const response = await fetch('/api/pdf/translate', {
            method: 'POST',
            body: formData
        });
        
        const result = await response.json();
        
        if (result.success) {
            translationResult = result;
            displayResult(result);
            resultSection.style.display = 'block';
            resultSection.scrollIntoView({ behavior: 'smooth' });
        } else {
            alert('번역 실패: ' + result.message);
        }
    } catch (error) {
        console.error('Error:', error);
        alert('서버 오류가 발생했습니다: ' + error.message);
    } finally {
        hideLoading();
        submitBtn.disabled = false;
    }
});

// 로딩 표시
function showLoading() {
    loadingOverlay.style.display = 'flex';
    
    const messages = [
        'PDF를 분석하고 있습니다...',
        '용어를 추출하고 있습니다...',
        '한국어 음독을 생성하고 있습니다...',
        '번역을 진행하고 있습니다...',
        '결과를 정리하고 있습니다...'
    ];
    
    let messageIndex = 0;
    const messageInterval = setInterval(() => {
        if (messageIndex < messages.length) {
            loadingMessage.textContent = messages[messageIndex];
            messageIndex++;
        } else {
            clearInterval(messageInterval);
        }
    }, 3000);
    
    // 프로그레스 바 애니메이션
    let progress = 0;
    const progressInterval = setInterval(() => {
        progress += Math.random() * 10;
        if (progress > 90) progress = 90;
        progressFill.style.width = progress + '%';
    }, 500);
    
    // 로딩 완료 시 정리를 위해 interval ID 저장
    loadingOverlay.messageInterval = messageInterval;
    loadingOverlay.progressInterval = progressInterval;
}

// 로딩 숨기기
function hideLoading() {
    loadingOverlay.style.display = 'none';
    
    // interval 정리
    if (loadingOverlay.messageInterval) {
        clearInterval(loadingOverlay.messageInterval);
    }
    if (loadingOverlay.progressInterval) {
        clearInterval(loadingOverlay.progressInterval);
    }
    
    // 프로그레스 바 리셋
    progressFill.style.width = '0%';
}

// 결과 표시
function displayResult(result) {
    // 번역문 표시
    translationText.textContent = result.translated_text;
    
    // 용어집 표시
    glossaryContent.innerHTML = '';
    if (result.glossary && result.glossary.length > 0) {
        result.glossary.forEach(item => {
            const glossaryItem = document.createElement('div');
            glossaryItem.className = 'glossary-item';
            glossaryItem.innerHTML = `
                <span class="glossary-term">${item.term}</span>
                <span class="glossary-translation">${item.ko || '(음독 없음)'}</span>
            `;
            glossaryContent.appendChild(glossaryItem);
        });
    } else {
        glossaryContent.innerHTML = '<p>용어집이 생성되지 않았습니다.</p>';
    }
}

// 다운로드 기능
downloadBtn.addEventListener('click', () => {
    if (!translationResult) return;
    
    const content = `PDF 번역 결과\n\n번역문:\n${translationResult.translated_text}\n\n용어집:\n${
        translationResult.glossary.map(item => `${item.term}: ${item.ko || '(음독 없음)'}`).join('\n')
    }`;
    
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${selectedFile.name.replace('.pdf', '')}_번역결과.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

// 복사 기능
copyBtn.addEventListener('click', async () => {
    if (!translationResult) return;
    
    const activeTab = document.querySelector('.tab-btn.active').getAttribute('data-tab');
    let textToCopy = '';
    
    if (activeTab === 'translation') {
        textToCopy = translationResult.translated_text;
    } else {
        textToCopy = translationResult.glossary.map(item => 
            `${item.term}: ${item.ko || '(음독 없음)'}`
        ).join('\n');
    }
    
    try {
        await navigator.clipboard.writeText(textToCopy);
        
        // 복사 완료 피드백
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fas fa-check"></i> 복사됨';
        copyBtn.style.background = '#48bb78';
        copyBtn.style.color = 'white';
        
        setTimeout(() => {
            copyBtn.innerHTML = originalText;
            copyBtn.style.background = '';
            copyBtn.style.color = '';
        }, 2000);
    } catch (err) {
        alert('복사에 실패했습니다.');
    }
});

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    // 결과 섹션 숨기기
    resultSection.style.display = 'none';
});

