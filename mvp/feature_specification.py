import asyncio
import datetime
import json
import logging
import math
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from gpt_utils import extract_json_from_gpt_response
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from mongodb_setting import get_feature_collection
from openai import AsyncOpenAI
from redis_setting import load_from_redis, save_to_redis

logger = logging.getLogger(__name__)
# 최상위 디렉토리의 .env 파일 로드
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

feature_collection = get_feature_collection()

def assign_featureId(feature: Dict[str, Any]) -> Dict[str, Any]:
    """
    기능 목록에 기능 ID를 할당합니다.
    
    Args:
        feature_data (List[Dict[str, Any]]): 기능 목록
        
    Returns:
        Dict[str, Any]: 기능 ID가 할당된 기능
    """
    # UUID4를 생성하고 문자열로 변환
    feature["_id"] = str(uuid.uuid4())
    
    print(f"ID 부여 결과: {feature}에 _id: {feature['_id']} 부여 완료")
    return feature


def calculate_priority(expected_days: int, difficulty: int) -> int:
    """
    개발 예상 시간과 난이도를 기반으로 우선순위를 계산합니다.
    
    Args:
        expected_days (int): 개발 예상 시간
        difficulty (int): 개발 난이도
        
    Returns:
        int: 우선순위가 계산된 데이터
    """
    
    # 시간과 난이도의 가중치 (시간이 더 중요하다고 가정)
    time_weight = 0.6
    difficulty_weight = 0.4
    
    # 정규화된 시간 점수 (시간이 짧을수록 점수가 높음)
    time_score = 1 - (expected_days / 30)  # 30일을 최대치로 가정
        
    # 정규화된 난이도 점수 (난이도가 낮을수록 점수가 높음)
    difficulty_score = 1 - ((difficulty - 1) / 4)
        
    # 최종 우선순위 점수 계산
    priority_score = (time_score * time_weight) + (difficulty_score * difficulty_weight)
        
    # 1-300 범위로 변환 (점수가 높을수록 우선순위가 높음)
    priority = math.ceil(priority_score * 300)
    
    return priority


