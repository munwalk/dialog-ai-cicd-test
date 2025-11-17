"""
컨텍스트 기반 선택 처리
- 번호 선택
- 날짜 선택
- 키워드 선택
"""
import re
import logging
from datetime import datetime
from .models import ChatRequest, ChatResponse
from .formatting import format_single_meeting, format_single_meeting_with_persona
from .context import save_context, delete_context
from .config import ENABLE_PERSONA

logger = logging.getLogger(__name__)

# ============================================================
# 선택 처리
# ============================================================

def handle_selection(user_input: str, context: dict, 
                    request: ChatRequest, session_id: str) -> ChatResponse:
    """사용자가 회의를 선택했을 때 처리 (번호, 제목, 날짜, 키워드)"""
    
    meetings = context.get('meetings', [])
    if not meetings:
        return ChatResponse(
            answer="선택할 회의가 없어요. 다시 검색해주세요! 😊",
            history=request.history,
            source="no_meetings",
            session_id=session_id
        )
    
    user_input_lower = user_input.lower().strip()
    selected_meeting = None
    selection_method = None
    matched_meetings = []
    
    # 1. 숫자로 선택 (예: "2", "2번")
    number_match = re.search(r'(\d+)', user_input)
    if number_match:
        selection = int(number_match.group(1))
        if 1 <= selection <= len(meetings):
            selected_meeting = meetings[selection - 1]
            selection_method = f"{selection}번"
            print(f"[DEBUG] 번호 선택: {selection}번")
    
    # 2. 날짜로 선택 (예: "10월 20일", "20일", "20일꺼")
    if not selected_meeting:
        # "X월 Y일" 패턴
        date_match = re.search(r'(\d{1,2})월\s*(\d{1,2})일', user_input)
        if date_match:
            month = int(date_match.group(1))
            day = int(date_match.group(2))
            
            # 해당 날짜의 모든 회의 찾기
            matched_meetings = []
            for i, meeting in enumerate(meetings):
                scheduled_at = meeting.get('scheduled_at')
                if isinstance(scheduled_at, str):
                    scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                
                if scheduled_at and scheduled_at.month == month and scheduled_at.day == day:
                    matched_meetings.append((i, meeting))
            
            # 매칭 결과 처리
            if len(matched_meetings) == 1:
                # 1개만 매칭 → 바로 선택
                selected_meeting = matched_meetings[0][1]
                selection_method = f"{month}월 {day}일"
                print(f"[DEBUG] 날짜 선택: {month}월 {day}일 (1개 매칭)")
            elif len(matched_meetings) > 1:
                # 여러 개 매칭 → 연도가 다른 경우!
                print(f"[DEBUG] 날짜 선택: {month}월 {day}일 (여러 개 매칭: {len(matched_meetings)}개)")
                
                response_msg = f"{month}월 {day}일에 회의가 {len(matched_meetings)}개 있어요! 🗓️\n"
                response_msg += "연도가 다른 것 같아요. 확인해주세요!\n\n"
                
                for idx, (original_idx, meeting) in enumerate(matched_meetings, 1):
                    title = meeting.get('title', '제목 없음')
                    scheduled_at = meeting.get('scheduled_at')
                    if isinstance(scheduled_at, str):
                        scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    
                    date_str = scheduled_at.strftime('%Y년 %m월 %d일') if scheduled_at else '날짜 정보 없음'
                    description = meeting.get('description', '')
                    if len(description) > 40:
                        description = description[:40] + "..."
                    
                    emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'][idx - 1] if idx <= 10 else f"{idx}️⃣"
                    response_msg += f"{emoji} {title} ({date_str})\n"
                    response_msg += f"   - {description}\n\n"
                
                response_msg += "어떤 회의를 보시겠어요?\n"
                response_msg += "예: 번호(1, 2), 연도 포함 날짜(2025년 10월 20일) 😊"
                
                # 매칭된 회의들만 컨텍스트에 저장 (다시 선택하도록)
                matched_meetings_list = [m for _, m in matched_meetings]
                context_data = {
                    'state': 'awaiting_selection',
                    'meetings': matched_meetings_list,
                    'original_query': user_input
                }
                save_context(session_id, context_data)
                
                return ChatResponse(
                    answer=response_msg,
                    history=request.history + [
                        {"role": "user", "content": user_input},
                        {"role": "assistant", "content": response_msg}
                    ],
                    source="multiple_date_matches",
                    session_id=session_id
                )
        
        # "X일" 패턴 (예: "20일", "20일꺼")
        if not selected_meeting:
            day_match = re.search(r'(\d{1,2})일', user_input)
            if day_match:
                day = int(day_match.group(1))
                
                # 해당 날짜의 모든 회의 찾기
                matched_meetings = []
                for i, meeting in enumerate(meetings):
                    scheduled_at = meeting.get('scheduled_at')
                    if isinstance(scheduled_at, str):
                        scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                    
                    if scheduled_at and scheduled_at.day == day:
                        matched_meetings.append((i, meeting))
                
                # 매칭 결과 처리
                if len(matched_meetings) == 1:
                    # 1개만 매칭 → 바로 선택
                    selected_meeting = matched_meetings[0][1]
                    selection_method = f"{day}일"
                    print(f"[DEBUG] 날짜 선택: {day}일 (1개 매칭)")
                elif len(matched_meetings) > 1:
                    # 여러 개 매칭 → 목록 보여주고 다시 선택
                    print(f"[DEBUG] 날짜 선택: {day}일 (여러 개 매칭: {len(matched_meetings)}개)")
                    
                    response_msg = f"{day}일에 회의가 {len(matched_meetings)}개 있어요! 🗓️\n\n"
                    
                    for idx, (original_idx, meeting) in enumerate(matched_meetings, 1):
                        title = meeting.get('title', '제목 없음')
                        scheduled_at = meeting.get('scheduled_at')
                        if isinstance(scheduled_at, str):
                            scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                        
                        date_str = scheduled_at.strftime('%Y년 %m월 %d일') if scheduled_at else '날짜 정보 없음'
                        description = meeting.get('description', '')
                        if len(description) > 40:
                            description = description[:40] + "..."
                        
                        emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'][idx - 1] if idx <= 10 else f"{idx}️⃣"
                        response_msg += f"{emoji} {title} ({date_str})\n"
                        response_msg += f"   - {description}\n\n"
                    
                    response_msg += "어떤 회의를 보시겠어요?\n"
                    response_msg += "예: 번호(1, 2), 월 포함 날짜(10월 20일) 😊"
                    
                    # 매칭된 회의들만 컨텍스트에 저장 (다시 선택하도록)
                    matched_meetings_list = [m for _, m in matched_meetings]
                    context_data = {
                        'state': 'awaiting_selection',
                        'meetings': matched_meetings_list,
                        'original_query': user_input
                    }
                    save_context(session_id, context_data)
                    
                    return ChatResponse(
                        answer=response_msg,
                        history=request.history + [
                            {"role": "user", "content": user_input},
                            {"role": "assistant", "content": response_msg}
                        ],
                        source="multiple_date_matches",
                        session_id=session_id
                    )
    
