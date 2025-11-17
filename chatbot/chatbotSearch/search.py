"""
회의록 검색 로직 전체
- 날짜 파싱
- 상태 파싱  
- 키워드 추출
- 오프토픽 체크
- MySQL 직접 검색
- Phase 2-A: 페르소나 검색
"""
import re
import logging
import mysql.connector
from datetime import datetime, timedelta
from .database import get_db_connection
from .config import ENABLE_PERSONA
from .formatting import format_single_meeting, format_single_meeting_with_persona, format_my_tasks, format_meeting_tasks, format_assignee_tasks

logger = logging.getLogger(__name__)

# ============================================================
# 조사 처리 함수
# ============================================================
def get_location_josa(date_str):
    """날짜 표현에 맞는 위치 조사 반환"""
    if not date_str:
        return date_str
    
    # "은" 사용 (오늘, 어제, 내일, 모레)
    if any(x in date_str for x in ['오늘', '어제', '내일', '모레']):
        return f"{date_str}은"
    
    # "에는" 사용 (나머지: 이번주, 이번달, 10월, 10월 20일 등)
    else:
        return f"{date_str}에는"
    
# ============================================================
# 날짜 파싱
# ============================================================

def parse_date_from_query(query: str) -> dict:
    """
    쿼리에서 날짜 정보 추출
    
    반환:
    {
        'type': 'relative' | 'absolute' | 'range' | None,
        'start_date': datetime | None,
        'end_date': datetime | None,
        'original': str  # 원본 날짜 표현
    }
    """
    result = {
        'type': None,
        'start_date': None,
        'end_date': None,
        'original': None
    }
    
    today = datetime.now()
    
    # ========== 1. 범위 패턴 (최우선!) ==========
    # "N월 N일부터 ~ 까지" 범위 패턴
    range_patterns = [
        r'(\d{1,2})월\s*(\d{1,2})일\s*부터\s*(\d{1,2})월\s*(\d{1,2})일',
        r'(\d{1,2})월\s*(\d{1,2})일\s*부터\s*오늘(?:까지)?',
        r'(\d{1,2})월\s*(\d{1,2})일\s*[-~]\s*(\d{1,2})월\s*(\d{1,2})일',
        r'(\d{1,2})월\s*(\d{1,2})일\s*[-~]\s*오늘',
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, query)
        if match:
            groups = match.groups()
            
            # "N월 N일부터 오늘" 패턴
            if '오늘' in match.group(0):
                start_month = int(groups[0])
                start_day = int(groups[1])
                year = today.year
                
                try:
                    start_date = datetime(year, start_month, start_day, 0, 0, 0)
                    end_date = today.replace(hour=23, minute=59, second=59)
                    
                    result['type'] = 'range'
                    result['start_date'] = start_date
                    result['end_date'] = end_date
                    result['original'] = f'{start_month}월 {start_day}일부터 오늘'
                    return result
                except ValueError:
                    pass
            else:
                # "N월 N일부터 M월 M일" 패턴
                start_month, start_day, end_month, end_day = map(int, groups)
                year = today.year
                
                try:
                    start_date = datetime(year, start_month, start_day, 0, 0, 0)
                    end_date = datetime(year, end_month, end_day, 23, 59, 59)
                    
                    result['type'] = 'range'
                    result['start_date'] = start_date
                    result['end_date'] = end_date
                    result['original'] = f'{start_month}월 {start_day}일부터 {end_month}월 {end_day}일'
                    return result
                except ValueError:
                    pass
    
    # ========== 2. 상대적 날짜 ==========
    # "오늘"
    if '오늘' in query:
        result['type'] = 'relative'
        result['start_date'] = today.replace(hour=0, minute=0, second=0)
        result['end_date'] = today.replace(hour=23, minute=59, second=59)
        result['original'] = '오늘'
        return result
    
    # "어제"
    if '어제' in query:
        yesterday = today - timedelta(days=1)
        result['type'] = 'relative'
        result['start_date'] = yesterday.replace(hour=0, minute=0, second=0)
        result['end_date'] = yesterday.replace(hour=23, minute=59, second=59)
        result['original'] = '어제'
        return result
    
    # "이번주"
    if '이번주' in query or '이번 주' in query:
        start_of_week = today - timedelta(days=today.weekday())
        end_of_week = start_of_week + timedelta(days=6)
        result['type'] = 'relative'
        result['start_date'] = start_of_week.replace(hour=0, minute=0, second=0)
        result['end_date'] = end_of_week.replace(hour=23, minute=59, second=59)
        result['original'] = '이번주'
        return result
    
    # "지난주"
    if '지난주' in query or '지난 주' in query or '저번주' in query or '저번 주' in query:
        start_of_last_week = today - timedelta(days=today.weekday() + 7)
        end_of_last_week = start_of_last_week + timedelta(days=6)
        result['type'] = 'relative'
        result['start_date'] = start_of_last_week.replace(hour=0, minute=0, second=0)
        result['end_date'] = end_of_last_week.replace(hour=23, minute=59, second=59)
        result['original'] = '지난주'
        return result
    
    # "이번달"
    if '이번달' in query or '이번 달' in query:
        start_of_month = today.replace(day=1, hour=0, minute=0, second=0)
        if today.month == 12:
            end_of_month = today.replace(month=12, day=31, hour=23, minute=59, second=59)
        else:
            next_month = today.replace(month=today.month + 1, day=1)
            end_of_month = (next_month - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        result['type'] = 'relative'
        result['start_date'] = start_of_month
        result['end_date'] = end_of_month
        result['original'] = '이번달'
        return result
    
    # "지난달"
    if '지난달' in query or '지난 달' in query or '저번달' in query or '저번 달' in query:
        if today.month == 1:
            last_month = today.replace(year=today.year - 1, month=12, day=1)
        else:
            last_month = today.replace(month=today.month - 1, day=1)
        
        start_of_last_month = last_month.replace(hour=0, minute=0, second=0)
        end_of_last_month = (today.replace(day=1) - timedelta(days=1)).replace(hour=23, minute=59, second=59)
        result['type'] = 'relative'
        result['start_date'] = start_of_last_month
        result['end_date'] = end_of_last_month
        result['original'] = '지난달'
        return result
    
    # "최근" (지난 7일)
    if '최근' in query or '요즘' in query:
        last_week = today - timedelta(days=14)
        result['type'] = 'relative'
        result['start_date'] = last_week.replace(hour=0, minute=0, second=0)
        result['end_date'] = today.replace(hour=23, minute=59, second=59)
        result['original'] = '최근'
        result['recent_flag'] = True  # ← 최근 플래그 추가!
        return result
    
    # ========== 2. 절대적 날짜 ==========
    
    # "N월 N일부터 ~ 까지" 범위 패턴 (최우선!)
    range_patterns = [
        r'(\d{1,2})월\s*(\d{1,2})일\s*부터\s*(\d{1,2})월\s*(\d{1,2})일',  # 10월 27일부터 10월 31일까지
        r'(\d{1,2})월\s*(\d{1,2})일\s*부터\s*오늘(?:까지)?',  # 10월 27일부터 오늘(까지)
        r'(\d{1,2})월\s*(\d{1,2})일\s*[-~]\s*(\d{1,2})월\s*(\d{1,2})일',  # 10월 27일 - 10월 31일
        r'(\d{1,2})월\s*(\d{1,2})일\s*[-~]\s*오늘',  # 10월 27일 ~ 오늘
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, query)
        if match:
            groups = match.groups()
            
            # "N월 N일부터 오늘" 패턴
            if '오늘' in match.group(0):
                start_month = int(groups[0])
                start_day = int(groups[1])
                year = today.year
                
                try:
                    start_date = datetime(year, start_month, start_day, 0, 0, 0)
                    end_date = today.replace(hour=23, minute=59, second=59)
                    
                    result['type'] = 'range'
                    result['start_date'] = start_date
                    result['end_date'] = end_date
                    result['original'] = f'{start_month}월 {start_day}일부터 오늘'
                    return result
                except ValueError:
                    pass
            else:
                # "N월 N일부터 M월 M일" 패턴
                start_month, start_day, end_month, end_day = map(int, groups)
                year = today.year
                
                try:
                    start_date = datetime(year, start_month, start_day, 0, 0, 0)
                    end_date = datetime(year, end_month, end_day, 23, 59, 59)
                    
                    result['type'] = 'range'
                    result['start_date'] = start_date
                    result['end_date'] = end_date
                    result['original'] = f'{start_month}월 {start_day}일부터 {end_month}월 {end_day}일'
                    return result
                except ValueError:
                    pass
                
    # "N월" 패턴 (예: "11월", "1월") - 전체 달
    month_only_pattern = r'(\d{1,2})월'
    month_match = re.search(month_only_pattern, query)
    if month_match and '월' in query:
        # "N월 N일" 패턴이 아닌지 확인
        if not re.search(r'\d{1,2}월\s*\d{1,2}일', query):
            month = int(month_match.group(1))
            year = today.year
            
            try:
                start_date = datetime(year, month, 1, 0, 0, 0)
                
                if month == 12:
                    end_date = datetime(year, 12, 31, 23, 59, 59)
                else:
                    next_month = datetime(year, month + 1, 1)
                    end_date = (next_month - timedelta(days=1)).replace(hour=23, minute=59, second=59)
                
                result['type'] = 'range'
                result['start_date'] = start_date
                result['end_date'] = end_date
                result['original'] = f'{month}월'
                
                print(f"[DEBUG] '{month}월' 감지 → {start_date.date()} ~ {end_date.date()}")
                return result
            except ValueError:
                pass
    
    # "1월 15일", "2025년 1월 15일"
    date_patterns = [
        (r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', 'year-month-day'),
        (r'(\d{1,2})월\s*(\d{1,2})일', 'month-day'),
    ]
    
    for pattern, date_type in date_patterns:
        match = re.search(pattern, query)
        if match:
            if date_type == 'year-month-day':
                year, month, day = map(int, match.groups())
            else:  # month-day
                year = today.year
                month, day = map(int, match.groups())
            
            try:
                target_date = datetime(year, month, day)
                result['type'] = 'absolute'
                result['start_date'] = target_date.replace(hour=0, minute=0, second=0)
                result['end_date'] = target_date.replace(hour=23, minute=59, second=59)
                result['original'] = match.group(0)
                return result
            except ValueError:
                pass
    
    # ========== 3. 기간 검색 ==========
    range_patterns = [
        r'(\d{1,2})월\s*~\s*(\d{1,2})월',
        r'(\d{1,2})월부터\s*(\d{1,2})월까지',
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, query)
        if match:
            start_month, end_month = map(int, match.groups())
            year = today.year
            
            try:
                start_date = datetime(year, start_month, 1, 0, 0, 0)
                
                if end_month == 12:
                    end_date = datetime(year, 12, 31, 23, 59, 59)
                else:
                    next_month = datetime(year, end_month + 1, 1)
                    end_date = (next_month - timedelta(days=1)).replace(hour=23, minute=59, second=59)
                
                result['type'] = 'range'
                result['start_date'] = start_date
                result['end_date'] = end_date
                result['original'] = match.group(0)
                return result
            except ValueError:
                pass
    
    # 날짜 정보 없음
    return result

# ============================================================
# 상태 파싱
# ============================================================

def parse_status_from_query(query: str) -> str:
    """
    쿼리에서 회의 상태 추출
    
    반환:
    - 'SCHEDULED': 예정된
    - 'RECORDING': 진행중
    - 'COMPLETED': 완료된
    - 'CANCELLED': 취소된
    - None: 상태 지정 없음
    """
    query_lower = query.lower()
    
    # ========== 과거형 어미 패턴 (우선순위 1) ==========
    past_tense_patterns = [
        r'했어\??$',      # 했어? 했어
        r'있었어\??$',    # 있었어? 있었어
        r'였어\??$',      # 였어? 였어
        r'더라\??$',      # 더라? 더라
        r'했나\??$',      # 했나? 했나
        r'있었나\??$',    # 있었나? 있었나
        r'였나\??$',      # 였나? 였나
        r'됐어\??$',      # 됐어? 됐어
        r'했는지\??$',    # 했는지? 했는지
        r'있었는지\??$',  # 있었는지? 있었는지
        r'였던\s',        # 였던
        r'했던\s',        # 했던
    ]
    
    for pattern in past_tense_patterns:
        if re.search(pattern, query_lower):
            print(f"[DEBUG] 상태 필터: COMPLETED (과거형 어미 감지)")
            return 'COMPLETED'
    
    # ========== 미래형 어미 패턴 (우선순위 2) ==========
    future_tense_patterns = [
        r'할\s*거야\??$',   # 할 거야? 할거야?
        r'할까\??$',        # 할까?
        r'있을까\??$',      # 있을까?
        r'될까\??$',        # 될까?
        r'할\s*예정',       # 할 예정
        r'있을\s*예정',     # 있을 예정
    ]
    
    for pattern in future_tense_patterns:
        if re.search(pattern, query_lower):
            print(f"[DEBUG] 상태 필터: SCHEDULED (미래형 어미 감지)")
            return 'SCHEDULED'
    
    # ========== 명시적 키워드 (우선순위 3) ==========
    scheduled_keywords = ['예정', '예정된', '앞으로', '다가오는', '예약', '예약된', '미래', '다음']
    if any(kw in query_lower for kw in scheduled_keywords):
        print(f"[DEBUG] 상태 필터: SCHEDULED (예정)")
        return 'SCHEDULED'
    
    completed_keywords = ['완료', '완료된', '끝난', '지난', '과거', '했던', '했었던']
    if any(kw in query_lower for kw in completed_keywords):
        print(f"[DEBUG] 상태 필터: COMPLETED (완료)")
        return 'COMPLETED'
    
    recording_keywords = ['진행중', '진행 중', '현재', '녹화중', '녹화 중', '진행되는', '하는 중']
    if any(kw in query_lower for kw in recording_keywords):
        print(f"[DEBUG] 상태 필터: RECORDING (진행중)")
        return 'RECORDING'
    
    cancelled_keywords = ['취소', '취소된', '무산', '무산된']
    if any(kw in query_lower for kw in cancelled_keywords):
        print(f"[DEBUG] 상태 필터: CANCELLED (취소)")
        return 'CANCELLED'
    
    return None

# ============================================================
# 키워드 추출
# ============================================================

def extract_keywords_from_query(utterance):
    """질문에서 키워드 추출 (패턴 기반 - 완전판)"""
    import re
    
    # 1. 한글 2글자 이상 추출
    tokens = re.findall(r'[가-힣]{2,}', utterance)
    
    # 2. 영문/숫자 키워드 추출 (AI, Q4, CEO 등)
    english_tokens = re.findall(r'[A-Za-z0-9]+', utterance)
    
    # 영문 키워드 중 의미있는 것만 (2글자 이상 또는 대문자)
    for token in english_tokens:
        if len(token) >= 2:
            tokens.append(token.upper())  # 대문자로 통일
        elif token.isupper():  # 1글자여도 대문자면 약어로 간주
            tokens.append(token)
    
    # ========== 복합어 전처리 (회의, 관련 분리) ==========
    processed_tokens = []
    for token in tokens:
        # '회의'로 끝나는 복합어 처리
        if token.endswith('회의') and len(token) > 2:
            base_word = token[:-2]  # '개발회의' → '개발'
            processed_tokens.append(base_word)
            print(f"[DEBUG] 복합어 분리: '{token}' → '{base_word}'")
        # '관련'으로 끝나는 복합어 처리
        elif token.endswith('관련') and len(token) > 2:
            base_word = token[:-2]  # '채용관련' → '채용'
            processed_tokens.append(base_word)
            print(f"[DEBUG] 복합어 분리: '{token}' → '{base_word}'")
        else:
            processed_tokens.append(token)
    
    tokens = processed_tokens
    
    keywords = []

    # 의미 없는 패턴 (완전판!)
    meaningless_patterns = [
        # ========== 날짜/시간 표현 ==========
        r'^(오늘|어제|모레|그제|내일).*(은|는|에|의|도|만)?$',
        r'^(이번주|지난주|다음주|저번주).*(은|는|에|의|도|만)?$',
        r'^(이번달|지난달|다음달|저번달).*(은|는|에|의|도|만)?$',
        r'^(최근|요즘|근래|최근에|요즘에).*(은|는|에|의)?$',
        r'^(올해|작년|내년|재작년).*(은|는|에|의)?$',
        r'^(이번|지난|다음|저번|그|이|저).*(주|달|년|해)$',
        
        # ========== 회의 관련 (단독 사용만 불용어) ==========
        r'^(회의|미팅|회의록|세미나|워크샵)(가|이|은|는|을|를|에|의|있었|있나|였|인)?$',
        
        # ========== 상태/완료 ==========
        r'^(예정|완료|진행|끝난|지난|과거|미래).*(된|되어|이|인|의)?$',
        r'^(진행중|진행|완료|예정|끝).*(이|인)?$',
        
        # ========== 의문사 (모든 변형) ==========
        r'^(뭐|무엇|무슨|어떤|어느).*(가|를|에|야|지|야|였지|였어|있었지|인지)?$',
        r'^(언제|어디|누가|누구|왜|어떻게|어찌).*(가|를|에|서|인지)?$',
        r'^(몇|얼마|어느).*(개|명|번|시|분|일|인지)?$',
        
        # ========== 동사/형용사 어미 (과거/현재/미래) ==========
        r'.+(었어|었나|었니|었는지|었을까|었을|었던)$',
        r'.+(있어|있나|있니|있는지|있을까|있을|있는|있던)$',
        r'.+(했어|했나|했니|했는지|했을까|했을|했던|함)$',
        r'.+(이야|이니|인지|일까|인가|이었|이었어)$',
        r'.+(하는|하니|할까|할지|하지|한|하던)$',
        r'.+(되는|되니|될까|될지|되지|된|되던)$',
        r'.+(나|니|지|까|가|냐|냐고)$',
        r'.+(개야|번이야|거야|거니|뭐야|뭔가|뭐지|있어)$',

        # ========== 시간/기간 표현 ==========
        r'^(동안|사이|중|때|무렵|경|쯤|간|시|분|초)$',
        r'^(년|월|일|주).*(간|동안|사이|중|에|에는|에도)?$',
        
        # ========== 조사 (모든 조사) ==========
        r'^.+(가|이|은|는|을|를|에|의|와|과|로|으로|부터|까지|만|도|조차|마저|부터|한테|께|에게)$',
        r'^.+(라고|이라고|라는|이라는|처럼|같이|마냥|듯이|대로)$',
        r'^.+(에서|에게|한테서|로부터)$',
        r'^.+(동안|사이|중|까지)$',
        
        # ========== 지시어/대명사 ==========
        r'^(이|그|저|요|저것|이것|그것).*(가|이|은|는|을|를)?$',
        r'^(여기|거기|저기|어디).*(서|에|로|가)?$',
        r'^(이렇게|그렇게|저렇게|어떻게)$',
        
        # ========== 부사 (정도/양태) ==========
        r'^(좀|약간|조금|많이|아주|완전|정말|진짜|매우|꽤|제법|대단히|상당히|굉장히|엄청|너무|되게|무척|퍽|참)$',
        r'^(아마|혹시|만약|절대|결코|전혀|별로)$',
        r'^(빨리|천천히|갑자기|슬슬|서서히)$',
        
        # ========== 접속사/연결어 ==========
        r'^(그리고|그러나|하지만|그런데|근데|그래서|따라서|그러므로|그렇지만|그치만)$',
        r'^(그럼|그래|그치|맞아|맞지|응|네|예|아니)$',
        
        # ========== 요청/명령 동사 ==========
        r'^(찾아|알려|보여|말해|설명|가르쳐|검색|얘기|이야기).*(줘|주세요|봐|주|줄래|주실래)?$',
        r'^(줘|아줘|해줘)$',  # 오타 처리용

        # ========== 존재/상태 동사 ==========
        r'^(있|없|계시).+(어|었어|나|니|을까|는지|던|다|십니까)$',
        r'^(있어|없어|없나|없니)$',  # '있어', '없어' 단독 제거
        r'^(하나|둘|셋|한개|두개|몇개).*(밖에|만|뿐)?$',  # 수량 표현

        # ========== 의문/추측 ==========
        r'^(거|것|게).*(야|인가|인지|냐|까)?$',
        r'^(건가|건지|거나|거든|거야|걸까)$',
        
        # ========== 회상/기억 ==========
        r'.+(였더라|였지|더라|였나|였어|였는지|었더라|었지)$',
        r'^(기억|생각).*(나|안나|못|해|하니)?$',
        
        # ========== 기타 불용어 ==========
        r'^(관련|대해|관해|대한|관한)$',
        r'^(내용|정보|사항|항목|자료|데이터)$',
        r'^(전부|모두|다|전체|모든|각|모)$',
        r'^(하나|둘|셋|여러|몇몇)$',
        r'^(위해|위한|대로|만큼|처럼)$',
    ]
    
    keywords = []
    for token in tokens:
        # 패턴 매치 확인
        is_meaningless = any(
            re.match(pattern, token) 
            for pattern in meaningless_patterns
        )
        
        if not is_meaningless:
            keywords.append(token)
            print(f"[DEBUG] 추출된 키워드: '{token}'")
        else:
            print(f"[DEBUG] 불용어 제거: '{token}'")
    
    # 중복 제거
    keywords = list(dict.fromkeys(keywords))
    
    # ========== 날짜 관련 숫자 제거 ==========
    # 1. 날짜 패턴과 함께 나온 숫자 제거
    date_number_patterns = [
        r'(\d{1,2})\s*월',      # 11월, 1월
        r'(\d{1,2})\s*일',      # 15일, 1일  
        r'(\d{4})\s*년',        # 2025년
        r'월\s*(\d{1,2})',      # 월 11
        r'일\s*(\d{1,2})',      # 일 15
    ]
    
    excluded_numbers = set()
    for pattern in date_number_patterns:
        matches = re.findall(pattern, utterance)
        for match in matches:
            excluded_numbers.add(match)
    
    # 2. 날짜 관련 단어 근처의 모든 숫자 제거
    date_words = ['월', '일', '년', '부터', '까지', '전', '후', '오늘', '어제', '내일', '이번주', '지난주', '다음주']
    has_date_context = any(word in utterance for word in date_words)
    
    if has_date_context:
        # 날짜 맥락이 있으면 1~4자리 숫자는 모두 제거 (년도 포함)
        original_keywords = keywords.copy()
        keywords = [kw for kw in keywords if not (kw.isdigit() and 1 <= len(kw) <= 4)]
        removed = set(original_keywords) - set(keywords)
        if removed:
            print(f"[DEBUG] 날짜 맥락에서 숫자 제거: {removed}")

    else:
        # 날짜 맥락 없으면 패턴 매칭된 것만 제거
        if excluded_numbers:
            original_keywords = keywords.copy()
            keywords = [kw for kw in keywords if kw not in excluded_numbers]
            removed = set(original_keywords) - set(keywords)
            if removed:
                print(f"[DEBUG] 날짜 숫자 제거: {removed}")
    
    return keywords

# ============================================================
# Lambda 응답 파싱
# ============================================================
def parse_meeting_count(lambda_response: str) -> int:
    """Lambda 응답에서 회의 개수 추출"""
    import re
    
    # "회의록 3개를 찾았습니다" 패턴
    match = re.search(r'회의록\s*(\d+)개', lambda_response)
    if match:
        count = int(match.group(1))
        print(f"[DEBUG] 회의 개수: {count}개")
        return count
    
    # 못 찾으면 1개로 간주
    return 1

def parse_meetings_list(lambda_response: str) -> list:
    """Lambda 응답에서 회의 목록 파싱"""
    meetings = []
    
    # 구분선으로 섹션 분리
    sections = lambda_response.split("━━━━━━━━━━━━━━━━━━━━━━")
    
    for section in sections:
        # 📌가 없으면 스킵 (헤더나 빈 섹션)
        if "📌" not in section:
            continue
            
        meeting = {}
        
        # 제목 추출
        title_match = re.search(r'📌\s*(.+)', section)
        if title_match:
            meeting['title'] = title_match.group(1).strip()
        
        # 날짜 추출
        date_match = re.search(r'📅\s*날짜:\s*(.+)', section)
        if date_match:
            meeting['date'] = date_match.group(1).strip()
        
        # 설명 추출
        desc_match = re.search(r'📝\s*설명:\s*(.+)', section)
        if desc_match:
            meeting['description'] = desc_match.group(1).strip()
        
        # 요약 추출
        summary_match = re.search(r'📋\s*요약:\s*(.+)', section)
        if summary_match:
            meeting['summary'] = summary_match.group(1).strip()
        
        # 제목이 있으면 추가
        if meeting.get('title'):
            meetings.append(meeting)
    
    logger.info(f"[파싱 완료] {len(meetings)}개 회의 발견")
    return meetings


# ============================================================
# 오프토픽 체크
# ============================================================

def is_off_topic_query(query: str) -> bool:
    """회의록과 무관한 질문인지 체크"""
    query_lower = query.lower().strip()
    
    # ========== 1. 회의 관련 핵심 키워드 있으면 무조건 통과 ==========
    meeting_keywords = [
        '회의', '미팅', 'meeting', '회의록', '논의', '안건',
        '참석', '참여', '발표', '설명', '결정', '합의',
        '검토', '승인', '요약', 'discussion', '세미나', '워크샵'
    ]
    if any(keyword in query_lower for keyword in meeting_keywords):
        return False  # 오프토픽 아님
    
    # ========== 2. 할 일 관련 키워드도 통과 ==========
    task_keywords = ['할 일', '할일', 'task', '업무', '맡은', '담당']
    if any(keyword in query_lower for keyword in task_keywords):
        return False
    
    # ========== 3. 대명사로 시작하는 짧은 질문은 컨텍스트 질문으로 간주 ==========
    pronouns = ['그', '저', '이', '거기', '그거', '저거', '이거']
    if any(query_lower.startswith(p) for p in pronouns) and len(query) <= 15:
        return False  # 컨텍스트 질문일 가능성 높음
    
    # ========== 4. 숫자만 입력 (회의 선택) ==========
    if query_lower.isdigit():
        return False
    
    # ========== 5. 오프토픽 패턴 체크 ==========
    off_topic_patterns = [
        '안녕', '안녕하세요', 'hello', 'hi', '뭐해', '심심',
        '날씨', '요리', '맛집', '영화', '음악', '게임',
        '뉴스', '스포츠', '주식', '부동산', '연애', '건강',
        '농담', '사랑', '운동', '여행', '레시피', '음식'
    ]
    
    return any(pattern in query_lower for pattern in off_topic_patterns)

def get_off_topic_response() -> str:
    """오프토픽 안내 메시지"""
    return """죄송해요, 저는 회의록 검색 전용 챗봇이에요! 🗂️

다음과 같은 질문만 도와드릴 수 있어요:
✅ 마케팅 회의 있었어?
✅ 이번주 기획 회의록 찾아줘
✅ 디자인 논의 내용 알려줘
✅ 최근 개발 미팅 정리해줘

회의록 검색이 필요하시면 '회의', '미팅', '회의록' 같은
단어와 함께 질문해주세요! 😊"""

# ============================================================

def has_search_intent(query: str) -> bool:
    """검색 의도가 있는지 판단"""
    search_keywords = [
        '회의', '미팅', '회의록', '찾아', '검색', '알려', '보여',
        '있어', '있었어', '있나', '있니', '뭐', '어떤', '어디',
        'meeting', 'search', 'find'
    ]
    
    query_lower = query.lower()
    return any(keyword in query_lower for keyword in search_keywords)

# ============================================================
# MySQL 직접 검색
# ============================================================

def search_meetings_direct(user_query, date_info=None, status=None, user_job=None, selected_meeting_id=None, user_id=None):
    """MySQL 직접 검색 + 페르소나 적용"""
    from .formatting import format_single_meeting, format_multiple_meetings_short
    from .config import ENABLE_PERSONA
    from .llm import parse_query_intent
    
    with get_db_connection() as conn:
        if not conn:
            return ("데이터베이스 연결 실패", [])
        
        try:
            # 1. 키워드 추출
            keywords = extract_keywords_from_query(user_query)
            print(f"[DEBUG] 추출된 키워드: {keywords}")
            
            # ========== Hybrid 방식: 패턴 실패 시 LLM 호출 ==========
            # 통계 질문 감지
            is_count = any(word in user_query for word in ['몇', '개수', '횟수', '번', '총'])

            # LLM 호출 조건: 키워드 없거나, 상태 없거나, 통계 질문
            needs_llm = not keywords or not status or is_count

            if needs_llm:
                meeting_keywords = ['회의', '미팅', '회의록', '논의', '발표', '보고']
                has_meeting_word = any(kw in user_query for kw in meeting_keywords)
                
                if has_meeting_word:
                    print(f"[DEBUG] 패턴 실패 감지 → HyperCLOVA X 호출 (키워드: {bool(keywords)}, 상태: {bool(status)}, 통계: {is_count})")
                    from .llm import parse_query_intent
                    parsed = parse_query_intent(user_query)
                    
                    # 통계 질문이면 count 함수로
                    if parsed.get('intent') == 'count_meetings':
                        print(f"[DEBUG] 통계 질문 감지 → search_meeting_count 호출")
                        result = search_meeting_count(
                            keywords=keywords or parsed.get('keywords', []),
                            date_info=date_info,
                            status=status or parsed.get('status'),
                            user_job=user_job
                        )
                        if result:
                            return format_count_result(result, user_query)
                        else:
                            return ("회의를 찾을 수 없었어요. 😢", [])
                    
                    # 일반 검색: 실패한 것만 LLM 결과로 보충
                    if not keywords:
                        keywords = parsed.get('keywords', [])
                    
                    if not date_info and parsed.get('date_range'):
                        date_info = parse_date_from_query(parsed['date_range'])
                    
                    if not status and parsed.get('status'):
                        status = parsed['status']
                    
                    print(f"[DEBUG] LLM 보충 결과 - 키워드: {keywords}, 날짜: {date_info}, 상태: {status}")
                
                else:
                    # 회의 키워드 없지만 키워드나 상태가 있으면 검색 진행
                    if not status and not keywords:
                        return (get_off_topic_response(), [])
                    # keywords나 status 있으면 아래 SQL 검색으로 진행

            # 2. SQL 쿼리 구성
            cursor = conn.cursor()
                        
            query = "SELECT * FROM Meeting WHERE 1=1"
            params = []

            # [추가] user_id 조건 (로그인한 사용자의 회의만)
            if user_id:
                query += " AND host_user_id = %s"
                params.append(user_id)
                print(f"[DEBUG] user_id 필터 추가: {user_id}")
            
            # 키워드 조건 (SQL에서 직접 처리)
            if keywords:
                keyword_conditions = []
                for keyword in keywords:
                    keyword_conditions.append(
                        "(title LIKE %s OR description LIKE %s OR summary LIKE %s)"
                    )
                    params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
                
                # 여러 키워드면 AND, 단일 키워드면 그대로
                if len(keywords) > 1:
                    query += " AND (" + " AND ".join(keyword_conditions) + ")"
                else:
                    query += " AND (" + " OR ".join(keyword_conditions) + ")"
                    
            from datetime import datetime

            # 오늘 날짜인지 확인
            is_today_query = False
            if date_info and date_info.get('start_date') and date_info.get('end_date'):
                today = datetime.now().date()
                start_date = date_info['start_date']
                end_date = date_info['end_date']
                
                # start_date와 end_date가 같고, 오늘이면
                if hasattr(start_date, 'date'):
                    start_date = start_date.date()
                if hasattr(end_date, 'date'):
                    end_date = end_date.date()
                
                if start_date == end_date == today:
                    is_today_query = True
                    print(f"[DEBUG] 오늘 날짜 쿼리 감지 → 모든 상태 검색")

            # 날짜 조건
            if date_info and date_info.get('start_date'):
                query += " AND scheduled_at >= %s"
                params.append(date_info['start_date'])

            if date_info and date_info.get('end_date'):
                query += " AND scheduled_at <= %s"
                params.append(date_info['end_date'])

            # 상태 조건
            if status and not is_today_query:  # 오늘 쿼리가 아닐 때만 상태 필터 적용
                today_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                if status == 'SCHEDULED':
                    # 예정된 회의: 오늘 00:00 이후
                    query += " AND status = %s AND scheduled_at >= %s"
                    params.append(status)
                    params.append(today_dt)
                elif status == 'COMPLETED':
                    # 완료된 회의: 오늘 00:00 이전
                    query += " AND status = %s AND scheduled_at < %s"
                    params.append(status)
                    params.append(today_dt)
                else:
                    # RECORDING은 날짜 제한 없음
                    query += " AND status = %s"
                    params.append(status)
            elif status and is_today_query:
                # 오늘 쿼리면 상태 무시하고 모든 회의 검색
                print(f"[DEBUG] 오늘 쿼리 → 상태 필터({status}) 무시")
                        
            # ========== 컨텍스트로 특정 회의만 검색 ==========
            if selected_meeting_id:
                query += " AND id = %s"
                params.append(selected_meeting_id)
                print(f"[컨텍스트 필터] 회의 ID={selected_meeting_id}만 검색")
            
            query += " ORDER BY scheduled_at DESC LIMIT 50"

            print(f"[DEBUG] SQL: {query}")
            print(f"[DEBUG] Params: {params}")
            
            # 3. 쿼리 실행
            cursor.execute(query, params)
            meetings = cursor.fetchall()
            
            print(f"[DEBUG] 검색 결과: {len(meetings)}개")

            # ========== 완전 일치 체크 ==========
            if len(meetings) > 1:
                user_query_lower = user_query.lower().strip()
                for meeting in meetings:
                    meeting_title_lower = meeting.get('title', '').lower().strip()
                    if user_query_lower == meeting_title_lower:
                        print(f"[DEBUG] 완전 일치 발견: {meeting.get('title')}")
                        meetings = [meeting]  # 단일 회의로 변경
                        break
            
            # ========== Phase 2-A: 페르소나 정렬 적용 ==========
            # 키워드 검색이 있으면 키워드 매칭 점수로 정렬
            if keywords and meetings and len(meetings) > 1:
                # 키워드 매칭 점수 계산
                for meeting in meetings:
                    score = 0
                    title = meeting.get('title', '').lower()
                    description = meeting.get('description', '').lower()
                    summary = meeting.get('summary', '').lower()
                    
                    for keyword in keywords:
                        if keyword.lower() in title:
                            score += 10
                        if keyword.lower() in summary:
                            score += 5
                        if keyword.lower() in description:
                            score += 3
                    
                    meeting['keyword_score'] = score
                
                # 점수순 정렬
                meetings = sorted(meetings, key=lambda x: x.get('keyword_score', 0), reverse=True)
                print(f"[DEBUG] 키워드 매칭 점수로 정렬 완료")
                
                # 디버그: 상위 3개 점수 출력
                for i, m in enumerate(meetings[:3]):
                    print(f"  {i+1}. {m.get('title')} (키워드 점수: {m.get('keyword_score', 0)})")
                
                # 유사도 기반 단일 회의 판단
                if len(meetings) > 1:
                    import difflib
                    user_query_clean = user_query.lower().strip()
                    
                    # 각 회의 제목과의 유사도 계산
                    similarities = []
                    for meeting in meetings:
                        title = meeting.get('title', '').lower().strip()
                        # difflib로 유사도 계산 (0.0 ~ 1.0)
                        ratio = difflib.SequenceMatcher(None, user_query_clean, title).ratio()
                        similarities.append((meeting, ratio))
                        print(f"  - '{meeting.get('title')}' 유사도: {ratio:.2%}")
                    
                    # 가장 유사한 것 찾기
                    best_match = max(similarities, key=lambda x: x[1])
                    best_ratio = best_match[1]
                    
                    # 유사도가 80% 이상이고, 2등과 차이가 20% 이상이면 단일 회의로 처리
                    if best_ratio >= 0.8:
                        second_best_ratio = sorted(similarities, key=lambda x: x[1], reverse=True)[1][1] if len(similarities) > 1 else 0
                        ratio_diff = best_ratio - second_best_ratio
                        
                        if ratio_diff >= 0.2:
                            print(f"[DEBUG] 유사도 {best_ratio:.1%} (차이: {ratio_diff:.1%}) → 단일 회의로 처리")
                            meetings = [best_match[0]]

            elif ENABLE_PERSONA and user_job and meetings and len(meetings) > 1:
                meetings = search_with_persona(meetings, user_job)
                print(f"[DEBUG] Phase 2-A: {user_job} 관련도 순으로 정렬")

            # 4. 결과 포맷팅 (실패 시 단계적 완화)
            if not meetings:
                print(f"[DEBUG] 검색 실패 → 단계적 완화 시작")
                
                # ===== 1단계: status 제거 =====
                if status:
                    print(f"[DEBUG] 1단계 완화: status 제거")
                    query_fallback = "SELECT * FROM Meeting WHERE 1=1"
                    params_fallback = []
                    
                    if keywords:
                        keyword_conditions = []
                        for keyword in keywords:
                            keyword_conditions.append("(title LIKE %s OR description LIKE %s OR summary LIKE %s)")
                            params_fallback.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
                        query_fallback += " AND (" + " OR ".join(keyword_conditions) + ")"
                    
                    if date_info and date_info.get('start_date'):
                        query_fallback += " AND scheduled_at >= %s"
                        params_fallback.append(date_info['start_date'])
                    if date_info and date_info.get('end_date'):
                        query_fallback += " AND scheduled_at <= %s"
                        params_fallback.append(date_info['end_date'])
                    
                    query_fallback += " ORDER BY scheduled_at DESC LIMIT 50"
                    cursor.execute(query_fallback, params_fallback)
                    meetings_fallback = cursor.fetchall()
                    
                    if meetings_fallback:
                        status_kr = {'COMPLETED': '완료된', 'SCHEDULED': '예정된', 'RECORDING': '진행중'}
                        other_status = meetings_fallback[0]['status']
                        date_str = date_info.get('original', '') if date_info else ''
                        keyword_str = ', '.join(keywords) if keywords else ''
                        
                        # 조건 구성
                        conditions = []
                        if date_str:
                            conditions.append(date_str)
                        if status:
                            conditions.append(status_kr.get(status, status))
                        if keyword_str:
                            conditions.append(keyword_str)
                        
                        condition_text = ' '.join(conditions) if conditions else ''
                        
                        from .formatting import format_single_meeting, format_multiple_meetings_short
                        
                        if len(meetings_fallback) == 1:
                            if ENABLE_PERSONA and user_job:
                                detail = format_single_meeting_with_persona(meetings_fallback[0], user_job)
                            else:
                                detail = format_single_meeting(meetings_fallback[0])
                            
                            found_status = status_kr.get(other_status, other_status)  # 실제 발견된 상태
                            
                            if status:
                                # status가 있으면
                                requested_status = status_kr.get(status, status)
                                message = f"""❌ {requested_status} 회의는 없어요.

하지만 {found_status} 회의가 있습니다! 📌

{detail}

이 회의를 확인해보시겠어요?"""
                            else:
                                # status가 없으면
                                message = f"""✅ {found_status} 회의를 찾았어요! 📌

{detail}

이 회의를 확인해보시겠어요?"""
                                
                        else:
                            # 여러 회의의 상태 확인
                            statuses = list(set([m['status'] for m in meetings_fallback]))
                            if status:
                                statuses = [s for s in statuses if s != status]  # 요청한 상태 제외
                            found_statuses = [status_kr.get(s, s) for s in statuses]
                            found_status_text = '/'.join(found_statuses) if found_statuses else '다른'
                            
                            # detail 생성
                            detail = format_multiple_meetings_short(meetings_fallback[:5], user_query, len(meetings_fallback) if len(meetings_fallback) > 5 else None, date_info, None)
                            
                            if status:
                                # status가 있으면
                                requested_status = status_kr.get(status, status)
                                message = f"""❌ {requested_status} 회의는 없어요.

하지만 {found_status_text} 회의들이 있습니다! 📋

{detail}"""
                            else:
                                # status가 없으면
                                message = f"""✅ {found_status_text} 회의들을 찾았어요! 📋

{detail}"""
                        
                        print(f"[DEBUG] 1단계 완화 성공: {len(meetings_fallback)}개 발견")
                        return (message, meetings_fallback)
                                    
                # ===== 2단계: 날짜 제거, 키워드만 검색 =====
                if date_info and date_info.get('start_date'):
                    # 의미있는 키워드가 있으면 → 날짜만 제거하고 키워드로 재검색
                    meaningful_keywords = [k for k in keywords if k not in ['있어', '없어', '뭐', '거', '것', '회의']]
                    # "15일", "일", "월" 같은 날짜 관련 단어도 제거
                    meaningful_keywords = [k for k in meaningful_keywords if not any(x in k for x in ['일', '월', '주', '년'])]
                    
                    if meaningful_keywords:
                        print(f"[DEBUG] 2단계 완화: 날짜 제거, 키워드만 검색 (키워드: {meaningful_keywords})")
                        query_fallback = "SELECT * FROM Meeting WHERE 1=1"
                        params_fallback = []
                        
                        keyword_conditions = []
                        for keyword in meaningful_keywords:  # ← meaningful_keywords 사용!
                            keyword_conditions.append("(title LIKE %s OR description LIKE %s OR summary LIKE %s)")
                            params_fallback.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
                        query_fallback += " AND (" + " OR ".join(keyword_conditions) + ")"
                        
                        if status:
                            query_fallback += " AND status = %s"
                            params_fallback.append(status)
                        
                        query_fallback += " ORDER BY scheduled_at DESC LIMIT 50"
                        cursor.execute(query_fallback, params_fallback)
                        meetings_fallback = cursor.fetchall()
                        
                        if meetings_fallback:
                            print(f"[DEBUG] 2단계 완화 성공 (날짜 제거): {len(meetings_fallback)}개 발견")
                            
                            # 페르소나 정렬
                            if ENABLE_PERSONA and user_job and len(meetings_fallback) > 1:
                                meetings_fallback = search_with_persona(meetings_fallback, user_job)
                            
                            keyword_str = ', '.join(meaningful_keywords)  # ← meaningful_keywords 사용!
                            original_date = date_info.get('original', '')
                            
                            from .formatting import format_multiple_meetings_short
                            detail = format_multiple_meetings_short(meetings_fallback[:3], user_query, len(meetings_fallback) if len(meetings_fallback) > 3 else None, None, status)
                            
                            message = f"""❌ {original_date} '{keyword_str}' 관련 회의가 없어요.

하지만 다른 날짜에 '{keyword_str}' 회의가 있어요! 📋

{detail}"""
                            
                            return (message, meetings_fallback)
                        else:
                            # 키워드로도 없음
                            print(f"[DEBUG] 2단계 완화 실패 (키워드로도 없음)")
                    else:
                        # 의미있는 키워드 없음 (날짜만 있음)
                        print(f"[DEBUG] 2단계 완화 불가 (의미있는 키워드 없음)")
                        
                
                # ===== 최종 실패 =====
                print(f"[DEBUG] 모든 완화 실패")

                # 날짜만 있고 키워드 없으면 → 간단히
                if date_info and date_info.get('original') and not keywords:
                    date_str = date_info['original']
                    if status:
                        status_kr = {'COMPLETED': '완료된', 'SCHEDULED': '예정된', 'RECORDING': '진행중'}
                        no_result_msg = f"❌ {date_str}에 {status_kr.get(status, status)} 회의가 없어요."
                    else:
                        no_result_msg = f"❌ {date_str}에 회의가 없어요."
                    return (no_result_msg, [])

                # 키워드 있으면
                elif keywords:
                    # 의미있는 키워드만 필터링 (날짜 관련 단어 제거)
                    keyword_str_list = [k for k in keywords if k not in ['있어', '없어', '뭐', '거', '것', '회의']]
                    keyword_str_list = [k for k in keyword_str_list if not any(x in k for x in ['일', '월', '주', '년'])]
                    
                    if not keyword_str_list:
                        # 의미있는 키워드 없음
                        if date_info and date_info.get('original'):
                            date_str = date_info['original']
                            no_result_msg = f"❌ {date_str}에 회의가 없어요."
                        else:
                            no_result_msg = "❌ 조건에 맞는 회의를 찾을 수 없어요."
                    else:
                        keyword_str = ', '.join(keyword_str_list)
                        if date_info and date_info.get('original'):
                            date_str = date_info['original']
                            no_result_msg = f"❌ {date_str} '{keyword_str}' 관련 회의가 없어요."
                        else:
                            no_result_msg = f"❌ '{keyword_str}' 관련 회의를 찾을 수 없어요."
                    return (no_result_msg, [])

                # 상태만 있으면
                elif status:
                    status_kr = {'COMPLETED': '완료된', 'SCHEDULED': '예정된', 'RECORDING': '진행중'}
                    no_result_msg = f"❌ {status_kr.get(status, status)} 회의가 없어요."
                    return (no_result_msg, [])

                # 아무 조건도 없으면
                else:
                    no_result_msg = "❌ 회의를 찾을 수 없어요."
                    return (no_result_msg, [])
            
            # 1개 회의 → Phase 2-A: 페르소나 템플릿 적용
            if len(meetings) == 1:
                # 날짜 범위 표시
                date_prefix = ""
                if date_info and date_info.get('original'):
                    date_prefix = f"✅ {date_info['original']}에 진행한 회의는 1개입니다.\n\n"
                
                if ENABLE_PERSONA and user_job:
                    meeting_detail = format_single_meeting_with_persona(meetings[0], user_job)
                    message = date_prefix + meeting_detail
                    print(f"[DEBUG] Phase 2-A: 단일 회의 {user_job}용 템플릿 적용")
                else:
                    meeting_detail = format_single_meeting(meetings[0])
                    message = date_prefix + meeting_detail
                return (message, meetings)
            
            # 여러 회의
            total = len(meetings)
            message = format_multiple_meetings_short(
                meetings,
                user_query,
                total,  # 항상 전달!
                date_info,
                status
            )
            return (message, meetings)
        
        except Exception as e:
            logger.error(f"MySQL 검색 실패: {e}")
            import traceback
            traceback.print_exc()
            return ("검색 중 오류가 발생했어요.", [])

# ============================================================
# Phase 2-A: 페르소나 검색
# ============================================================

def calculate_relevance(meeting: dict, user_job: str) -> float:
    """회의와 User job의 관련도 점수 계산 (실제 DB enum 기준)"""
    score = 0.0
    
    # DB의 실제 ENUM: 'NONE', 'PROJECT_MANAGER', 'FRONTEND_DEVELOPER', 
    #                  'BACKEND_DEVELOPER', 'DATABASE_ADMINISTRATOR', 'SECURITY_DEVELOPER'
    job_keywords = {
        'PROJECT_MANAGER': [
            '기획', '전략', '로드맵', '목표', '계획', '일정', '마일스톤', 
            '프로젝트', 'pm', 'po', '스프린트', '스케줄', '리소스'
        ],
        'FRONTEND_DEVELOPER': [
            '프론트엔드', '프론트', 'ui', 'ux', 'react', 'vue', '화면', 
            '인터페이스', '디자인', 'frontend', 'fe', '컴포넌트', '반응형'
        ],
        'BACKEND_DEVELOPER': [
            '백엔드', 'backend', 'api', '서버', '데이터베이스', 'spring', 
            'node', '개발팀', 'be', 'fastapi', 'rest', '배포', '인프라', 
            '성능', '아키텍처'
        ],
        'DATABASE_ADMINISTRATOR': [
            '데이터베이스', 'database', 'db', 'sql', '쿼리', '최적화', 
            '인덱스', 'mysql', '데이터', 'dba', '스키마', '마이그레이션'
        ],
        'SECURITY_DEVELOPER': [
            '보안', 'security', '취약점', '암호화', '인증', '권한', 
            'ssl', '방화벽', '점검', '보안점검', '취약점점검'
        ],
    }
    
    keywords = job_keywords.get(user_job, [])
    
    title = (meeting.get('title') or '').lower()
    description = (meeting.get('description') or '').lower()
    summary = (meeting.get('summary') or '').lower()
    
    for keyword in keywords:
        if keyword in title:
            score += 10
        if keyword in summary:
            score += 5
        if keyword in description:
            score += 3
    
    return score

def search_with_persona(meetings: list, user_job: str) -> list:
    """Job에 따라 검색 결과 우선순위 조정 (관련도 + 시간 조합)"""
    from datetime import datetime
    
    current_time = datetime.now()
    
    # 1. 페르소나 점수 계산
    for meeting in meetings:
        meeting['relevance_score'] = calculate_relevance(meeting, user_job)
        
        # 시간 거리 계산
        scheduled_at = meeting.get('scheduled_at')
        if scheduled_at:
            if isinstance(scheduled_at, str):
                scheduled_at = datetime.fromisoformat(scheduled_at.replace('Z', '+00:00'))
            time_diff = abs((scheduled_at - current_time).total_seconds())
            meeting['time_distance'] = time_diff
        else:
            meeting['time_distance'] = float('inf')
    
    # 디버그: 정렬 전
    print(f"[DEBUG] 정렬 전 상위 3개:")
    for i, m in enumerate(meetings[:3]):
        scheduled = m.get('scheduled_at')
        if isinstance(scheduled, str):
            scheduled = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
        date_str = scheduled.strftime('%Y-%m-%d') if scheduled else '날짜없음'
        print(f"  {i+1}. {m.get('title')} ({m.get('relevance_score', 0)}점, {date_str})")
    
    # 2. 관련도 상위 70% / 하위 30% 분리
    scores = sorted([m['relevance_score'] for m in meetings], reverse=True)
    threshold_index = int(len(scores) * 0.3)
    threshold = scores[threshold_index] if threshold_index < len(scores) else 0
    
    high_relevance = [m for m in meetings if m['relevance_score'] >= threshold]
    low_relevance = [m for m in meetings if m['relevance_score'] < threshold]
    
    # 3. 상위 70%는 시간순 정렬 (현재와 가까운 순)
    high_relevance_sorted = sorted(high_relevance, key=lambda x: x['time_distance'])
    
    # 4. 하위 30%는 관련도순
    low_relevance_sorted = sorted(low_relevance, key=lambda x: x['relevance_score'], reverse=True)
    
    # 5. 합치기
    final_sorted = high_relevance_sorted + low_relevance_sorted
    
    # 디버그: 정렬 후
    print(f"[DEBUG] 정렬 후 상위 3개:")
    for i, m in enumerate(final_sorted[:3]):
        scheduled = m.get('scheduled_at')
        if isinstance(scheduled, str):
            scheduled = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
        date_str = scheduled.strftime('%Y-%m-%d') if scheduled else '날짜없음'
        days_diff = int(m['time_distance'] / 86400)  # 초 → 일
        print(f"  {i+1}. {m.get('title')} ({m.get('relevance_score', 0)}점, {date_str}, {days_diff}일 차이)")
    
    # 임시 필드 제거
    for meeting in final_sorted:
        if 'time_distance' in meeting:
            del meeting['time_distance']
    
    return final_sorted

# ============================================================
# Lambda 응답 파싱 (향후 Lambda 사용 시)
# ============================================================

def parse_meeting_count(lambda_response: str) -> int:
    """Lambda 응답에서 회의 개수 추출"""
    match = re.search(r'회의록\s*(\d+)개', lambda_response)
    if match:
        count = int(match.group(1))
        print(f"[DEBUG] 회의 개수: {count}개")
        return count
    return 1

def parse_meetings_list(lambda_response: str) -> list:
    """Lambda 응답에서 회의 목록 파싱"""
    meetings = []
    sections = lambda_response.split("━━━━━━━━━━━━━━━━━━━━━━")
    
    for section in sections:
        if "📌" not in section:
            continue
        
        meeting = {}
        
        title_match = re.search(r'📌\s*(.+)', section)
        if title_match:
            meeting['title'] = title_match.group(1).strip()
        
        date_match = re.search(r'📅\s*날짜:\s*(.+)', section)
        if date_match:
            meeting['date'] = date_match.group(1).strip()
        
        desc_match = re.search(r'📝\s*설명:\s*(.+)', section)
        if desc_match:
            meeting['description'] = desc_match.group(1).strip()
        
        summary_match = re.search(r'📋\s*요약:\s*(.+)', section)
        if summary_match:
            meeting['summary'] = summary_match.group(1).strip()
        
        if meeting.get('title'):
            meetings.append(meeting)
    
    logger.info(f"[파싱 완료] {len(meetings)}개 회의 발견")
    return meetings

# ============================================================
# Phase 3: 통계 쿼리 (COUNT)
# ============================================================
def search_meeting_count(keywords=None, date_info=None, status=None, user_job=None):
    """회의 개수 세기 + 날짜 목록 (페르소나 정렬 포함)"""
    with get_db_connection() as conn:
        if not conn:
            return None
        
        try:
            cursor = conn.cursor()
            
            # COUNT 쿼리
            query = "SELECT COUNT(*) as count FROM Meeting WHERE 1=1"
            params = []
            
            # 키워드 조건
            if keywords:
                keyword_conditions = []
                for keyword in keywords:
                    keyword_conditions.append(
                        "(title LIKE %s OR description LIKE %s OR summary LIKE %s)"
                    )
                    params.extend([f'%{keyword}%', f'%{keyword}%', f'%{keyword}%'])
                
                query += " AND (" + " OR ".join(keyword_conditions) + ")"
            
            # 날짜 조건
            if date_info and date_info.get('start_date'):
                query += " AND scheduled_at >= %s"
                params.append(date_info['start_date'])
            
            if date_info and date_info.get('end_date'):
                query += " AND scheduled_at <= %s"
                params.append(date_info['end_date'])
            
            # 상태 조건
            if status:
                from datetime import datetime
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                
                if status == 'SCHEDULED':
                    # 예정된 회의: 오늘 00:00 이후
                    query += " AND status = %s AND scheduled_at >= %s"
                    params.append(status)
                    params.append(today)
                elif status == 'COMPLETED':
                    # 완료된 회의: 오늘 00:00 이전
                    query += " AND status = %s AND scheduled_at < %s"
                    params.append(status)
                    params.append(today)
                else:
                    # RECORDING은 날짜 제한 없음
                    query += " AND status = %s"
                    params.append(status)
            
            print(f"[DEBUG] COUNT SQL: {query}")
            print(f"[DEBUG] Params: {params}")
            
            # 개수 세기
            cursor.execute(query, params)
            result = cursor.fetchone()
            count = result['count'] if result else 0
            
            print(f"[DEBUG] 회의 개수: {count}개")
            
            # 날짜 목록 가져오기 (최대 제한 없음!)
            date_query = query.replace("COUNT(*) as count", "scheduled_at, title, description, summary, id, status, host_user_id")
            date_query += " ORDER BY scheduled_at DESC"  # ← LIMIT 제거!
            
            cursor.execute(date_query, params)
            meetings = cursor.fetchall()
                    
            # ========== Phase 2-A: 페르소나 정렬 적용 ==========
            if ENABLE_PERSONA and user_job and meetings and len(meetings) > 1 and not keywords:
                meetings = search_with_persona(meetings, user_job)
                print(f"[DEBUG] Phase 2-A (COUNT): {user_job} 관련도 순으로 정렬")
            
            return {
                'count': count,
                'meetings': meetings
            }
            
        except Exception as e:
            logger.error(f"COUNT 쿼리 실패: {e}")
            import traceback
            traceback.print_exc()
            return None
        

# ============================================================
# 통계 결과 포맷팅
# ============================================================
def format_count_result(result: dict, user_query: str) -> tuple:
    """통계 쿼리 결과 포맷팅"""
    count = result.get('count', 0)
    meetings = result.get('meetings', [])
    
    if count == 0:
        return ("해당 조건의 회의를 찾을 수 없었어요. 😢", [])
    
    # 날짜 목록 생성
    from datetime import datetime
    date_list = []
    for m in meetings[:10]:  # 최대 10개만
        scheduled = m.get('scheduled_at')
        if isinstance(scheduled, str):
            scheduled = datetime.fromisoformat(scheduled.replace('Z', '+00:00'))
        date_str = scheduled.strftime('%m월 %d일') if scheduled else '날짜미정'
        date_list.append(f"- {m.get('title', '제목없음')} ({date_str})")
    
    date_summary = '\n'.join(date_list) if date_list else ''
    
    response = f"""총 {count}개의 회의가 있어요! 📊

{date_summary}

{'...' if count > 10 else ''}"""
    
    return (response, meetings)


# ============================================================
def search_tasks(user_query: str, user_id: int = 1, meeting_id: int = None, user_name: str = None) -> tuple:
    """
    Task 테이블 검색
    
    Args:
        user_query: 사용자 질문
        user_id: 현재 사용자 ID (기본값 1, 나중에 JWT로 교체)
        meeting_id: 특정 회의 ID (선택)
    
    Returns:
        (message, tasks) 튜플
    """
    from .config import DB_CONFIG
    
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        
        # ========== 타인 이름 감지 (meeting_id 무시) ==========

        # DB에서 사용자 이름 조회
        cursor.execute("SELECT name FROM User WHERE id = %s", (user_id,))
        current_user_result = cursor.fetchone()
        current_user_name = current_user_result['name'] if current_user_result else '알 수 없음'

        cursor.execute("SELECT name FROM User WHERE id != %s", (user_id,))
        other_names = [row['name'] for row in cursor.fetchall()]

        print(f"[DEBUG] 현재 사용자: {current_user_name}, 다른 사용자: {other_names}")

        # DB에서 사용자 이름 조회
        cursor.execute("SELECT name FROM User WHERE id = %s", (user_id,))
        current_user_result = cursor.fetchone()
        current_user_name = current_user_result['name'] if current_user_result else '알 수 없음'
        
        cursor.execute("SELECT name FROM User WHERE id != %s", (user_id,))
        other_names = [row['name'] for row in cursor.fetchall()]
        
        print(f"[DEBUG] 현재 사용자: {current_user_name}, 다른 사용자: {other_names}")

        query_lower = user_query.lower() 

        # 다른 사람 이름이 쿼리에 있으면 meeting_id 무시
        # 단, 회의 대명사가 있으면 meeting_id 유지 (오타 허용)
        def has_meeting_pronoun(query: str) -> bool:
            import re, difflib
            cleaned = re.sub(r'[^\w\s]', '', query)
            tokens = cleaned.split()
            pronoun_tokens = {'저', '그', '이', '해당'}
            
            for i in range(len(tokens)):
                if tokens[i] in pronoun_tokens and i + 1 < len(tokens):
                    next_token = tokens[i + 1]
                    # 조사 제거
                    next_token_no_josa = re.sub(r'에서|에게|한테|부터|까지', '', next_token)
                    # 한글만 추출
                    next_token_clean = re.sub(r'[^가-힣]', '', next_token_no_josa)
                    
                    # "회의", "미팅"과 유사도
                    similarity_meeting = difflib.SequenceMatcher(None, next_token_clean, '회의').ratio()
                    if similarity_meeting >= 0.5:
                        return True
            
            # 단독 지시어
            if any(ref in query for ref in ['거기', '여기']):
                return True
            return False
        
        has_meeting_reference = has_meeting_pronoun(user_query)
        
        found_name = None  # 여기서 미리 선언
        
        for name in other_names:
            if name in user_query:
                if not has_meeting_reference:
                    print(f"[DEBUG] 타인 이름 '{name}' 감지 → meeting_id 무시, 전체 검색")
                    meeting_id = None
                    found_name = name  # 이름 저장
                else:
                    print(f"[DEBUG] 타인 이름 '{name}' + 회의 대명사 감지 → meeting_id 유지 (특정 회의 검색)")
                    found_name = name  # 이름 저장
                    print(f"[DEBUG] found_name 저장: {found_name}")
                break
        
        # "전체", "모든", "다른" 등이 있으면 대명사 체크 무시
        has_global_keywords = any(word in query_lower for word in ['전체', '모든', '전부', '다른', '말고'])

        if not meeting_id and not has_global_keywords and any(word in query_lower for word in ['저 회의', '그 회의', '이 회의', '거기']):
            return ("어떤 회의인지 먼저 말씀해주세요! 😊\n예: '채용 전략 회의에서 할 일'", [])

        # 상태 필터링 감지
        status_filter = ""
        if any(keyword in query_lower for keyword in ['완료', '끝난', '완료한']):
            status_filter = "AND t.status = 'COMPLETED'"
            status_text = "완료한"
        elif any(keyword in query_lower for keyword in ['미완료', '남은', '해야', '할']):
            status_filter = "AND t.status = 'TODO'"
            status_text = "해야 할"
        else:
            # 기본: TODO만 (미완료 작업이 중요하므로)
            status_filter = "AND t.status = 'TODO'"
            status_text = ""
        
        # 1. "내가 맡은 일" 패턴
        if any(pattern in query_lower for pattern in ['내가', '나의', '내 할일', '내 할 일', '나는?', '나는', '내꺼는?', '내꺼는', '내가?', '내가']):
            # meeting_id가 있고 "전체"가 없으면 특정 회의 내에서 검색
            if meeting_id and not any(word in query_lower for word in ['전체', '모든', '다', '전부']):
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.user_id = %s AND t.meeting_id = %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (user_id, meeting_id))
                tasks = cursor.fetchall()
                
                # 회의 제목 추출
                meeting_title = tasks[0].get('meeting_title') if tasks else None
                if not meeting_title:
                    cursor.execute("SELECT title FROM Meeting WHERE id = %s", (meeting_id,))
                    result = cursor.fetchone()
                    meeting_title = result['title'] if result else None
                
                # meeting_title 없으면 DB에서 조회
                if not meeting_title and meeting_id:
                    cursor.execute("SELECT title FROM Meeting WHERE id = %s", (meeting_id,))
                    result = cursor.fetchone()
                    meeting_title = result['title'] if result else None
                
                # "내가" 할일이므로 내 할일만 표시
                if not tasks or len(tasks) == 0:
                    if meeting_title:
                        if user_name:
                            return (f"{meeting_title}에서 {user_name}님이 맡은 일이 없어요! 😊", [])
                        return (f"{meeting_title}에서 맡은 일이 없어요! 😊", [])
                    if user_name:
                        return (f"이 회의에서 {user_name}님이 맡은 일이 없어요! 😊", [])
                    return ("이 회의에서 맡은 일이 없어요! 😊", [])

                # 할일 목록 표시
                message = f"📋 {meeting_title} 회의에서 맡은 할 일 {len(tasks)}개:\n\n"
                for i, task in enumerate(tasks[:10], 1):
                    title = task.get('title', '제목 없음')
                    due_date = task.get('due_date')
                    status = task.get('status', 'TODO')
                    status_emoji = "✅" if status == 'COMPLETED' else "⏳"
                    
                    if due_date:
                        due_str = f"📅 {due_date.strftime('%m월 %d일')}"
                    else:
                        due_str = "📅 기한 없음"
                    
                    message += f"{status_emoji} {i}. {title}\n"
                    message += f"   {due_str}\n\n"

                return (message, tasks)

            else:
                # 전체 검색
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.user_id = %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (user_id,))
                tasks = cursor.fetchall()
                
                if not tasks:
                    if status_text:
                        if user_name:
                            return (f"{user_name}님의 {status_text} 일이 없어요! 😊", [])
                        return (f"{status_text} 일이 없어요! 😊", [])
                    if user_name:
                        return (f"{user_name}님이 아직 맡은 일이 없어요! 😊", [])
                    return ("아직 맡은 일이 없어요! 😊", [])

                message = format_my_tasks(tasks, status_text)
                return (message, tasks)
        
        # 2. "다른 사람" 패턴 (구체적이므로 먼저 체크)
        elif (any(pattern in query_lower for pattern in ['다른 사람', '다른사람', '다른 담당', '다른담당']) or
            ('회의에서' in query_lower and any(pattern in query_lower for pattern in ['다른 사람', '다른사람', '아무도', '전체', '모두']))):
            if meeting_id:
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.meeting_id = %s AND t.user_id != %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (meeting_id, user_id))
                tasks = cursor.fetchall()
                
                if not tasks:
                    cursor.execute("SELECT title FROM Meeting WHERE id = %s", (meeting_id,))
                    result = cursor.fetchone()
                    meeting_title = result['title'] if result else None
                    
                    if meeting_title:
                        return (f"{meeting_title}에서 다른 사람이 맡은 할 일은 없어요! 😊", [])
                    return ("이 회의에서 다른 사람이 맡은 할 일은 없어요! 😊", [])
                
                # meeting_title 추출
                meeting_title = tasks[0].get('meeting_title') if tasks else None
                message = format_meeting_tasks(tasks, meeting_title)
                return (message, tasks)
            else:  # ← 추가
                return ("어떤 회의의 담당자를 보고 싶으신가요? 😊", [])
                
        # 3. meeting_id만 있고 found_name이 없는 경우
        elif meeting_id and not found_name:
            # "다른 사람" 관련 질문 감지 (오타 포함)
            suspect_patterns = [
                '다른', '다름', '딴', '사람', '담당', '팀원', '멤버', '누가', 
                '아무', '모두', '전체', '나머지', '누구', '그외', '그 외',
                '다른이', '다른 이', '다른애', '다른 애'
            ]
            
            is_asking_others = any(w in query_lower for w in suspect_patterns)
            
            if is_asking_others:
                # 다른 사람 할일 검색 (현재 사용자 제외)
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.meeting_id = %s AND t.user_id != %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (meeting_id, user_id))  # user_id 추가!
                tasks = cursor.fetchall()
                
                if not tasks:
                    cursor.execute("SELECT title FROM Meeting WHERE id = %s", (meeting_id,))
                    result = cursor.fetchone()
                    meeting_title = result['title'] if result else None
                    
                    if meeting_title:
                        return (f"네, {meeting_title}에서 다른 사람이 맡은 할 일은 없어요! 😊", [])
                    return ("네, 이 회의에서 다른 사람이 맡은 할 일은 없어요! 😊", [])
                
                meeting_title = tasks[0].get('meeting_title') if tasks else None
                message = format_meeting_tasks(tasks, meeting_title)
                return (message, tasks)
            
            else:
                # "저 회의에서 할일" - 전체 할일 표시
                query = f"""
                    SELECT t.*, u.name as assignee_real_name, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN User u ON t.user_id = u.id
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.meeting_id = %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (meeting_id,))
                tasks = cursor.fetchall()
                
                # 회의 제목 추출
                meeting_title = tasks[0].get('meeting_title') if tasks else None
                if not meeting_title:
                    cursor.execute("SELECT title FROM Meeting WHERE id = %s", (meeting_id,))
                    result = cursor.fetchone()
                    meeting_title = result['title'] if result else None
                
                if not tasks:
                    if meeting_title:
                        return (f"네, {meeting_title}에서 정한 할 일이 없어요! 😊", [])
                    return ("네, 이 회의에서 정한 할 일이 없어요! 😊", [])
                
                message = format_meeting_tasks(tasks, meeting_title)
                return (message, tasks)
            
        # 4. "담당자 이름" 패턴 (김철수, 이영희 등)
        else:
            # 이름 추출 - 조사 목록을 먼저 제거
            import re
            
            # 이전에 이미 found_name이 설정된 경우 (회의 대명사 + 타인 이름)
            if 'found_name' not in locals():
                # 조사 제거
                cleaned_query = user_query
                josas = ['가', '이', '은', '는', '을', '를', '의', '와', '과', '에게', '한테', '께서', '님이', '님의', '님은', '님을']
                for josa in josas:
                    cleaned_query = cleaned_query.replace(josa, ' ')
                
                # 한글 이름 추출 (2-4글자)
                # DB에서 실제 사용자 이름 목록 가져오기
                cursor.execute("SELECT name FROM User")
                all_user_names = [row['name'] for row in cursor.fetchall()]
                
                # 쿼리에서 실제 이름 찾기
                found_name = None
                for name in all_user_names:
                    if name in user_query:
                        found_name = name
                        break
            
            if not found_name:
                return ("담당자 이름을 말씀해주세요! 😊", [])
            
            name = found_name

            # meeting_id가 있고 "전체"가 없으면 특정 회의 내에서 검색
            has_global_intent = (
                any(word in query_lower for word in ['전체', '모든', '전부', '전체에서', '전체적']) or
                ('다른' in query_lower and any(w in query_lower for w in ['회의', '일', '할일', '것']))
            )
            
            if meeting_id and not has_global_intent:
                # 특정 회의만
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.assignee_name LIKE %s AND t.meeting_id = %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (f'%{name}%', meeting_id))
            else:
                # 전체 검색
                query = f"""
                    SELECT t.*, m.title as meeting_title 
                    FROM Task t
                    LEFT JOIN Meeting m ON t.meeting_id = m.id
                    WHERE t.assignee_name LIKE %s {status_filter}
                    ORDER BY 
                        CASE WHEN t.due_date < CURDATE() THEN 0 ELSE 1 END,
                        t.due_date ASC
                    LIMIT 10
                """
                cursor.execute(query, (f'%{name}%',))
            
            tasks = cursor.fetchall()
            
            # 디버깅
            print(f"[DEBUG] 담당자 검색: name={name}, meeting_id={meeting_id if meeting_id else 'None'}")
            print(f"[DEBUG] 검색 결과: {len(tasks)}개")
            if tasks:
                print(f"[DEBUG] 첫 번째 결과: {tasks[0]}")
                        
            if not tasks:
                if status_text:
                    return (f"{name}님이 {status_text} 일을 찾을 수 없어요! 😊", [])
                return (f"{name}님이 담당한 일을 찾을 수 없어요! 😊", [])
            
            message = format_assignee_tasks(tasks, name, status_text)
            return (message, tasks)
        
    except Exception as e:
        logger.error(f"Task 검색 실패: {e}")
        import traceback
        traceback.print_exc()
        return ("Task 검색 중 오류가 발생했어요. 😢", [])
    
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

# ============================================================
# Participant 검색
# ============================================================

def search_participants(query_type: str, meeting_id: int = None, person_name: str = None):
    """
    참석자 검색
    
    query_type:
        - "meeting_participants": 특정 회의의 참석자 조회
        - "person_meetings": 특정 사람이 참석한 회의 조회
    
    Examples:
        search_participants("meeting_participants", meeting_id=1)
        search_participants("person_meetings", person_name="김철수")
    """
    from database import get_db_connection
    import logging
    
    logger = logging.getLogger(__name__)
    
    try:
        with get_db_connection() as conn:
            if not conn:
                return ("데이터베이스 연결에 실패했어요. 😢", [])
            
            cursor = conn.cursor()
            
            # ========== 1. 특정 회의의 참석자 조회 ==========
            if query_type == "meeting_participants":
                if not meeting_id:
                    return ("회의 정보가 없어요. 😢", [])
                
                # 회의 정보 먼저 가져오기
                cursor.execute("""
                    SELECT title, scheduled_at 
                    FROM Meeting 
                    WHERE id = %s
                """, (meeting_id,))
                meeting = cursor.fetchone()
                
                if not meeting:
                    return ("회의를 찾을 수 없어요. 😢", [])
                
                # 참석자 목록 조회
                cursor.execute("""
                    SELECT p.name, p.speaker_id, u.job
                    FROM Participant p
                    LEFT JOIN User u ON p.name = u.name
                    WHERE p.meeting_id = %s
                    ORDER BY p.name
                """, (meeting_id,))
                participants = cursor.fetchall()
                
                if not participants:
                    return (f"{meeting['title']}에는 등록된 참석자가 없어요. 😢", [])
                
                from formatting import format_meeting_participants
                message = format_meeting_participants(meeting, participants)
                return (message, participants)
            
            # ========== 2. 특정 사람이 참석한 회의 조회 ==========
            elif query_type == "person_meetings":
                if not person_name:
                    return ("사람 이름을 알려주세요. 😢", [])
                
                # 사용자 정보 조회
                cursor.execute("""
                    SELECT id, name, job 
                    FROM User 
                    WHERE name LIKE %s
                """, (f"%{person_name}%",))
                user = cursor.fetchone()
                
                if not user:
                    return (f"{person_name}님을 찾을 수 없어요. 😢", [])
                
                # 참석한 회의 목록 조회
                cursor.execute("""
                    SELECT 
                        m.id,
                        m.title,
                        m.scheduled_at,
                        m.status,
                        m.description
                    FROM Meeting m
                    JOIN Participant p ON m.id = p.meeting_id
                    WHERE p.name = %s
                    ORDER BY m.scheduled_at DESC
                    LIMIT 50
                """, (user['name'],))
                meetings = cursor.fetchall()
                
                if not meetings:
                    return (f"{user['name']}님이 참석한 회의를 찾을 수 없어요. 😢", [])
                
                from formatting import format_person_meetings
                message = format_person_meetings(user, meetings)
                return (message, meetings)
            
            else:
                return ("잘못된 검색 유형이에요. 😢", [])
    
    except Exception as e:
        logger.error(f"Participant 검색 실패: {e}")
        import traceback
        traceback.print_exc()
        return ("참석자 검색 중 오류가 발생했어요. 😢", [])
    

def search_keywords(keyword_name, user_job=None):
    """
    Keyword 테이블에서 특정 키워드로 회의 검색
    
    Args:
        keyword_name: 검색할 키워드
        user_job: 사용자 직무 (페르소나 정렬용)
    
    Returns:
        (message, meetings): 응답 메시지와 회의 목록
    """
    from .formatting import format_single_meeting, format_multiple_meetings_short
    from .config import ENABLE_PERSONA
    
    with get_db_connection() as conn:
        if not conn:
            return ("데이터베이스 연결 실패", [])
        
        try:
            cursor = conn.cursor()
            
            # Keyword 테이블과 Meeting 테이블 JOIN
            query = """
                SELECT DISTINCT m.* 
                FROM Meeting m
                JOIN MeetingKeyword mk ON m.id = mk.meeting_id
                JOIN Keyword k ON mk.keyword_id = k.id
                WHERE k.name LIKE %s
                ORDER BY m.scheduled_at DESC
                LIMIT 50
            """
            
            cursor.execute(query, (f'%{keyword_name}%',))
            meetings = cursor.fetchall()
            
            print(f"[DEBUG] Keyword 검색 결과: {len(meetings)}개 (키워드: {keyword_name})")
            
            # 결과 없음
            if not meetings or len(meetings) == 0:
                return (f"❌ '{keyword_name}' 키워드가 포함된 회의를 찾을 수 없어요.", [])
            
            # 페르소나 정렬
            if ENABLE_PERSONA and user_job and len(meetings) > 1:
                meetings = search_with_persona(meetings, user_job)
                print(f"[DEBUG] Keyword 검색: {user_job} 페르소나 정렬 완료")
            
            # 단일 회의
            if len(meetings) == 1:
                meeting_detail = format_single_meeting(meetings[0])
                message = f"✅ '{keyword_name}' 키워드가 포함된 회의를 찾았어요!\n\n{meeting_detail}"
                return (message, meetings)
            
            # 여러 회의
            else:
                detail = format_multiple_meetings_short(
                    meetings[:10],
                    user_query=f"'{keyword_name}' 키워드",
                    total=len(meetings) if len(meetings) > 10 else None,
                    date_info=None,
                    status=None
                )
                message = f"✅ '{keyword_name}' 키워드가 포함된 회의 {len(meetings)}개를 찾았어요!\n\n{detail}"
                return (message, meetings)
        
        except Exception as e:
            logger.error(f"Keyword 검색 실패: {e}")
            import traceback
            traceback.print_exc()
            return (f"'{keyword_name}' 키워드 검색 중 오류가 발생했어요. 😢", [])