### ======== Create Feature Specification ======== ###
async def create_feature_specification(email: str) -> Dict[str, Any]:
    # /project/specification에서 참조하는 변수 초기화
    stacks=[]
    project_members=[]
    
    # 프로젝트 정보 조회
    project_data = await load_from_redis(email)
    feature_data = await load_from_redis(f"features:{email}")
    if not project_data:
        raise ValueError(f"Project for user {email} not found")
    if not feature_data:
        raise ValueError(f"Feature for user {email} not found")

    try:
        if isinstance(project_data, str):
            project_data = json.loads(project_data)
    except Exception as e:
        logger.error(f"🚨 email이 일치하는 Project 정보 JSON 로드 중 오류 발생: {str(e)}")
        raise Exception(f"🚨 email이 일치하는 Project 정보 JSON 로드 중 오류 발생: {str(e)}") from e
    
    # 프로젝트 정보 추출
    try:
        projectId = project_data.get("projectId", "")
    except Exception as e:
        logger.error(f"projectId 접근 중 오류 발생: {str(e)}")
        raise

    try:
        project_start_date = project_data.get("startDate", "")
    except Exception as e:
        logger.error(f"project_start_date 접근 중 오류 발생: {str(e)}")
        raise

    try:
        project_end_date = project_data.get("endDate", "")
    except Exception as e:
        logger.error(f"project_end_date 접근 중 오류 발생: {str(e)}")
        raise

    print(f"프로젝트 아이디: {projectId}")
    
    try:
        members = project_data.get("members", [])
    except Exception as e:
        logger.error(f"members 접근 중 오류 발생: {str(e)}")
        raise

    for member in members:
        try:
            name = member.get("name")
        except Exception as e:
            logger.error(f"member name 접근 중 오류 발생: {str(e)}")
            continue

        print(f"멤버 이름: {name}")
        
        try:
            profiles = member.get("profiles", [])
        except Exception as e:
            logger.error(f"member profiles 접근 중 오류 발생: {str(e)}")
            continue

        print(f"멤버 프로필: {profiles}")
        
        for profile in profiles:
            try:
                profile_project_id = profile.get("projectId")
            except Exception as e:
                logger.error(f"profile projectId 접근 중 오류 발생: {str(e)}")
                continue

            if profile_project_id == projectId:
                print(f"프로젝트 아이디 일치: {projectId}")
                
                try:
                    stacks = profile.get("stacks", [])
                except Exception as e:
                    logger.error(f"profile stacks 접근 중 오류 발생: {str(e)}")
                    continue

                try:
                    positions = profile.get("positions", [])
                    position = positions[0] if positions else ""
                except Exception as e:
                    logger.error(f"profile positions 접근 중 오류 발생: {str(e)}")
                    continue

                try:
                    member_info = [
                        name,
                        position,
                        ", ".join(profile.get("stacks", []))
                    ]
                    project_members.append(", ".join(str(item) for item in member_info))
                except Exception as e:
                    logger.error(f"member_info 생성 중 오류 발생: {str(e)}")
                    continue

    try:
        if isinstance(feature_data, str):
            feature_data = json.loads(feature_data)
    except Exception as e:
        logger.error(f"🚨 features 접근 중 오류 발생: {str(e)}")
        raise Exception(f"🚨 features 접근 중 오류 발생: {str(e)}") from e
    
    print("\n=== 불러온 프로젝트 정보 ===")
    print("스택:", stacks)
    print("멤버:", project_members)
    print("기능 목록:", feature_data)
    print("시작일:", project_start_date)
    print("종료일:", project_end_date)
    print("=== 프로젝트 정보 끝 ===\n")
    
    # 프롬프트 템플릿 생성
    prompt = ChatPromptTemplate.from_template("""
    당신은 소프트웨어 기능 목록을 분석하여 기능 명세서를 작성하는 일을 도와주는 엔지니어입니다.
    다음 기능 정의서와 프로젝트 스택 정보, 프로젝트에 참여하는 멤버 정보를 분석하여 
    각 기능별로 상세 명세를 작성하고, 필요한 정보를 지정해주세요.
    절대 주석을 추가하지 마세요. 당신은 한글이 주언어입니다.
    
    프로젝트 개발에 사용되는 스택:
    {stacks}
    
    프로젝트 멤버별 [이름, 역할, 스택]를 융합한 리스트:
    {project_members}
    
    정의되어 있는 기능 목록:
    {feature_data}
    
    프로젝트 시작일:
    {startDate}
    프로젝트 종료일:
    {endDate}
    
    주의사항:
    1. 위 기능 정의서에 나열된 모든 기능에 대해 상세 명세를 작성해주세요.
    2. 새로운 기능을 추가하거나 기존 기능을 제외하지 마세요.
    3. 각 기능의 이름은 기능 정의서와 동일하게 사용하고 절대 임의로 바꾸지 마세요.
    4. 담당자 할당 시 각 멤버의 역할(BE/FE)을 고려해주세요.
    5. 기능 별 startDate와 endDate는 프로젝트 시작일인 {startDate}와 종료일인 {endDate} 사이에 있어야 하며, 그 기간이 expected_days와 일치해야 합니다.
    6. input과 output은 반드시 string으로 반환하세요.
    7. 반드시 아래의 JSON 형식을 정확하게 따라주세요.
    8. 모든 문자열은 쌍따옴표(")로 감싸주세요.
    9. 객체의 마지막 항목에는 쉼표를 넣지 마세요.
    10. 배열의 마지막 항목 뒤에도 쉼표를 넣지 마세요.
    11. expected_days는 양의 정수여야 합니다.
    12. difficulty는 1 이상 5 이하의 정수여야 합니다.
    13. startDate와 endDate는 "YYYY-MM-DD" 형식이어야 합니다.
    14. 각 기능에 대해 다음 항목들을 JSON 형식으로 응답해주세요:
    {{
        "features": [
            {{
                "name": "기능명",
                "useCase": "기능의 사용 사례 설명",
                "input": "기능에 필요한 입력 데이터",
                "output": "기능의 출력 결과",
                "precondition": "기능 실행 전 만족해야 할 조건",
                "postcondition": "기능 실행 후 보장되는 조건",
                "stack": ["프로젝트에 포함된 스택 중 사용 가능한 스택1", "프로젝트에 포함된 스택 중 사용 가능한 스택2"],
                "expected_days": 정수,
                "startDate": "YYYY-MM-DD",
                "endDate": "YYYY-MM-DD",
                "difficulty": 1
            }}
        ]
    }}
    """)
    
    # 프롬프트에 데이터 전달
    message = prompt.format_messages(
        stacks=stacks,
        project_members=project_members,
        feature_data=feature_data,
        startDate=project_start_date,
        endDate=project_end_date
    )
    
    # LLM 호출
    llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0.3)
    response = await llm.ainvoke(message)
    
    # 응답 파싱
    try:
        content = response.content
        try:
            gpt_result = extract_json_from_gpt_response(content)
        except Exception as e:
            logger.error(f"GPT util 사용 중 오류 발생: {str(e)}")
            raise Exception(f"GPT util 사용 중 오류 발생: {str(e)}") from e
        print(f"📌 응답 파싱 후 gpt_result 타입: {type(gpt_result)}")   # 현재 List 반환 중
        print(f"📌 gpt_result 내용: {gpt_result}")
        
        try:
            feature_list = gpt_result["features"]
        except Exception as e:
            logger.error(f"📌 gpt result에 list 형식으로 접근할 수 없습니다: {str(e)}")
            raise Exception(f"📌 gpt result에 list 형식으로 접근할 수 없습니다: {str(e)}") from e
        print(f"📌 feature_list 타입: {type(feature_list)}")   # 여기에서 List 반환되어야 함
        for i in range(len(feature_list)):
            print(f"📌 feature_list 하위 항목 타입: {type(feature_list[i])}")   # 여기에서 모두 Dict 반환되어야 함 (PASS)
            if type(feature_list[i]) != dict:
                raise ValueError("feature_list 하위 항목은 모두 Dict 형식이어야 합니다.")
        
        features_to_store = []
        for data in feature_list:
            feature = {
                "name": data["name"],
                "useCase": data["useCase"],
                "input": data["input"],
                "output": data["output"],
                "precondition": data["precondition"],
                "postcondition": data["postcondition"],
                "stack": data["stack"],
                "priority": calculate_priority(data["expected_days"], data["difficulty"]),
                "relfeatIds": [],
                "embedding": [],
                "startDate": data["startDate"],
                "endDate": data["endDate"],
                "expected_days": data["expected_days"],
                "difficulty": data["difficulty"]
            }
            feature = assign_featureId(feature)
            print(f"✅ 새롭게 명세된 기능 정보: {feature}")
            features_to_store.append(feature)   # 현재 JSON 타입과 충돌하지 않음 (List of Dict)
        
        # Redis에 저장
        print(f"✅ Redis에 저장되는 feature 정보들: {features_to_store}")
        try:
            await save_to_redis(f"features:{email}", features_to_store)
        except Exception as e:
            logger.error(f"feature_specification 초안 Redis 저장 실패: {str(e)}")
            raise e
        
        # API 응답 반환
        response = {
            "features": [
                {
                    "featureId": feature["_id"],  # assign_featureId에서 할당한 _id 사용
                    "name": feature["name"],
                    "useCase": feature["useCase"],
                    "input": feature["input"],
                    "output": feature["output"]
                }
                for feature in features_to_store
            ]
        }
        logger.info(f"👉 API 응답 결과: {response}")
        return response
    
    except Exception as e:
        logger.error(f"GPT API 응답 처리 중 오류 발생: {str(e)}")
        raise Exception(f"GPT API 응답 처리 중 오류 발생: {str(e)}") from e


