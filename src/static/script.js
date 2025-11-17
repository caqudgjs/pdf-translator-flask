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
    
    // 로딩 시작
    showLoading();
    submitBtn.disabled = true;
    
    try {
        // 1. 파일 업로드 및 태스크 생성
        updateLoadingMessage('PDF 업로드 및 분석 중...');
        const uploadResponse = await fetch('/api/pdf/upload', {
            method: 'POST',
            body: formData
        });
        
        const uploadResult = await uploadResponse.json();
        
        if (!uploadResult.success) {
            throw new Error(uploadResult.message);
        }
        
        const { task_id, total_chunks } = uploadResult;
        
        // 2. 각 청크 병렬 번역
        await translateChunksParallel(task_id, total_chunks);
        
        // 3. 최종 결과 가져오기
        updateLoadingMessage('최종 결과 취합 중...');
        updateProgressBar(1); // 최종 단계이므로 100%로 설정
        const resultResponse = await fetch(`/api/pdf/result/${task_id}`);
        const finalResult = await resultResponse.json();
        
        if (finalResult.success) {
            translationResult = finalResult;
            displayResult(finalResult);
            resultSection.style.display = 'block';
            resultSection.scrollIntoView({ behavior: 'smooth' });
        } else {
            throw new Error(finalResult.message);
        }
        
    } catch (error) {
        console.error('Error:', error);
        alert('오류가 발생했습니다: ' + error.message);
    } finally {
        hideLoading();
        submitBtn.disabled = false;
    }
});

async function translateChunksParallel(taskId, totalChunks) {
    const concurrencyLimit = 5;
    const chunks = Array.from({ length: totalChunks }, (_, i) => i);
    let completedChunks = 0;

    async function translateWorker(chunkIndices) {
        for (const i of chunkIndices) {
            updateLoadingMessage(`청크 번역 중 (${completedChunks + 1}/${totalChunks})...`);
            
            const response = await fetch('/api/pdf/translate_chunk', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ task_id: taskId, chunk_index: i })
            });

            const result = await response.json();
            if (!result.success) {
                throw new Error(`청크 ${i} 번역 실패: ${result.message}`);
            }
            
            completedChunks++;
            updateProgressBar(completedChunks / totalChunks);
        }
    }

    const workers = [];
    const chunkSlices = [];
    for (let i = 0; i < concurrencyLimit; i++) {
        chunkSlices.push([]);
    }
    chunks.forEach((chunk, i) => {
        chunkSlices[i % concurrencyLimit].push(chunk);
    });

    for (let i = 0; i < concurrencyLimit; i++) {
        workers.push(translateWorker(chunkSlices[i]));
    }

    await Promise.all(workers);
}

// 로딩 UI 업데이트 함수들
function showLoading() {
    loadingOverlay.style.display = 'flex';
    progressFill.style.width = '0%';
}

function hideLoading() {
    loadingOverlay.style.display = 'none';
}

function updateLoadingMessage(message) {
    loadingMessage.textContent = message;
}

function updateProgressBar(progress) { // progress is 0 to 1
    progressFill.style.width = (progress * 100) + '%';
}


// 결과 표시
function displayResult(result) {
    // 번역문 표시
    translationText.textContent = result.translated_text;
    
    // 용어집 표시
    glossaryContent.innerHTML = '';
    const combinedGlossary = new Map();

    // 1. Add custom glossary (from dict.csv)
    if (result.glossary && typeof result.glossary === 'object') {
        for (const term in result.glossary) {
            if (Object.prototype.hasOwnProperty.call(result.glossary, term)) {
                if (!combinedGlossary.has(term)) {
                    combinedGlossary.set(term, result.glossary[term]);
                }
            }
        }
    }

    // 2. Add extracted glossary, giving priority to custom glossary
    if (result.extracted_glossary && Array.isArray(result.extracted_glossary)) {
        result.extracted_glossary.forEach(item => {
            if (item.term && !combinedGlossary.has(item.term)) {
                combinedGlossary.set(item.term, item.translation || '(번역 없음)');
            }
        });
    }

    if (combinedGlossary.size > 0) {
        combinedGlossary.forEach((translation, term) => {
            const glossaryItem = document.createElement('div');
            glossaryItem.className = 'glossary-item';
            glossaryItem.innerHTML = `
                <span class="glossary-term">${term}</span>
                <span class="glossary-translation">${translation}</span>
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
    
    const combinedGlossary = new Map();

    // 1. Add custom glossary (from dict.csv)
    if (translationResult.glossary && typeof translationResult.glossary === 'object') {
        for (const term in translationResult.glossary) {
            if (Object.prototype.hasOwnProperty.call(translationResult.glossary, term)) {
                if (!combinedGlossary.has(term)) {
                    combinedGlossary.set(term, translationResult.glossary[term]);
                }
            }
        }
    }

    // 2. Add extracted glossary, giving priority to custom glossary
    if (translationResult.extracted_glossary && Array.isArray(translationResult.extracted_glossary)) {
        translationResult.extracted_glossary.forEach(item => {
            if (item.term && !combinedGlossary.has(item.term)) {
                combinedGlossary.set(item.term, item.translation || '(번역 없음)');
            }
        });
    }

    let glossaryText = '';
    combinedGlossary.forEach((translation, term) => {
        glossaryText += `${term}: ${translation}\n`;
    });

    const content = `PDF 번역 결과\n\n번역문:\n${translationResult.translated_text}\n\n용어집:\n${glossaryText}`;
    
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
        const combinedGlossary = new Map();

        // 1. Add custom glossary (from dict.csv)
        if (translationResult.glossary && typeof translationResult.glossary === 'object') {
            for (const term in translationResult.glossary) {
                if (Object.prototype.hasOwnProperty.call(translationResult.glossary, term)) {
                    if (!combinedGlossary.has(term)) {
                        combinedGlossary.set(term, translationResult.glossary[term]);
                    }
                }
            }
        }

        // 2. Add extracted glossary, giving priority to custom glossary
        if (translationResult.extracted_glossary && Array.isArray(translationResult.extracted_glossary)) {
            translationResult.extracted_glossary.forEach(item => {
                if (item.term && !combinedGlossary.has(item.term)) {
                    combinedGlossary.set(item.term, item.translation || '(번역 없음)');
                }
            });
        }

        let glossaryText = '';
        combinedGlossary.forEach((translation, term) => {
            glossaryText += `${term}: ${translation}\n`;
        });
        textToCopy = glossaryText;
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

