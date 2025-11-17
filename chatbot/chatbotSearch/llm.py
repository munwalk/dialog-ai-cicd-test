"""
HyperCLOVA X API 호출
"""
import requests
import uuid
import logging
from datetime import datetime
from .config import CLOVA_STUDIO_URL, CLOVA_API_KEY

logger = logging.getLogger(__name__)

def call_hyperclova_rag(user_query: str, lambda_result: str):
    """Lambda 검색 결과를 바탕으로 HyperCLOVA X RAG 답변 생성"""
    import requests
    import uuid
    import traceback
    from datetime import datetime
    
    # 오늘 날짜 동적 생성
    today = datetime.now()
    today_str = today.strftime('%Y년 %m월 %d일')
    today_iso = today.strftime('%Y-%m-%d')
    
    system_prompt = f"""🚨 회의록 검색 챗봇

    ## 오늘: {today_str} ({today_iso})

    ## 규칙

    ### 여러 회의 (2개+):
    네, [조건] 회의들이 있어요! 📋

    1️⃣ [제목] ([날짜])
    - [15자 이내 요약]

    2️⃣ [제목] ([날짜])
    - [15자 이내 요약]

    번호를 말씀해주세요! (예: 1, 2) 😊

    ❌ 금지: 상세 설명, 📌📅📝💡 이모지, 2문장 이상

    ### 단일 회의 (1개):
    네, [주제] 회의가 있었어요! 📌

    📌 [제목]
    📅 날짜: YYYY년 MM월 DD일

    📝 회의 설명:
    [2-3문장 자세히] 했어요

    💡 핵심 내용:
    [2-3문장 자세히] 했습니다

    ## 시제
    - 날짜 < {today_iso} → 과거형
    - 날짜 >= {today_iso} → 미래형

    ## 예시

    ### 여러 회의:
    네, 이번주 완료된 회의로는 다음이 있어요! 📋

    1️⃣ 디자인 시스템 구축 회의 (10월 20일)
    - 디자인 시스템 방안 논의

    2️⃣ 개발팀 스프린트 회의 (10월 22일)
    - 목표와 작업 배분

    번호를 말씀해주세요! 😊

    ### 단일 회의:
    네, 디자인 시스템 구축 회의가 있었어요! 📌

    📌 디자인 시스템 구축 회의
    📅 날짜: 2025년 10월 20일

    📝 회의 설명:
    통합 디자인 시스템 구축 방안을 논의했습니다. 컴포넌트와 패턴을 정의하고 가이드를 작성하기로 결정했어요.

    💡 핵심 내용:
    컴포넌트 라이브러리와 디자인 토큰 표준화를 진행하기로 했습니다. 효율적인 관리 툴과 프로세스도 검토했답니다!

    ## 금지
    ❌ 여러 회의인데 상세 설명
    ❌ 단일 회의 5문장 미만
    ❌ 정보 누락
    ❌ 잘못된 시제
    
    ## ⚠️ 중요: 검색 결과 준수
    - 검색 결과에 없는 회의, 날짜, 내용을 절대 만들어내지 마세요
    - 반드시 제공된 검색 결과의 정보만 사용하세요
    - 날짜는 검색 결과에 표시된 그대로만 사용하세요
    """.strip()

    user_message = f"""다음은 회의록 검색 결과입니다:

{lambda_result}

사용자 질문: {user_query}

**🚨 중요 규칙:**
1. 오늘 날짜는 {today_str} ({today_iso})입니다.
2. **검색 결과에 표시된 회의, 날짜, 내용만 사용하세요.**
3. **검색 결과에 없는 정보를 절대 만들어내지 마세요.**
4. 날짜는 검색 결과에 나온 그대로만 사용하세요.

검색 결과에 여러 회의가 있는지 확인하고, 사용자 질문 유형에 맞게 답변하세요:
- "뭐가 있어?" / "어떤 회의?" → 모든 회의 나열
- "특정 주제" → 최신 1개 상세히
- "날짜 범위" → 해당 기간 모두 나열

검색 결과 개수에 따라:
- 2개 이상: 간단 목록 형식
- 1개: 상세 설명 형식

위 형식에 맞춰 답변해주세요."""

    studio_request = {
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "topP": 0.8,
        "topK": 0,
        "maxTokens": 500,
        "temperature": 0.3,
        "repeatPenalty": 1.2,
        "stopBefore": [],
        "includeAiFilters": True
    }
    
    headers = {
        'Authorization': f'Bearer {CLOVA_API_KEY}',
        'Content-Type': 'application/json',
        'X-NCP-CLOVASTUDIO-REQUEST-ID': str(uuid.uuid4())
    }
    
    try:
        print(f"[DEBUG] HyperCLOVA X 호출 중...")
        print(f"[DEBUG] 오늘 날짜: {today_str} ({today_iso})")
        response = requests.post(
            CLOVA_STUDIO_URL,
            headers={
                'Authorization': f'Bearer {CLOVA_API_KEY}',
                'Content-Type': 'application/json',
                'X-NCP-CLOVASTUDIO-REQUEST-ID': str(uuid.uuid4())
            },
            json=studio_request,
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ HyperCLOVA X 오류: {response.status_code}")
            print(f"응답: {response.text[:500]}")
            response.raise_for_status()
        
        data = response.json()
        answer = data.get('result', {}).get('message', {}).get('content', '')
        
        if not answer:
            print(f"⚠️ 응답 생성 실패 (빈 답변)")
            return None
        
        print(f"✅ RAG 답변 생성 성공: {len(answer)}자")
        return answer
    
    except requests.exceptions.HTTPError as e:
        print(f"❌ HTTP 오류: {e}")
        print(traceback.format_exc())
        return None
    
    except requests.exceptions.Timeout:
        print(f"❌ 타임아웃 (30초 초과)")
        return None
    
    except Exception as e:
        print(f"❌ RAG 생성 오류: {e}")
        print(traceback.format_exc())
        return None
    
# ================== HyperCLOVA X 호출 (일반 대화) ==================
def call_hyperclova(user_query):
    """오프토픽 안내 메시지"""
    print(f"\n🚫 [오프토픽] 회의록 검색 전용 챗봇 안내")
    
    off_topic_message = """죄송해요, 저는 회의록 검색 전용 챗봇이에요! 🗂️

다음과 같은 질문만 도와드릴 수 있어요:

✅ "마케팅 회의 있었어?"
✅ "이번주 기획 회의록 찾아줘"
✅ "디자인 논의 내용 알려줘"
✅ "최근 개발 미팅 정리해줘"

회의록 검색이 필요하시면 "회의", "미팅", "회의록" 같은 단어와 함께 질문해주세요! 😊"""
    
    print(f"✅ 오프토픽 안내 메시지 반환")
    return off_topic_message


def parse_query_intent(user_query: str) -> dict:
    """
    HyperCLOVA X로 사용자 질문 의도 파악
    
    반환:
    {
        'intent': 'search_meetings' | 'count_meetings' | 'off_topic',
        'keywords': [...],
        'date_range': str or None,
        'status': 'COMPLETED' | 'SCHEDULED' | None
    }
    """
    try:
        system_prompt = """당신은 회의록 검색 시스템의 질문 분석 전문가입니다.
            사용자의 질문을 분석해서 다음 정보를 추출하세요:

            1. intent: 질문 유형
            - "search_meetings": 회의 검색
            - "count_meetings": 회의 개수/횟수 질문  
            - "off_topic": 회의와 관련 없는 질문

            2. keywords: 검색 키워드 리스트 (명사만, 불용어 제외)
            - 불용어: 회의, 미팅, 알려줘, 보여줘, 찾아줘, 있어, 뭐, 거, 이번주, 지난주, 오늘, 어제, 줘, 아줘, 해줘  # ← 추가!

            3. date_range: 날짜 표현
            - "오늘", "어제", "이번주", "지난주", "최근", "10월", "10월 20일" 등
            - 없으면 null

            4. status: 회의 상태 (매우 중요!)
            - "COMPLETED": 과거형
                * 어미: ~했어, ~한, ~있었어, ~였어, ~된, ~됐어
                * 오타: "회의함" → "회의한" (과거)
            - "SCHEDULED": 미래형
                * 어미: ~할, ~있을, ~될, ~예정
            - null: 명시 안 됨

            🚨 오타 처리 규칙:
            - "회의함 거" → "회의한 거" (과거형)
            - "미팅 했던거" → "미팅 했던 거" (과거형)
            - "회의할거" → "회의할 거" (미래형)
            - "회의 ㅈ아줘" → "회의 찾아줘" → keywords=[] (불용어)

            반드시 JSON 형식으로만 답변하세요. 설명 없이 JSON만 출력하세요.

            예시:
            질문: "이번주 회의함 거 뭐있어?"
            JSON: {"intent": "search_meetings", "keywords": [], "date_range": "이번주", "status": "COMPLETED"}

            질문: "회의한 거 보여줘"
            JSON: {"intent": "search_meetings", "keywords": [], "date_range": null, "status": "COMPLETED"}

            질문: "다음주 회의 있을까?"
            JSON: {"intent": "search_meetings", "keywords": [], "date_range": "다음주", "status": "SCHEDULED"}

            질문: "회의 ㅈ아줘"
            JSON: {"intent": "search_meetings", "keywords": [], "date_range": null, "status": null}"""
        user_prompt = f"""질문: {user_query}

        JSON:"""

        response = requests.post(
            CLOVA_STUDIO_URL,
            headers={
                'Authorization': f'Bearer {CLOVA_API_KEY}',
                'Content-Type': 'application/json',
                'X-NCP-CLOVASTUDIO-REQUEST-ID': str(uuid.uuid4())
            },
            json={
                'messages': [
                    {'role': 'system', 'content': system_prompt},
                    {'role': 'user', 'content': user_prompt}
                ],
                'topP': 0.6,
                'topK': 0,
                'maxTokens': 500,
                'temperature': 0.1,
                'repeatPenalty': 1.2,
                'stopBefore': [],
                'includeAiFilters': True
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['result']['message']['content']
            
            # JSON 파싱
            import json
            # ```json 제거
            content = content.replace('```json', '').replace('```', '').strip()
            parsed = json.loads(content)
            
            print(f"[DEBUG] LLM 의도 파악 결과: {parsed}")
            return parsed
        else:
            print(f"[ERROR] LLM 호출 실패: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"[ERROR] LLM 의도 파악 실패: {e}")
        return None
    
def preprocess_query_with_llm(user_query: str, context: dict = None) -> dict:
    """
    사용자 질문 전처리 (오타 보정 + 의도 파악)
    """
    context_info = ""
    if context and context.get('state') == 'meeting_selected':
        meeting_title = context.get('meeting_title', '알 수 없는 회의')
        context_info = f"\n현재 선택된 회의: {meeting_title}"
    
    prompt = f"""사용자 질문을 분석하여 JSON으로 답변하세요.

사용자 질문: "{user_query}"{context_info}

분석할 내용:
1. corrected_query: 오타를 수정한 질문 (오타 없으면 원본 그대로)
   ⚠️ 중요: "저회의", "그회의"는 "저 회의", "그 회의"로 보정 (띄어쓰기 추가)
   ⚠️ 절대 "저희"로 바꾸지 마세요!
2. intent: 질문 의도 (다음 중 하나)
   - "meeting_search": 회의 검색 ("기획 회의", "회의 뭐있어")
   - "task_search": 할일 검색 ("내가 할일", "다른 사람은", "누가 담당")
   - "participant_search": 참석자 검색 ("누가 참석", "누구랑 회의", "회의 멤버")
   - "meeting_detail_rag": 선택된 회의의 상세 질문 ("이 회의 예산은?", "주요 결론은?", "몇 분 진행?")
   - "keyword_search": 키워드 검색 ("'예산' 키워드 있는 회의", "'리팩토링' 포함된 회의")
   - "meeting_select": 선택 ("1", "10월 20일", "디자인")
   - "confirmation": 확인 질문 ("그거야?", "맞아?")
   - "off_topic": 회의와 무관한 질문
3. is_contextual: 이전 회의 정보를 사용해야 하는가? (true/false)
4. scope_expansion: 범위 확장 질문인가? (true/false)
   - "전체적으로", "전부", "모두", "다", "전체에서", "전체적" 등 → true
   - "아니 전체에서" 같은 범위 확장 표현 → true

🎯 의도 구분 가이드:
- "누가 참석했어?" → participant_search (회의 멤버 질문)
- "누구랑 회의했어?" → participant_search (함께한 사람)
- "김철수 회의에 있었어?" → participant_search (특정인 참석 여부)
- "회의 멤버는?" → participant_search (참석자 목록)
- "누가 뭐해?" → task_search (할일/업무)
- "다른 사람은?" → task_search (다른 사람 할일)
- "누가 담당?" → task_search (담당자)
- "이 회의 예산은?" → meeting_detail_rag (선택된 회의 상세)
- "이 회의 몇 분 진행?" → meeting_detail_rag (선택된 회의 시간)
- "회의 분위기는?" → meeting_detail_rag (선택된 회의 내용)
- "'예산' 키워드 있는 회의?" → keyword_search (회의 검색, 선택 아님)
- "회의 있었어?" → meeting_search (새로운 검색, 컨텍스트 무시)
- "회의 뭐있어?" → meeting_search (새로운 검색)

예시:
질문: "누가 참석했어?"
{{
    "corrected_query": "누가 참석했어?",
    "intent": "participant_search",
    "is_contextual": true,
    "scope_expansion": false,
    "key_entities": ["참석"]
}}

질문: "거기서 누가 뭐해?"
{{
    "corrected_query": "거기서 누가 뭐해?",
    "intent": "task_search",
    "is_contextual": true,
    "scope_expansion": false,
    "key_entities": ["할일"]
}}

질문: "전체적으로는?"
현재 컨텍스트: 채용 전략 회의
{{
    "corrected_query": "전체적으로는?",
    "intent": "task_search",
    "is_contextual": false,
    "scope_expansion": true,
    "key_entities": ["전체"]
}}
질문: "아니 전체에서 내 할일"
현재 컨텍스트: 개발팀 스프린트 회의
{{
    "corrected_query": "아니 전체에서 내 할일",
    "intent": "task_search",
    "is_contextual": false,
    "scope_expansion": true,
    "key_entities": ["전체", "할일"]
}}

질문: "누가 참석했어?"
현재 컨텍스트: 채용 전략 회의
{{
    "corrected_query": "누가 참석했어?",
    "intent": "participant_search",
    "is_contextual": true,
    "scope_expansion": false,
    "key_entities": ["참석"]
}}"""

    try:
        response = call_hyperclova_simple(prompt)
        # JSON 추출 (혹시 마크다운으로 감싸져 있을 수 있음)
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            import json
            return json.loads(json_match.group())
        else:
            # 파싱 실패 시 기본값
            return {
                "corrected_query": user_query,
                "intent": "meeting_search",
                "is_contextual": False,
                "key_entities": []
            }
    except Exception as e:
        print(f"[LLM 전처리 실패] {e}")
        return {
            "corrected_query": user_query,
            "intent": "meeting_search",
            "is_contextual": False,
            "key_entities": []
        }
    
def call_hyperclova_simple(prompt: str) -> str:
    """
    간단한 HyperCLOVA X 호출 (시스템 프롬프트 없이)
    """
    try:
        response = requests.post(
            CLOVA_STUDIO_URL,
            headers={
                'Authorization': f'Bearer {CLOVA_API_KEY}',
                'Content-Type': 'application/json',
                'X-NCP-CLOVASTUDIO-REQUEST-ID': str(uuid.uuid4())
            },
            json={
                'messages': [
                    {'role': 'user', 'content': prompt}
                ],
                'topP': 0.6,
                'topK': 0,
                'maxTokens': 500,
                'temperature': 0.1,
                'repeatPenalty': 1.2,
                'stopBefore': [],
                'includeAiFilters': True
            },
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result['result']['message']['content']
            return content
        else:
            print(f"[ERROR] LLM 호출 실패: {response.status_code}")
            return ""
            
    except Exception as e:
        print(f"[ERROR] LLM 호출 실패: {e}")
        return ""
    
def answer_meeting_question(meeting_content: dict, question: str) -> str:
    """
    회의록 내용 기반 질의응답 (RAG)
    
    Args:
        meeting_content: 회의 정보 (title, summary, description 등)
        question: 사용자 질문
    
    Returns:
        답변
    """
    from datetime import datetime
    
    # 날짜 포맷팅
    scheduled_at = meeting_content.get('scheduled_at', '알 수 없음')
    if isinstance(scheduled_at, datetime):
        scheduled_at = scheduled_at.strftime('%Y년 %m월 %d일')
    
    prompt = f"""다음은 회의록 정보입니다:

📌 회의 제목: {meeting_content.get('title', '알 수 없음')}
📅 날짜: {scheduled_at}

📝 회의 설명:
{meeting_content.get('description', '정보 없음')}

💡 회의 요약:
{meeting_content.get('summary', '정보 없음')}

🗣️ 실시간 발화 내용:
{meeting_content.get('transcript_text', '발화 기록 없음')}

질문: {question}

위 회의록 내용을 바탕으로 질문에 답변해주세요.

**규칙:**
1. 답변은 2-3문장으로 간결하게
2. 회의록에 명시된 내용만 답변
3. 회의록에 없는 내용은 "회의록에서 해당 정보를 찾을 수 없어요 😢"
4. 자연스럽고 친근한 말투 (존댓말)
5. 숫자나 금액이 있으면 정확하게 표기
"""
    
    try:
        response = call_hyperclova_simple(prompt)
        return response.strip()
    
    except Exception as e:
        logger.error(f"RAG 답변 생성 실패: {e}")
        import traceback
        traceback.print_exc()
        return "죄송해요, 답변 생성 중 오류가 발생했어요. 😢"