### ======== Update Feature Specification ======== ###
async def update_feature_specification(email: str, feedback: str, createdFeatures: List[Dict[str, Any]], modifiedFeatures: List[Dict[str, Any]], deletedFeatures: List[str]) -> Dict[str, Any]:
    try:
        draft_feature_specification = await load_from_redis(f"features:{email}")
    except Exception as e:
        logger.error(f"Redis로부터 기능 명세서 초안 불러오기 실패: {str(e)}")
        raise Exception(f"Redis로부터 기능 명세서 초안 불러오기 실패: {str(e)}") from e
    
    # Redis에서 가져온 데이터가 문자열인 경우 JSON 파싱
    if isinstance(draft_feature_specification, str):
        draft_feature_specification = json.loads(draft_feature_specification)
    try:
        project_data = await load_from_redis(email)
    except Exception as e:
        logger.error(f"Redis로부터 프로젝트 데이터 불러오기 실패: {str(e)}")
        raise Exception(f"Redis로부터 프로젝트 데이터 불러오기 실패: {str(e)}") from e
    
    #print(f"👍 프로젝트 데이터 type: ", type(project_data)) # Dict가 반환됨

    project_start_date = project_data.get("startDate")
    project_end_date = project_data.get("endDate")  # 🚨 Project EndDate는 변경될 수 있음
    
    # 프로젝트 멤버와 스택 정보 추출    # 🚨 Project Members와 Stacks는 변경될 수 있음
    project_members = []
    stacks = []
    
    for member in project_data.get("members", []):
        try:
            name = member.get("name")
            profiles = member.get("profiles", [])
            for profile in profiles:
                if profile.get("projectId") == project_data.get("projectId"):
                    stacks.extend(profile.get("stacks", []))
                    position = profile.get("positions", [])[0] if profile.get("positions") else ""
                    member_info = [
                        name,
                        position,
                        ", ".join(profile.get("stacks", []))
                    ]
                    project_members.append(", ".join(str(item) for item in member_info))
        except Exception as e:
            logger.error(f"멤버 정보 처리 중 오류 발생: {str(e)}")
            continue
    
    current_features = draft_feature_specification
    
    print(f"project_start_date: {project_start_date}")
    print(f"project_end_date: {project_end_date}")
    print(f"project_members: {project_members}")
    print(f"stacks: {stacks}")
    print(f"current_features: {current_features}")
    
    prev_feat_num = len(current_features)
    ######### 삭제된 기능들 제거 (deletedFeatures는 featureId의 배열임)
    for deleted_feature in deletedFeatures:
        current_features = [feature for feature in current_features if feature["_id"] != deleted_feature]   # current features 목록에서 deleted features 배제
        
    print(f"삭제된 기능들 제거 결과: {current_features}\n전체 기능의 갯수가 {prev_feat_num}개에서 {len(current_features)}개로 줄었습니다.")
    
    # 현재 기능들을 featureId를 키로 하는 딕셔너리로 변환
    feature_dict = {feature["_id"]: feature for feature in current_features}
    ######### 수정된 기능들로 업데이트
    for modified_feature in modifiedFeatures:
        feature_id = modified_feature["featureId"]
        if feature_id in feature_dict:
            feature = feature_dict[feature_id]
            feature.update({
                "name": modified_feature["name"],
                "useCase": modified_feature["useCase"],
                "input": modified_feature["input"],
                "output": modified_feature["output"]
            })
    # 딕셔너리에서 다시 리스트로 변환
    try:
        current_features = list(feature_dict.values())
    except Exception as e:
        logger.error(f"current_features dict에서 list로 형변환 중 오류 발생: {str(e)}")
        raise Exception(f"current_features dict에서 list로 형변환 중 오류 발생: {str(e)}") from e
    
    print(f"수정된 기능들 업데이트 결과: {current_features}")
    
    ######### 생성된 기능들 추가
    for created_feature in createdFeatures:
        current_features.append(created_feature)
    
    print(f"생성된 기능들 추가 결과: {current_features}")
    
    
    # 피드백 분석 및 기능 업데이트
    update_prompt = ChatPromptTemplate.from_template("""
    당신은 사용자의 피드백을 분석하고 프로젝트 정보를 바탕으로 기능 명세에서 누락된 정보를 생성하거나 피드백을 반영하여 정보를 수정하는 전문가입니다.
    반드시 JSON으로만 응답해주세요. 추가 설명이나 주석은 절대 포함하지 마세요.
    
    프로젝트 정보:
    1. 프로젝트 시작일:
    {startDate}
    2. 프로젝트 종료일:
    {endDate}
    3. 프로젝트 멤버별 [이름, 역할, 스택]:
    {project_members}
    4. 프로젝트에서 사용 중인 스택:
    {stacks}
    5. 프로젝트에 현재 포함되어 있는 기능 목록:
    {current_features}
    
    사용자 피드백:
    다음은 기능 명세 단계에서 받은 사용자의 피드백입니다: {feedback}
    이 피드백이 다음 중 어떤 유형인지 판단해주세요:
    1. 수정/삭제 요청:
    예시: "담당자를 다른 사람으로 변경해 주세요", "~기능 개발 우선순위를 낮추세요", "~기능을 삭제해주세요.
    2. 종료 요청:
    예시: "이대로 좋습니다", "더 이상 수정할 필요 없어요", "다음으로 넘어가죠"
    1번 유형의 경우는 isNextStep을 0으로, 2번 유형의 경우는 isNextStep을 1로 설정해주세요.

    다음 형식으로 응답해주세요:
    주의사항:
    0. 반드시 모든 내용을 한국어로 작성해주세요. 만약 한국어로 대체하기 어려운 단어가 있다면 영어를 사용해 주세요.
    1. 반드시 위 JSON 형식을 정확하게 따라주세요.
    2. 모든 문자열은 쌍따옴표(")로 감싸주세요.
    3. 객체의 마지막 항목에는 쉼표를 넣지 마세요.
    4. features에서 null로 전달된 값이 있는 필드는 형식에 맞게 채워주세요.
    5. isNextStep은 사용자의 피드백이 종료 요청인 경우 1, 수정/삭제 요청인 경우 0으로 설정해주세요.
    6. 각 기능의 모든 필드를 포함해주세요.
    7. difficulty는 1에서 5 사이의 정수여야 합니다.
    8. expected_days는 양의 정수여야 합니다.
    9. 절대 주석을 추가하지 마세요.
    10. startDate와 endDate는 프로젝트 시작일인 {startDate}와 종료일인 {endDate} 사이에 있어야 하며, 그 기간이 expected_days와 일치해야 합니다.
    11. 요청에 포함된 값들 중 null이 존재할 경우, 해당 필드를 조건에 맞게 생성해 주세요.
    12. _id는 절대 수정하지 말고, 값이 없더라도 추가하지 마세요. current_features에 제시된 _id의 값과 동일한 값만 반환하세요.
    13. isNextStep을 1로 판단하였다면, 마지막으로 {feedback}의 내용이 반환할 결과에 반영되었는지 확인하세요.
    {{
        "isNextStep": 0 또는 1,
        "features": [
            {{
                "_id": "기능의 고유 ID",
                "name": "기능명",
                "useCase": "사용 사례",
                "input": "입력 데이터",
                "output": "출력 결과",
                "precondition": "기능 실행 전 만족해야 할 조건",
                "postcondition": "기능 실행 후 보장되는 조건",
                "stack": ["스택1", "스택2"],
                "expected_days": 정수,
                "startDate": "YYYY-MM-DD로 정의되는 기능 시작일",
                "endDate": "YYYY-MM-DD로 정의되는 기능 종료일"
                "difficulty": 1-5,
                "priority": 정수
            }}
        ]
    }}
    """)
    
    messages = update_prompt.format_messages(
        startDate=project_start_date,
        endDate=project_end_date,
        current_features=current_features,
        project_members=project_members,
        stacks=stacks,
        feedback=feedback,
    )
    
    # LLM Config
    llm = ChatOpenAI(
        model_name="gpt-4o-mini",
        temperature=0.3
    )
    response = await llm.ainvoke(messages)
    
    # 응답 파싱
    try:
        content = response.content
        try:
            gpt_result = extract_json_from_gpt_response(content)
        except Exception as e:
            logger.error(f"GPT util 사용 중 오류 발생: {str(e)}")
            raise Exception(f"GPT util 사용 중 오류 발생: {str(e)}") from e
        
        # 응답 검증
        if isinstance(gpt_result, dict) and "features" in gpt_result:
            feature_list = gpt_result["features"]
        elif isinstance(gpt_result, list):
            feature_list = gpt_result
        else:
            raise ValueError("GPT 응답이 유효한 features 리스트를 포함하지 않습니다.")
        
        if "isNextStep" not in gpt_result:
            raise ValueError("isNextStep 필드가 누락되었습니다.")
        
        if not isinstance(gpt_result["isNextStep"], int) or gpt_result["isNextStep"] not in [0, 1]:
            raise ValueError("isNextStep은 0 또는 1이어야 합니다.")
        
        if "features" not in gpt_result:
            raise ValueError("features 필드가 누락되었습니다.")
        
        if not isinstance(gpt_result["features"], list):
            raise ValueError("features는 배열이어야 합니다.")
        
        # 각 기능 검증
        for feature in feature_list:
            required_fields = [
                "_id", "name", "useCase", "input", "output", "precondition", "postcondition",
                "stack", "expected_days", "startDate", "endDate", "difficulty", "priority"
            ]
            for field in required_fields:
                if field not in feature:
                    raise ValueError(f"기능 '{feature.get('name', 'unknown')}'에 '{field}' 필드가 누락되었습니다.")
            
            if not isinstance(feature["stack"], list):
                raise ValueError(f"기능 '{feature['name']}'의 stack 형식이 잘못되었습니다.")
            
            if not isinstance(feature["expected_days"], int) or feature["expected_days"] <= 0:
                raise ValueError(f"기능 '{feature['name']}'의 expected_days는 양의 정수여야 합니다.")
            
            if not isinstance(feature["difficulty"], int) or not 1 <= feature["difficulty"] <= 5:
                raise ValueError(f"기능 '{feature['name']}'의 difficulty 형식이 잘못되었습니다.")
            
            if not feature["startDate"] >= project_start_date or not feature["endDate"] <= project_end_date:
                raise ValueError(f"기능 '{feature['name']}'의 startDate와 endDate는 프로젝트 시작일인 {project_start_date}와 종료일인 {project_end_date} 사이에 있어야 합니다.")
        
    except Exception as e:
        logger.error(f"GPT API 응답 처리 중 오류 발생: {str(e)}")
        raise Exception(f"GPT API 응답 처리 중 오류 발생: {str(e)}") from e
    