# 3. 제목/키워드로 선택 (예: "디자인", "디자인 시스템", "AI회의")
    if not selected_meeting:
        # 회의 제목과의 유사도 계산
        matched_meetings = []  # (meeting, score) 튜플 리스트
        user_input_lower = user_input.lower().strip()
        
        # ========== 검색 유도 불용어 체크: '선택'이 아닌 '검색'으로 빠지게 유도 ==========<br>
        search_stopwords = ['최근', '이번주', '지난주', '회의', '미팅', '뭐', '어떤', '있어', '있었어', '있나', '찾아', '검색', '더', '나머지']
        
        # 사용자 입력의 토큰 중 검색 유도 단어의 비율이 높으면 선택 매칭을 스킵
        tokens = user_input_lower.split()
        search_word_count = len([t for t in tokens if t in search_stopwords])
        
        # 검색 유도 단어가 60% 이상을 차지하면 선택 로직 스킵 (선택 시도 중단)
        if tokens and search_word_count / len(tokens) > 0.6:
            print(f"[DEBUG] 키워드 선택 스킵: 검색 유도 단어가 대부분 ({search_word_count}/{len(tokens)})")
            pass # matched_meetings가 빈 상태로 아래로 내려가 'invalid_selection'이 됨
        
        # 기존 키워드 매칭 로직 시작
        else:
            for i, meeting in enumerate(meetings):
                title = meeting.get('title', '').lower()
                description = meeting.get('description', '').lower()
                score = 0
                
                # 정확히 일치하는 경우
                if user_input_lower in title:
                    score = len(user_input_lower) / len(title)
                # description에서 일치
                elif user_input_lower in description:
                    score = len(user_input_lower) / len(description) * 0.8
                # 토큰 단위 매칭 (한글 + 영문/숫자)
                else:
                    # 한글 토큰
                    korean_tokens = re.findall(r'[가-힣]+', user_input_lower)
                    # 영문/숫자 토큰
                    english_tokens = re.findall(r'[a-z0-9]+', user_input_lower)
                    
                    all_tokens = korean_tokens + english_tokens
                    # 불용어 제거
                    meaningful_tokens = [t for t in all_tokens if len(t) >= 2 and t not in ['회의', '알려', '알려줘', '보여', '보여줘']]
                    
                    if meaningful_tokens:
                        match_count = sum(1 for token in meaningful_tokens if token in title or token in description)
                        if match_count > 0:
                            score = match_count / len(meaningful_tokens) * 0.7
                
                # 적당한 매칭 점수면 추가 (임계값 낮춤: 0.3 → 0.15)
                if score > 0.15:
                    matched_meetings.append((meeting, score))
        
        # 매칭 결과 처리
        if len(matched_meetings) == 0:
            # 매칭 없음
            pass  # 아래 invalid_selection으로
        elif len(matched_meetings) == 1:
            # 1개만 → 바로 선택
            selected_meeting = matched_meetings[0][0]
            selection_method = "키워드"
            print(f"[DEBUG] 키워드 선택: '{user_input}' (점수: {matched_meetings[0][1]:.2f}, 1개 매칭)")
            
        else: # <--- [수정] matched_meetings > 1 인 경우만 실행
            # 여러 개 → 점수 순 정렬 후 목록 표시
            matched_meetings.sort(key=lambda x: x[1], reverse=True)
            print(f"[DEBUG] 키워드 선택: '{user_input}' (여러 개 매칭: {len(matched_meetings)}개)")
            
            response_msg = f"'{user_input}' 관련 회의가 {len(matched_meetings)}개 있어요! 📋\n\n"
            
            for idx, (meeting, score) in enumerate(matched_meetings[:10], 1):  # 최대 10개
                title = meeting.get('title', '제목 없음')
                scheduled_at = meeting.get('scheduled_at')
                if isinstance(scheduled_at, str):
                    scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
                
                date_str = scheduled_at.strftime('%Y년 %m월 %d일') if scheduled_at else '날짜 정보 없음'
                description = meeting.get('description', '')
                if len(description) > 40:
                    description = description[:40] + "..."
                
                emoji = ['1️⃣', '2️⃣', '3️⃣', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'][idx - 1] if idx <= 10 else f"{idx}️⃣"
                response_msg += f"{emoji} {title} ({date_str})\n"
                response_msg += f"   - {description}\n\n"
            
            if len(matched_meetings) > 10:
                response_msg += f"💡 나머지 {len(matched_meetings) - 10}개 회의도 있어요!\n\n"
            
            response_msg += "어떤 회의를 보시겠어요?\n"
            response_msg += "예: 번호(1, 2), 날짜(10월 20일) 😊"
            
            # 매칭된 회의들만 컨텍스트에 저장 (다시 선택하도록)
            matched_meetings_list = [m for m, _ in matched_meetings[:10]]
            context_data = {
                'state': 'awaiting_selection',
                'meetings': matched_meetings_list,
                'original_query': user_input
            }
            save_context(session_id, context_data)
            
            return ChatResponse(
                answer=response_msg,
                history=request.history + [
                    {"role": "user", "content": user_input},
                    {"role": "assistant", "content": response_msg}
                ],
                source="multiple_keyword_matches",
                session_id=session_id
            )
    
    # 선택된 회의가 없으면 안내 메시지
    if not selected_meeting:
        return ChatResponse(
            answer=f"'{user_input}'로는 회의를 찾을 수 없어요. 😅\n\n번호(예: 1, 2), 날짜(예: 10월 20일, 20일), 또는 회의 제목으로 선택해주세요!",
            history=request.history,
            source="invalid_selection",
            session_id=session_id
        )
    
    # 선택된 회의 정보 포맷
    print(f"[DEBUG] 선택 완료 ({selection_method}): {selected_meeting['title']}")
    
    # ========== Phase 2-A: 페르소나 템플릿 적용 ==========
    user_job_raw = getattr(request, 'job', 'NONE')
    
    # 정규화 (대문자 변환)
    user_job = user_job_raw.upper()

    # 유효한 직무만 허용
    valid_jobs = ['NONE', 'PROJECT_MANAGER', 'FRONTEND_DEVELOPER', 
                'BACKEND_DEVELOPER', 'DATABASE_ADMINISTRATOR', 'SECURITY_DEVELOPER']
    if user_job not in valid_jobs:
        user_job = 'NONE'

    print(f"[DEBUG] Phase 2-A: user_job (원본: {user_job_raw}, 정규화: {user_job})")

    if ENABLE_PERSONA and user_job != 'NONE':
        meeting_info = format_single_meeting_with_persona(selected_meeting, user_job)
        print(f"[DEBUG] Phase 2-A: {user_job}용 템플릿 적용 (선택)")
    else:
        meeting_info = format_single_meeting(selected_meeting)
        print(f"[DEBUG] 기본 템플릿 적용 (선택)")
        
    # 선택 완료 후 - 컨텍스트 업데이트 (삭제 대신)
    new_context = {
        'state': 'meeting_selected',
        'selected_meeting_id': selected_meeting['id'],
        'meeting_title': selected_meeting.get('title', ''),  # ← 추가!
        'selected_meeting': selected_meeting
    }
    save_context(session_id, new_context)
    
    return ChatResponse(
        answer=meeting_info,
        history=request.history + [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": meeting_info}
        ],
        source="selected_meeting",
        session_id=session_id
    )