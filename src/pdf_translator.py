# -*- coding: utf-8 -*-
"""
PDF 번역 모듈
기존 스크립트를 Flask 웹앱에서 사용할 수 있도록 모듈화
"""

import os, io, re, json, time, tempfile
from dataclasses import dataclass
from typing import List, Dict, Tuple
from collections import Counter, defaultdict
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTTextContainer, LTChar
from openai import OpenAI

@dataclass
class Span:
    text: str
    page: int
    italic: bool
    block: int

class PDFTranslator:
    def __init__(self, api_key: str, model_name: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)
        self.glossary_top_n = 120
        self.max_input_chars = 7000
        self.max_output_tokens = 3200
        
        # 정규식 패턴들
        self.BINOMIAL = re.compile(r"\b[A-Z][a-z]+ [a-z]+(?: [a-z]+)?\b")
        self.ABBR = re.compile(r"\b[A-Z]{2,}(?:\d+)?(?:-\d+)?\b")
        self.CAMEL = re.compile(r"\b[A-Z][a-z]+[A-Z][A-Za-z0-9-]*\b")
        self.MODEL = re.compile(r"\b([A-Za-z]+(?:\d+)?(?:-[A-Za-z0-9]+)*)\b")
        self.ASCII_LOWER = re.compile(r"\b[a-z][a-z\-]{3,}\b")
        
        self.STOPWORDS = {
            "the","and","for","with","that","this","from","were","was","are","have","has","had",
            "into","onto","over","under","between","among","within","without","about","above","below",
            "into","than","then","when","where","which","while","what","such","these","those","their",
            "there","here","each","other","both","most","more","less","very","much","many","some",
            "any","all","every","not","only","also","can","could","may","might","should","would",
            "use","used","using","based","given","make","made","makeup","takes","taken","taking",
            "we","our","you","they","he","she","it","its","them","his","her","him","as","of","in","on","at","by","to","or","an","a","is","be","do","did","does"
        }
        
        self.SYS_RULES = """당신은 '논문 전문 음독 번역기'입니다.
반드시 문서의 모든 문장을 빠짐없이 한국어로 **완전 번역**하되,
다음 표기 규칙을 100% 지키세요(요약/생략 금지, 누락 금지).

[핵심 규칙 — 항상 같은 형식]
1) 용어시트의 term 및 본문 내 영문 기술/전문 용어는 **원문 + 괄호 안 한국어 음독**으로 매번 표기합니다.
   - 형식: term(한글음독).  예) application → application(어플리케이션)
   - 약어(예: AI, RPKM)도 같은 형식: AI(에이아이), RPKM(아르피케이엠)
   - 이미 앞에서 나온 단어라도 **매번 동일한 표기**를 유지합니다.

2) type=species 이면 원문 학명을 기울임 강조 표기로 두고 뒤에 음독을 붙입니다.
   - 형식: *Genus species*(한글음독)
   - 텍스트 파일이므로 기울임은 별표(*)로 표시합니다.

3) 용어시트 항목의 ko가 비어있으면, 문맥에 맞는 한국어 음독을 **생성하여** 괄호에 채웁니다.

4) 위 규칙을 적용하면서도 전체 문장은 자연스러운 한국어로 번역합니다.
   - 지정된 용어만 원문을 보존하고, 나머지는 자연스럽게 번역합니다.

5) 일관성:
   - 동일한 영어 단어는 문서 전반에 걸쳐 같은 한글 음독을 사용합니다.
"""

    def log(self, msg: str):
        """로그 메시지 출력"""
        t = time.strftime("%H:%M:%S")
        print(f"[{t}] {msg}", flush=True)

    def parse_pdf_with_italics(self, pdf_file) -> List[Span]:
        """PDF 파일에서 텍스트와 이탤릭 정보 추출"""
        spans: List[Span] = []
        total_pages = 0
        self.log("PDF 파싱 시작")
        
        # 파일 객체를 BytesIO로 변환
        if hasattr(pdf_file, 'read'):
            bio = io.BytesIO(pdf_file.read())
        else:
            bio = io.BytesIO(pdf_file)

        for pageno, page_layout in enumerate(extract_pages(bio), start=1):
            total_pages = pageno
            italic_blocks = 0
            block_id = 0
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    text = element.get_text()
                    italic_count, total = 0, 0
                    for line in element:
                        for ch in getattr(line, "_objs", []):
                            if isinstance(ch, LTChar):
                                total += 1
                                fname = (ch.fontname or "").lower()
                                if "italic" in fname or "oblique" in fname:
                                    italic_count += 1
                    is_italic = (total > 0 and italic_count/total >= 0.5)
                    if text.strip():
                        spans.append(Span(text=text, page=pageno, italic=is_italic, block=block_id))
                        if is_italic: italic_blocks += 1
                        block_id += 1
            self.log(f"  - 페이지 {pageno} 처리: 텍스트블록 {block_id}개 (이탤릭블록 {italic_blocks}개)")
        
        self.log(f"PDF 파싱 완료: 총 {total_pages} 페이지, 총 스팬 {len(spans)}")
        return spans

    def section_weight(self, span: Span, idx: int) -> float:
        """섹션별 가중치 계산"""
        t = span.text.strip()
        w = 1.0
        if span.page == 1 and idx < 6: w += 0.5
        if re.search(r"\b(abstract|keywords)\b", t, re.I): w += 0.5
        if span.italic: w += 0.2
        return w

    def extract_candidates(self, spans: List[Span]) -> Dict[str, float]:
        """용어 후보 추출 및 점수화"""
        self.log("용어 후보 추출/점수화...")
        counts = Counter()
        weights = defaultdict(float)
        
        for i, sp in enumerate(spans):
            txt = sp.text
            w = self.section_weight(sp, i)

            # 고유·전문 용어 패턴
            for pat in (self.BINOMIAL, self.ABBR, self.CAMEL):
                for m in pat.finditer(txt):
                    term = m.group(0).strip()
                    counts[term] += 1
                    weights[term] += w

            # 모델/숫자-하이픈 용어 가중
            for m in self.MODEL.finditer(txt):
                term = m.group(1)
                if "-" in term or re.search(r"\d", term):
                    counts[term] += 1
                    weights[term] += w * 0.8

            # 일반 소문자 영어 단어
            for m in self.ASCII_LOWER.finditer(txt):
                term = m.group(0)
                if term in self.STOPWORDS: 
                    continue
                counts[term] += 1
                weights[term] += w * 0.6

        if not counts:
            self.log("  - 후보 0개 (문서가 이미지 스캔일 가능성).")
            return {}

        max_c = max(counts.values())
        max_w = max(weights.values()) if weights else 1.0
        scored = {t: 0.6*(counts[t]/max_c) + 0.4*((weights[t]/max_w) if max_w else 0.0)
                  for t in counts}
        scored_sorted = dict(sorted(scored.items(), key=lambda x: x[1], reverse=True))
        self.log(f"  - 후보 {len(scored_sorted)}개 추출 (상위 {self.glossary_top_n} 사용)")
        return scored_sorted

    def guess_type(self, term: str) -> str:
        """용어 타입 추정"""
        if self.BINOMIAL.fullmatch(term) or re.fullmatch(r"[A-Z]\. [a-z]+", term):
            return "species"
        if self.ABBR.fullmatch(term): return "acronym"
        if "-" in term or re.search(r"\d", term): return "model_or_dataset"
        if self.CAMEL.fullmatch(term): return "concept"
        if self.ASCII_LOWER.fullmatch(term): return "common_english"
        return "concept"

    def decide_rule(self, term: str) -> str:
        """표기 규칙 결정"""
        typ = self.guess_type(term)
        if typ == "species": return "original_plus_korean_italic"
        return "original_plus_korean"

    def build_glossary(self, scored: Dict[str, float]) -> List[Dict]:
        """용어시트 생성"""
        chosen = list(scored.keys())[:self.glossary_top_n]
        gloss = [{"term": t, "type": self.guess_type(t), "rule": self.decide_rule(t)} for t in chosen]
        self.log(f"용어시트 생성: {len(gloss)}개")
        return gloss

    def gpt_fill_korean_transliteration(self, glossary: List[Dict]) -> List[Dict]:
        """GPT로 한국어 음독 생성"""
        if not glossary: return glossary
        self.log(f"GPT에 음독(ko) 요청: {len(glossary)}개 용어")
        
        ask = {
            "role":"user",
            "content":(
                "다음 용어들을 한국어 '음독'(발음대로 표기)으로 제안해 주세요. "
                "반드시 JSON 배열 형식으로 [{\"term\":\"...\",\"ko\":\"...\"}, ...] 만 출력하세요.\n\n"
                + json.dumps([g['term'] for g in glossary], ensure_ascii=False)
            )
        }
        
        try:
            resp = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role":"system","content":"당신은 과학 논문 편집자를 돕는 한국어 음독 변환기입니다."}, 
                    ask
                ],
                temperature=0.2,
                max_tokens=2500
            )
            text = resp.choices[0].message.content.strip()
            arr = json.loads(text)
            ko_map = {d.get("term",""): d.get("ko","") for d in arr if isinstance(d, dict)}
            applied = 0
            for g in glossary:
                val = ko_map.get(g["term"], "")
                if val:
                    g["ko"] = val
                    applied += 1
            self.log(f"  - 음독 적용 {applied}/{len(glossary)}개")
        except Exception as e:
            self.log(f"  - 음독 JSON 파싱 실패: {e} (ko 필드 비움)")
            for g in glossary:
                g.setdefault("ko","")
        return glossary

    def build_page_chunks(self, spans: List[Span]) -> List[Tuple[str, List[int]]]:
        """페이지별 청크 생성"""
        pages = defaultdict(list)
        for s in spans:
            pages[s.page].append(s.text)
        ordered_pages = [(p, "".join(pages[p])) for p in sorted(pages.keys())]

        chunks: List[Tuple[str, List[int]]] = []
        cur_text, cur_pages, cur_len = [], [], 0
        for p, txt in ordered_pages:
            if cur_len + len(txt) > self.max_input_chars and cur_text:
                chunks.append(("\n".join(cur_text), cur_pages[:]))
                cur_text, cur_pages, cur_len = [], [], 0
            cur_text.append(f"[Page {p}]\n{txt}")
            cur_pages.append(p)
            cur_len += len(txt)
        if cur_text:
            chunks.append(("\n".join(cur_text), cur_pages))
        return chunks

    def translate_with_rules(self, spans: List[Span], glossary: List[Dict]) -> str:
        """규칙 기반 번역 수행"""
        chunks = self.build_page_chunks(spans)
        gjson = json.dumps(glossary, ensure_ascii=False)
        outputs = []
        N = len(chunks)
        self.log(f"번역 시작: 청크 {N}개 (MAX_OUTPUT_TOKENS={self.max_output_tokens})")

        for idx, (chunk_text, pages) in enumerate(chunks, 1):
            label = f"[{idx}/{N}] pages={pages}"
            self.log(f"{label} 전송 중... (chars={len(chunk_text)})")
            
            user_msg = {
                "role":"user",
                "content":(
                    f"용어시트(JSON):\n{gjson}\n\n"
                    f"아래 원문을 규칙에 맞춰 **완전 번역**하세요. 요약/생략/누락 금지.\n"
                    f"모든 해당 단어를 '원문(한국어 음독)'으로 **매번** 표기하세요. 예: application → application(어플리케이션)\n"
                    f"이 청크는 원문의 페이지 {pages}에 해당합니다.\n\n"
                    f"{chunk_text}"
                )
            }
            
            for attempt in range(3):
                try:
                    resp = self.client.chat.completions.create(
                        model=self.model_name,
                        messages=[{"role":"system","content":self.SYS_RULES}, user_msg],
                        temperature=0.2,
                        max_tokens=self.max_output_tokens
                    )
                    out = resp.choices[0].message.content.strip()
                    if not out:
                        raise RuntimeError("빈 응답")
                    outputs.append(out)
                    self.log(f"{label} 완료 (out_chars={len(out)})")
                    break
                except Exception as e:
                    self.log(f"{label} 실패(시도 {attempt+1}/3): {e}")
                    if attempt == 2:
                        raise
                    time.sleep(1.2 * (attempt+1))
        
        return "\n\n".join(outputs)

    def translate_pdf(self, pdf_file, generate_ko=True):
        """PDF 번역 메인 함수"""
        try:
            # PDF 파싱
            spans = self.parse_pdf_with_italics(pdf_file)
            full_text = "".join(s.text for s in spans)
            if not full_text.strip():
                raise RuntimeError("PDF에서 텍스트를 추출하지 못했습니다. (스캔본이면 OCR 선행 필요)")

            # 용어 후보 추출 및 용어시트 생성
            scored = self.extract_candidates(spans)
            glossary = self.build_glossary(scored)

            # 한국어 음독 생성
            if generate_ko and glossary:
                glossary = self.gpt_fill_korean_transliteration(glossary)

            # 번역 수행
            translated = self.translate_with_rules(spans, glossary)

            return {
                'success': True,
                'translated_text': translated,
                'glossary': glossary,
                'message': '번역이 완료되었습니다.'
            }

        except Exception as e:
            return {
                'success': False,
                'error': str(e),
                'message': f'번역 중 오류가 발생했습니다: {str(e)}'
            }