#     # 업데이트된 기능 정보를 기존 기능 리스트와 융합
#     updated_map = {feature["name"]: feature for feature in feature_list}
#     merged_features = []
    
#     # 기존 기능 리스트 순회
#     for current_feature in current_features:
#         feature_name = current_feature["name"]
#         if feature_name in updated_map:
#             # 업데이트된 기능이 있는 경우
#             updated = updated_map[feature_name]
#             merged_feature = current_feature.copy()
            
#             # expected_days나 difficulty가 변경되었는지 확인
#             if current_feature["expected_days"] is not None and updated["expected_days"] != current_feature["expected_days"]:
#                 expected_days_changed = True
#             if current_feature["difficulty"] is not None and updated["difficulty"] != current_feature["difficulty"]:
#                 difficulty_changed = True
            
#             merged_feature.update({
#                 "useCase": updated["useCase"],
#                 "input": updated["input"],
#                 "output": updated["output"],
#                 "precondition": updated["precondition"],
#                 "postcondition": updated["postcondition"],
#                 "stack": updated["stack"],
#                 "expected_days": updated["expected_days"],
#                 "startDate": updated["startDate"],
#                 "endDate": updated["endDate"],
#                 "difficulty": updated["difficulty"]
#             })
            
#             # priority 처리
#             if "priority" in updated:
#                 # GPT가 직접 priority를 지정한 경우
#                 merged_feature["priority"] = updated["priority"]
#             elif expected_days_changed or difficulty_changed:
#                 # expected_days나 difficulty가 변경된 경우 우선순위 재계산
#                 merged_feature["priority"] = calculate_priority(merged_feature["expected_days"], merged_feature["difficulty"])
#             else:
#                 # 변경사항이 없는 경우 기존 priority 유지
#                 merged_feature["priority"] = current_feature["priority"]
            
#             merged_features.append(merged_feature)
#         else:
#             # 업데이트되지 않은 기능은 그대로 유지
#             merged_features.append(current_feature)
    
    try:
        merged_features = gpt_result["features"]
    except Exception as e:
        logger.error(f"GPT 응답에서 features 필드 추출 중 오류 발생: {str(e)}")
        raise Exception(f"GPT 응답에서 features 필드 추출 중 오류 발생: {str(e)}") from e
    
    # _id가 없는 기능에 대해 assign_featureId 호출
    for feature in merged_features:
        if "_id" not in feature:
            feature = assign_featureId(feature)
        if "priority" not in feature:
            feature["priority"] = calculate_priority(feature["expected_days"], feature["difficulty"])
    
    # 업데이트된 기능 목록으로 교체
    logger.info("\n=== 업데이트된 feature_specification 데이터 ===")
    logger.info(json.dumps(merged_features, indent=2, ensure_ascii=False))
    logger.info("=== 데이터 끝 ===\n")
    
    # Redis에 저장
    try:
        await save_to_redis(f"features:{email}", merged_features)
    except Exception as e:
        logger.error(f"업데이트된 feature_specification Redis 저장 실패: {str(e)}")
        raise e
    
    # 다음 단게로 넘어가는 경우, MongoDB에 Redis의 데이터를 옮겨서 저장
    if gpt_result["isNextStep"] == 1:
        try:
            feature_collection = await get_feature_collection()
            for feat in merged_features:
                feature_data = {
                    "featureId": feat["_id"],
                    "name": feat["name"],
                    "useCase": feat["useCase"],
                    "input": feat["input"],
                    "output": feat["output"],
                    "precondition": feat["precondition"],
                    "postcondition": feat["postcondition"],
                    "stack": feat["stack"],
                    "expected_days": feat["expected_days"],
                    "startDate": feat["startDate"],
                    "endDate": feat["endDate"],
                    "difficulty": feat["difficulty"],
                    "priority": feat["priority"],
                    "projectId": project_data["projectId"],
                    "createdAt": datetime.datetime.utcnow()
                }
                try:
                    await feature_collection.insert_one(feature_data)
                    logger.info(f"{feat['name']} MongoDB 저장 성공 (ID: {feat['_id']})")
                except Exception as e:
                    logger.error(f"{feat['name']} MongoDB 저장 실패: {str(e)}")
                    raise e
            logger.info("모든 feature MongoDB 저장 완료")
        except Exception as e:
            logger.error(f"feature_specification MongoDB 저장 실패: {str(e)}")
            raise e
    
    # API 응답 반환
    response = {
        "features": [
            {
                "featureId": feature["_id"],
                "name": feature["name"],
                "useCase": feature["useCase"],
                "input": feature["input"],
                "output": feature["output"]
            }
            for feature in merged_features
        ],
        "isNextStep": gpt_result["isNextStep"]
    }
    logger.info(f"👉 API 응답 결과: {response}")
    return response
